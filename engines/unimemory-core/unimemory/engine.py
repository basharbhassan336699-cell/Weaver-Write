"""
UniMemory — محرك الذاكرة الموحّد.

يجمع أفضل ميزات الأدوات الأربعة في محرك واحد متماسك:
  • أنواع ذاكرة + تلاشي  (OpenMemory) — 5 قطاعات مع decay/salience
  • Graph معرفي          (Cognee)     — علاقات عبر الكيانات
  • Truth-checking       (Cognee)     — كشف التناقضات
  • Contextualizer آمن   (Zep)        — معالجة إدخال محمية
  • كشف الوكلاء          (mem0)       — تكامل تلقائي مع Claude Code/Cursor
  • LLM مزدوج            (الكل)       — Ollama + سحابي

المخزن: SQLite واحد (خفيف لـ Termux، قوي للخادم).
"""

from __future__ import annotations
import os
import sqlite3
import json
import time
from typing import Optional

from .memory_types import Memory, Sector, classify_sector
from .graph_store import GraphStore, Edge
from .truth_checker import TruthChecker, Verdict
from .llm import LLMClient
from .extract import extract_entities, extract_memories
from .compress import Compressor
from .distill import SessionDistiller


def detect_agent_caller() -> Optional[str]:
    """كشف الوكيل المستدعي — من mem0."""
    agents = {
        "claude-code": ("CLAUDECODE", "CLAUDE_CODE"),
        "cursor": ("CURSOR_AGENT", "CURSOR_SESSION_ID"),
        "codex": ("CODEX_CLI", "OPENAI_CODEX"),
        "cline": ("CLINE_AGENT", "CLINE"),
        "windsurf": ("WINDSURF_AGENT",),
    }
    for name, env_vars in agents.items():
        if any(os.environ.get(v) for v in env_vars):
            return name
    return None


class UniMemory:
    """
    محرك الذاكرة الموحّد.

    الاستخدام:
        mem = UniMemory("./memory.db")
        mem.add("المستخدم يفضل Python على JavaScript")
        results = mem.search("ما لغة البرمجة المفضلة؟")
    """

    def __init__(
        self,
        db_path: str = "./unimemory.db",
        *,
        llm_provider: Optional[str] = None,
        enable_truth_check: bool = True,
        enable_graph: bool = True,
        user_id: str = "default",
    ):
        self.db_path = db_path
        self.user_id = user_id
        self.agent = detect_agent_caller()

        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self._init_schema()

        self.llm = LLMClient(provider=llm_provider)
        self.graph = GraphStore(self.conn) if enable_graph else None
        self.truth = TruthChecker(self.llm) if enable_truth_check else None
        self.compressor = Compressor()
        self.distiller = SessionDistiller(self.llm)

    def _init_schema(self):
        self.conn.executescript("""
        CREATE TABLE IF NOT EXISTS memories (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            content TEXT NOT NULL,
            sector TEXT NOT NULL,
            node TEXT,
            salience REAL DEFAULT 1.0,
            decay_lambda REAL DEFAULT 0.005,
            created_at REAL,
            updated_at REAL,
            last_seen_at REAL,
            tags TEXT,
            entities TEXT,
            metadata TEXT,
            embedding TEXT,
            version INTEGER DEFAULT 1
        );
        CREATE INDEX IF NOT EXISTS idx_mem_user ON memories(user_id);
        CREATE INDEX IF NOT EXISTS idx_mem_sector ON memories(sector);
        CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts USING fts5(
            id UNINDEXED, content, tokenize='unicode61'
        );
        """)
        self.conn.commit()

    # ─────────────────────────────────────────────
    # الإضافة (مع Truth-check + Graph + Contextualize)
    # ─────────────────────────────────────────────

    def add(
        self,
        content: str,
        *,
        node: str = "observe",
        sector: Optional[str] = None,
        tags: Optional[list] = None,
        auto_extract: bool = True,
    ) -> Memory:
        """
        يضيف ذكرى مع كل المعالجات:
          1. تحديد القطاع (sector)
          2. استخراج الكيانات (للـ graph)
          3. فحص التناقض (truth-check)
          4. الحفظ + الفهرسة + الربط
        """
        sec = Sector(sector) if sector else classify_sector(node)

        mem = Memory(
            content=content, sector=sec, node=node,
            tags=tags or [], metadata={"user_id": self.user_id},
        )
        if self.agent:
            mem.metadata["agent"] = self.agent

        # استخراج الكيانات للـ graph
        if auto_extract and self.graph:
            mem.entities = extract_entities(content, self.llm)

        # embedding للبحث الدلالي
        try:
            mem.embedding = self.llm.embed(content)
        except Exception:
            mem.embedding = self.llm._simple_embed(content)

        # فحص التناقض ضد المشابهات
        if self.truth:
            similar = self._semantic_search(content, limit=3)
            check = self.truth.check(content, similar)
            if check.verdict == Verdict.DUPLICATE and check.conflicting_id:
                # تقوية الموجودة بدل التكرار
                existing = self.get(check.conflicting_id)
                if existing:
                    existing.reinforce()
                    self._update(existing)
                    return existing
            elif check.verdict == Verdict.CONTRADICTS and check.conflicting_id:
                existing = self.get(check.conflicting_id)
                if existing:
                    self.truth.resolve(check, mem, existing)
                    self._update(existing)

        self._insert(mem)

        # الربط في الـ graph
        if self.graph and mem.entities:
            self.graph.link_by_entities(mem.id, mem.entities)

        return mem

    # ─────────────────────────────────────────────
    # البحث (دلالي + graph + إعادة ترتيب بالأهمية)
    # ─────────────────────────────────────────────

    def search(
        self,
        query: str,
        *,
        limit: int = 5,
        sector: Optional[str] = None,
        use_graph: bool = True,
        reinforce: bool = True,
    ) -> list[Memory]:
        """
        بحث هجين:
          1. بحث دلالي (embedding) + FTS
          2. توسيع عبر الـ graph (ذكريات مرتبطة)
          3. إعادة ترتيب بالأهمية الحالية (بعد التلاشي)
          4. تقوية الذكريات المسترجعة
        """
        # ١. بحث دلالي
        candidates = self._semantic_search(query, limit=limit * 3, sector=sector)

        # ٢. توسيع عبر الـ graph
        if use_graph and self.graph and candidates:
            expanded_ids = set()
            for mem in candidates[:3]:
                related = self.graph.related_memories(mem.id, max_hops=2)
                expanded_ids.update(related)
            for mid in expanded_ids:
                m = self.get(mid)
                if m and m not in candidates:
                    candidates.append(m)

        # ٣. إعادة الترتيب بالأهمية الحالية (التلاشي)
        now = time.time()
        candidates.sort(key=lambda m: m.current_salience(now), reverse=True)
        results = candidates[:limit]

        # ٤. تقوية المسترجعة
        if reinforce:
            for mem in results:
                mem.reinforce(now=now)
                self._update(mem)

        return results

    def _semantic_search(self, query, limit=5, sector=None) -> list[Memory]:
        """بحث دلالي بالـ embedding + FTS fallback."""
        try:
            query_emb = self.llm.embed(query)
        except Exception:
            query_emb = self.llm._simple_embed(query)

        # جلب المرشحين (FTS للتصفية الأولية)
        sql = "SELECT * FROM memories WHERE user_id = ?"
        params = [self.user_id]
        if sector:
            sql += " AND sector = ?"
            params.append(sector)
        rows = self.conn.execute(sql, params).fetchall()

        # حساب التشابه cosine
        scored = []
        for row in rows:
            mem = self._row_to_memory(row)
            if mem.embedding:
                sim = self._cosine(query_emb, mem.embedding)
                scored.append((sim, mem))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [m for _, m in scored[:limit]]

    @staticmethod
    def _cosine(a: list, b: list) -> float:
        if not a or not b or len(a) != len(b):
            return 0.0
        dot = sum(x * y for x, y in zip(a, b))
        na = sum(x * x for x in a) ** 0.5 or 1.0
        nb = sum(y * y for y in b) ** 0.5 or 1.0
        return dot / (na * nb)

    # ─────────────────────────────────────────────
    # الصيانة (ضغط الذكريات المتلاشية)
    # ─────────────────────────────────────────────

    def consolidate(self, threshold: float = 0.1) -> int:
        """
        يحذف/يضغط الذكريات المتلاشية تحت العتبة.
        من OpenMemory: الذكريات الضعيفة تُنسى طبيعياً.
        """
        now = time.time()
        removed = 0
        rows = self.conn.execute(
            "SELECT * FROM memories WHERE user_id = ?", (self.user_id,)
        ).fetchall()
        for row in rows:
            mem = self._row_to_memory(row)
            if mem.is_faded(threshold, now):
                self.conn.execute("DELETE FROM memories WHERE id = ?", (mem.id,))
                self.conn.execute("DELETE FROM memories_fts WHERE id = ?", (mem.id,))
                removed += 1
        self.conn.commit()
        return removed

    # ─────────────────────────────────────────────
    # عمليات CRUD
    # ─────────────────────────────────────────────

    def get(self, memory_id: str) -> Optional[Memory]:
        row = self.conn.execute(
            "SELECT * FROM memories WHERE id = ?", (memory_id,)
        ).fetchone()
        return self._row_to_memory(row) if row else None

    def all(self, sector: Optional[str] = None) -> list[Memory]:
        sql = "SELECT * FROM memories WHERE user_id = ?"
        params = [self.user_id]
        if sector:
            sql += " AND sector = ?"
            params.append(sector)
        rows = self.conn.execute(sql, params).fetchall()
        return [self._row_to_memory(r) for r in rows]

    def delete(self, memory_id: str):
        self.conn.execute("DELETE FROM memories WHERE id = ?", (memory_id,))
        self.conn.execute("DELETE FROM memories_fts WHERE id = ?", (memory_id,))
        self.conn.commit()

    def stats(self) -> dict:
        """إحصاءات الذاكرة."""
        now = time.time()
        rows = self.conn.execute(
            "SELECT sector, COUNT(*) as cnt FROM memories WHERE user_id = ? GROUP BY sector",
            (self.user_id,)
        ).fetchall()
        by_sector = {r["sector"]: r["cnt"] for r in rows}
        total = sum(by_sector.values())
        faded = sum(1 for m in self.all() if m.is_faded(now=now))
        return {
            "total": total,
            "by_sector": by_sector,
            "faded": faded,
            "agent": self.agent,
            "llm_provider": self.llm.provider,
        }

    # ─────────────────────────────────────────────
    # داخلي
    # ─────────────────────────────────────────────

    def _insert(self, mem: Memory):
        self.conn.execute(
            "INSERT OR REPLACE INTO memories "
            "(id, user_id, content, sector, node, salience, decay_lambda, "
            " created_at, updated_at, last_seen_at, tags, entities, metadata, embedding, version) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (mem.id, self.user_id, mem.content, mem.sector.value, mem.node,
             mem.salience, mem.decay_lambda, mem.created_at, mem.updated_at,
             mem.last_seen_at, json.dumps(mem.tags), json.dumps(mem.entities),
             json.dumps(mem.metadata), json.dumps(mem.embedding) if mem.embedding else None,
             mem.version)
        )
        self.conn.execute(
            "INSERT OR REPLACE INTO memories_fts (id, content) VALUES (?, ?)",
            (mem.id, mem.content)
        )
        self.conn.commit()

    def _update(self, mem: Memory):
        self.conn.execute(
            "UPDATE memories SET salience=?, updated_at=?, last_seen_at=?, "
            "metadata=?, version=? WHERE id=?",
            (mem.salience, mem.updated_at, mem.last_seen_at,
             json.dumps(mem.metadata), mem.version, mem.id)
        )
        self.conn.commit()

    def _row_to_memory(self, row) -> Memory:
        return Memory(
            id=row["id"], content=row["content"], sector=Sector(row["sector"]),
            node=row["node"] or "observe", salience=row["salience"],
            decay_lambda=row["decay_lambda"], created_at=row["created_at"],
            updated_at=row["updated_at"], last_seen_at=row["last_seen_at"],
            tags=json.loads(row["tags"] or "[]"),
            entities=json.loads(row["entities"] or "[]"),
            metadata=json.loads(row["metadata"] or "{}"),
            embedding=json.loads(row["embedding"]) if row["embedding"] else None,
            version=row["version"],
        )

    # ─────────────────────────────────────────────
    # إضافة دفعية (من محادثة/وثيقة)
    # ─────────────────────────────────────────────

    def add_bulk(
        self,
        content: str,
        *,
        node: str = "observe",
        auto_split: bool = True,
    ) -> list[Memory]:
        """
        يضيف محتوى كبيراً مقسّماً لذكريات ذرّية.
        مفيد لإضافة وثيقة أو محادثة كاملة دفعة واحدة.
        """
        if auto_split:
            atomic = extract_memories(content, self.llm)
        else:
            atomic = [content]

        added = []
        for piece in atomic:
            if len(piece.strip()) >= 10:
                added.append(self.add(piece, node=node))
        return added

    # ─────────────────────────────────────────────
    # ضغط الذكريات المتلاشية (بدل حذفها)
    # ─────────────────────────────────────────────

    def compress_faded(self, threshold: float = 0.3, aggressive: bool = False) -> int:
        """
        يضغط الذكريات المتلاشية بدل حذفها — يحفظ الجوهر ويوفّر المساحة.
        بديل ألطف من consolidate: لا يفقد المعلومة، فقط يقلّصها.
        """
        now = time.time()
        compressed = 0
        for mem in self.all():
            sal = mem.current_salience(now)
            # الذكريات بين العتبة والحذف تُضغط
            if 0.1 <= sal < threshold and not mem.metadata.get("compressed"):
                original = mem.content
                shrunk = self.compressor.compress(original, aggressive=aggressive)
                if len(shrunk) < len(original):
                    mem.content = shrunk
                    mem.metadata["compressed"] = True
                    mem.metadata["original_length"] = len(original)
                    self.conn.execute(
                        "UPDATE memories SET content=?, metadata=? WHERE id=?",
                        (shrunk, json.dumps(mem.metadata), mem.id)
                    )
                    self.conn.execute(
                        "UPDATE memories_fts SET content=? WHERE id=?",
                        (shrunk, mem.id)
                    )
                    compressed += 1
        self.conn.commit()
        return compressed

    # ─────────────────────────────────────────────
    # استخلاص الدروس من جلسة
    # ─────────────────────────────────────────────

    def distill_session(
        self,
        messages: list,
        *,
        min_confidence: float = 0.5,
        store: bool = True,
    ) -> list:
        """
        يستخلص دروساً دائمة من محادثة ويخزّنها كذكريات reflective.

        Args:
            messages: قائمة رسائل [{role, content}]
            min_confidence: أدنى ثقة لقبول الدرس
            store: هل يخزّن الدروس تلقائياً
        """
        lessons = self.distiller.distill(messages, min_confidence)
        if store:
            for lesson in lessons:
                self.add(
                    lesson.lesson,
                    node="reflect",
                    sector=lesson.sector,
                    tags=["distilled"],
                )
        return lessons

    # ─────────────────────────────────────────────
    # التصدير والاستيراد
    # ─────────────────────────────────────────────

    def export_json(self, filepath: Optional[str] = None) -> str:
        """يصدّر كل الذكريات كـ JSON (للنقل/النسخ الاحتياطي)."""
        data = {
            "version": "1.0.0",
            "user_id": self.user_id,
            "exported_at": time.time(),
            "memories": [m.to_dict() for m in self.all()],
        }
        text = json.dumps(data, ensure_ascii=False, indent=2)
        if filepath:
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(text)
        return text

    def import_json(self, filepath_or_text: str, *, merge: bool = True) -> int:
        """
        يستورد ذكريات من JSON.

        Args:
            filepath_or_text: مسار ملف أو نص JSON مباشرة
            merge: دمج مع الموجود (True) أو استبدال (False)
        """
        # قراءة المصدر
        if filepath_or_text.strip().startswith("{"):
            data = json.loads(filepath_or_text)
        else:
            with open(filepath_or_text, encoding="utf-8") as f:
                data = json.load(f)

        if not merge:
            self.conn.execute("DELETE FROM memories WHERE user_id = ?", (self.user_id,))
            self.conn.execute("DELETE FROM memories_fts")
            self.conn.commit()

        imported = 0
        for mem_dict in data.get("memories", []):
            mem = Memory.from_dict(mem_dict)
            self._insert(mem)
            if self.graph and mem.entities:
                self.graph.link_by_entities(mem.id, mem.entities)
            imported += 1
        return imported

    def close(self):
        self.conn.close()
