"""
pipeline/orchestrator.py
========================
المنسّق المركزي لـ Weaver Write.

يُدير ٥ مهام متوازية، كل مهمة في pipeline مستقل.
يُوزّع المهام على الطبقات ويُتابع حالة كل مهمة.
"""

from __future__ import annotations
import asyncio
import uuid
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

try:
    from ..core.memory import MemoryManager, TaskMemory
    from ..core.sandbox import SandboxManager, TaskSandbox
except ImportError:
    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
    from core.memory import MemoryManager, TaskMemory
    from core.sandbox import SandboxManager, TaskSandbox

MAX_TASKS = 5

# Capability registry (Tools/Skills/Libraries) — Claude pattern
try:
    from capabilities import CapabilityRegistry
    _CAPABILITIES = CapabilityRegistry().load_all()
except Exception:
    _CAPABILITIES = None


class TaskStatus(str, Enum):
    QUEUED     = "في الطابور"
    LAYER_0    = "تنسيق"
    LAYER_1    = "بنية تحتية"
    LAYER_2    = "إدخال"
    LAYER_3    = "فهم"
    LAYER_4    = "بحث"
    LAYER_5    = "مصداقية"
    LAYER_6    = "صياغة"
    LAYER_6_5  = "إعادة صياغة"
    LAYER_7    = "تحقق"
    LAYER_8    = "إخراج"
    COMPLETED  = "مكتملة"
    FAILED     = "فشلت"


@dataclass
class Task:
    """مهمة بحثية واحدة."""
    task_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    description: str = ""
    input_files: list[str] = field(default_factory=list)
    status: TaskStatus = TaskStatus.QUEUED
    created_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    output_path: Optional[str] = None
    error: Optional[str] = None

    # أولوية الدور في الطابور — الأعلى يُنفَّذ أولاً (افتراضي 0)
    priority: int = 0

    # بطاقة المهمة (تُملأ في طبقة الفهم)
    task_card: dict = field(default_factory=dict)

    # ما يُوجَّه إليه في طبقة الفهم (Phase 3) ويُستهلك في الطبقات التالية
    tools: list = field(default_factory=list)     # أسماء الأدوات المطلوبة
    skills: list = field(default_factory=list)    # أسماء المهارات المطلوبة
    draft: str = ""                                # مسودة النص (طبقة ٦)
    sections: list = field(default_factory=list)   # أقسام الوثيقة النهائية

    def elapsed(self) -> float:
        if self.started_at:
            end = self.completed_at or time.time()
            return end - self.started_at
        return 0.0


class WeaverOrchestrator:
    """
    المنسّق المركزي — قلب Weaver Write.

    يُدير:
      - طابور المهام (Queue)
      - ٥ مهام نشطة بالتوازي
      - الذاكرة المعزولة لكل مهمة (UniMemory)
      - بيئة العزل لكل مهمة (OpenSandbox)
      - تتابع الطبقات من ٠ إلى ٨
    """

    def __init__(
        self,
        db_path: str = "./weaver_memory.db",
        sandbox_domain: str = "localhost:8080",
        sandbox_key: str = "",
        llm_fn=None,
        vision_fn=None,
    ):
        self.memory = MemoryManager(db_path=db_path)
        self.sandbox = SandboxManager(domain=sandbox_domain, api_key=sandbox_key)

        # The one LLM client, built from config/.env. May be None (no key) →
        # every layer then keeps its offline placeholder behaviour.
        try:
            from core.llm import get_llm_fn, get_vision_fn
            self.llm_fn = llm_fn or get_llm_fn()
            self.vision_fn = vision_fn or get_vision_fn()
        except Exception:
            self.llm_fn = llm_fn
            self.vision_fn = vision_fn
        self.caps = _CAPABILITIES

        # main system prompt + the professional-conduct rule (rule 10), so the
        # MODEL itself also stays calm under hostility
        try:
            from pipeline.prompts import SYSTEM_PROMPT_MAIN
            from capabilities.skills.conduct_guard.scripts.conduct_guard import (
                CONDUCT_SYSTEM_RULE)
            self.system_main = SYSTEM_PROMPT_MAIN + "\n\n" + CONDUCT_SYSTEM_RULE
        except Exception:
            try:
                from pipeline.prompts import SYSTEM_PROMPT_MAIN
                self.system_main = SYSTEM_PROMPT_MAIN
            except Exception:
                self.system_main = None

        self._queue: list[Task] = []
        self._active: dict[str, Task] = {}      # task_id → Task
        self._completed: list[Task] = []
        self._lock = asyncio.Lock()

    # ── إضافة مهمة ──

    async def submit(self, description: str, input_files: list[str] = None,
                     priority: int = 0) -> Task:
        """
        يُضيف مهمة جديدة. حتى ٥ مهام تعمل بالتوازي؛ الزائد يدخل طابور أولوية:
        الأعلى `priority` يُنفَّذ أولاً (وعند التساوي: الأقدم أولاً).
        """
        task = Task(
            description=description,
            input_files=input_files or [],
            priority=priority,
        )

        async with self._lock:
            if len(self._active) < MAX_TASKS:
                await self._start_task(task)
            else:
                # priority insert: place before the first lower-priority task
                idx = len(self._queue)
                for i, q in enumerate(self._queue):
                    if q.priority < task.priority:
                        idx = i
                        break
                self._queue.insert(idx, task)
                print(f"📋 مهمة [{task.task_id}] في الطابور "
                      f"(أولوية {task.priority}، {len(self._queue)} بالانتظار)")

        return task

    async def _start_task(self, task: Task):
        """يبدأ مهمة جديدة."""
        task.status = TaskStatus.LAYER_0
        task.started_at = time.time()
        self._active[task.task_id] = task

        # إنشاء ذاكرة معزولة
        self.memory.create_task(task.task_id)

        # إنشاء sandbox معزول
        await self.sandbox.create_for_task(task.task_id)

        print(f"🚀 بدأت مهمة [{task.task_id}]: {task.description[:50]}")

        # تشغيل في الخلفية
        asyncio.create_task(self._run_pipeline(task))

    # ── Pipeline كامل ──

    async def _run_pipeline(self, task: Task):
        """يُشغّل pipeline المهمة من الطبقة ٠ إلى ٨."""
        mem = self.memory.get_task(task.task_id)
        sb = self.sandbox.get(task.task_id)

        try:
            # ── conduct guard (before Layer 0): stay professional under abuse ──
            try:
                lang0 = self._detect_lang(task.description)
                g = self._skill_call("conduct_guard", "conduct_guard",
                                     "guard_response", task.description, lang0)
                task.task_card["conduct"] = g
                if g.get("hostile") and not g.get("do_task"):
                    # abuse only, no task: calm redirect, do nothing else
                    task.task_card["reply"] = g.get("reply_prefix", "")
                    task.status = TaskStatus.COMPLETED
                    task.completed_at = time.time()
                    return
            except Exception:
                pass

            # الطبقات بالتسلسل
            await self._layer_0(task, mem)
            await self._layer_1(task, mem, sb)
            await self._layer_2(task, mem)
            await self._layer_3(task, mem)
            await self._layer_4(task, mem)
            await self._layer_5(task, mem)
            await self._layer_6(task, mem)
            await self._layer_6_5(task, mem)
            await self._layer_7(task, mem)
            await self._layer_8(task, mem)

            # اكتمال
            task.status = TaskStatus.COMPLETED
            task.completed_at = time.time()
            print(f"✅ مهمة [{task.task_id}] اكتملت في {task.elapsed():.0f}ث")

            # استخلاص دروس
            mem.distill_task_lessons([
                {"role": "system", "content": f"مهمة اكتملت: {task.description}"},
                {"role": "system", "content": f"المخرج: {task.output_path}"},
            ])

        except Exception as e:
            task.status = TaskStatus.FAILED
            task.error = str(e)
            print(f"❌ مهمة [{task.task_id}] فشلت: {e}")

        finally:
            # تنظيف
            await self.sandbox.destroy(task.task_id)
            self.memory.close_task(task.task_id)

            async with self._lock:
                self._active.pop(task.task_id, None)
                self._completed.append(task)
                # تشغيل مهمة من الطابور إن وُجدت
                if self._queue:
                    next_task = self._queue.pop(0)
                    await self._start_task(next_task)

    # ── الطبقات ──

    async def _layer_0(self, task: Task, mem: TaskMemory):
        """٠: التنسيق — تسجيل المهمة وإعداد السياق."""
        task.status = TaskStatus.LAYER_0
        mem.set_status(0, "بدأ التنسيق")
        await asyncio.sleep(0)  # yield للـ event loop

    async def _layer_1(self, task: Task, mem: TaskMemory, sb: TaskSandbox):
        """١: البنية التحتية — تجهيز sandbox والأدوات."""
        task.status = TaskStatus.LAYER_1
        mem.set_status(1, "تجهيز البنية التحتية")
        # تثبيت مكتبات إضافية إن لزم
        if sb:
            await sb.install("paperqa", "pymupdf4llm")

    async def _layer_2(self, task: Task, mem: TaskMemory):
        """٢: الإدخال — قراءة الملفات مع أرقام الصفحات."""
        task.status = TaskStatus.LAYER_2
        mem.set_status(2, "قراءة الملفات")
        from core.ocr import WeaverOCR
        ocr = WeaverOCR()
        for filepath in task.input_files:
            doc = ocr.read_with_pages(filepath)
            # حفظ محتوى كل صفحة في الذاكرة
            for page in doc.pages:
                mem.add_reference(
                    f"[{os.path.basename(filepath)}] {page.text[:200]}",
                    page=page.page,
                )

    @staticmethod
    def _detect_lang(text: str) -> str:
        """Cheap language guess for the conduct guard: Arabic if any Arabic
        letter is present, else English."""
        for ch in (text or ""):
            if "؀" <= ch <= "ۿ":
                return "ar"
        return "en"

    @staticmethod
    def _sourcing_mode(text: str) -> str:
        """How the user wants sourcing handled — conservative: only an EXPLICIT
        request flips away from the default.
          "none"    → write WITHOUT any sources/references/studies.
          "uncited" → research FROM sources but DON'T document/cite them.
          "cited"   → default: research, cite in-text, and list references.
        """
        t = " " + (text or "").lower() + " "
        # sources are USED but must NOT be documented/cited
        uncited = (
            "بدون توثيق", "بلا توثيق", "دون توثيق", "من غير توثيق",
            "لا توثقها", "لا توثق", "بدون توثيقها", "دون توثيقها",
            "بدون ذكر المراجع", "دون ذكر المراجع", "بدون ذكر المصادر",
            "دون ذكر المصادر", "لا تذكر المراجع", "لا تذكر المصادر",
            "بدون ان توثقها", "بدون أن توثقها", "لكن لا توثقها",
            "without citing", "without documenting", "don't cite",
            "do not cite", "no in-text citation", "no in text citation",
            "uncited", "without a references list", "no references list",
        )
        # NO sources at all
        none_src = (
            "بدون مصادر", "بلا مصادر", "دون مصادر", "من غير مصادر",
            "بدون أي مصادر", "بدون اي مصادر", "بدون مراجع", "بلا مراجع",
            "دون مراجع", "من غير مراجع", "بدون دراسات", "بلا دراسات",
            "دون دراسات", "من غير دراسات", "بدون مصادر ومراجع",
            "without sources", "without references", "no sources",
            "no references", "no citations", "source-free", "without any sources",
        )
        if any(p in t for p in uncited):
            return "uncited"
        if any(p in t for p in none_src):
            return "none"
        return "cited"

    @staticmethod
    def _strip_citations(text: str) -> str:
        """Remove parenthesised in-text citations (…, YEAR) / (key, p. N) /
        (…، ص. N) from prose. Used in the no-citation writing modes so an
        accidental citation from the model never survives to the output."""
        import re
        if not text:
            return text
        text = re.sub(
            r"\s*\([^()]*(?:\b\d{4}\b|p\.?\s*\d+|ص\.?\s*\d+)[^()]*\)", "", text)
        return re.sub(r"[ \t]{2,}", " ", text)

    @staticmethod
    def _looks_conversational(text: str) -> bool:
        """True when a section body is a chat turn (greeting / clarifying
        question / options menu) instead of document content — so it can be
        retried or dropped. Conservative: needs a real chat marker, not just a
        question mark inside otherwise substantial prose."""
        t = (text or "").strip()
        if not t:
            return False
        head = t[:400]
        markers = (
            "أهلاً", "أهلًا", "اهلا", "مرحبا", "مرحباً", "عزيزي",
            "ما الذي تريد", "ماذا تريد", "يرجى التوضيح", "الرجاء التوضيح",
            "أحتاج أن أحدد", "أحتاج إلى تحديد", "هل تريد", "هل تفضل",
            "بحاجة إلى مزيد", "أخبرني", "قبل أن أبدأ", "قبل أن أكتب",
            "hello", "hi there", "could you clarify", "what would you like",
            "which of the following", "please specify", "let me know",
            "before i begin", "i need to know", "would you like",
        )
        low = head.lower()
        if any(m in head or m in low for m in markers):
            return True
        # an options menu near the top: "أ." / "ب." / "ج." or "a)" "b)" list
        import re
        if re.search(r"(^|\n)\s*[أ-د]\s*[\.\)\-]", head) and (
                "؟" in head or "?" in head):
            return True
        # very short and ends in a question → almost certainly a clarifying Q
        if len(t) < 200 and t.rstrip().endswith(("؟", "?")):
            return True
        return False

    @staticmethod
    def _skill_call(skill: str, module: str, func: str, *args, **kwargs):
        """Dynamically import capabilities/skills/<skill>/scripts/<module>.py
        and call <func>(*args, **kwargs). Raises on failure — callers guard it
        so the pipeline degrades to placeholder behaviour."""
        import os as _os, sys as _sys, importlib
        sp = _os.path.abspath(_os.path.join(
            _os.path.dirname(__file__), "..", "capabilities", "skills",
            skill, "scripts"))
        if sp not in _sys.path:
            _sys.path.insert(0, sp)
        mod = importlib.import_module(module)
        return getattr(mod, func)(*args, **kwargs)

    @staticmethod
    def _primary_format(task_card: dict) -> str:
        """The first requested output format as a lowercase string (docx/pptx/
        xlsx/pdf), tolerating either a list or a bare string in the card."""
        of = task_card.get("output_format", ["DOCX"])
        if isinstance(of, list):
            of = of[0] if of else "DOCX"
        return str(of).lower()

    def _placeholder_card(self, task: Task) -> dict:
        """The offline fallback task card (used when llm_fn is None or fails)."""
        return {
            "task_type": "بحث",
            "topic": task.description,
            "language": "ar",
            "citation_style": "APA",
            "output_format": ["DOCX"],
        }

    def _route(self, task: Task):
        """Phase 3: from the understood task_card, compute ONCE the tools &
        skills the task needs, so later layers act only on what's required
        (each tool/skill invoked only when needed — no overlap)."""
        card = task.task_card
        of = card.get("output_format", [])
        of = of if isinstance(of, list) else [of]
        text = f"{card.get('topic','')} {task.description} " \
               f"{card.get('task_type','')} {' '.join(str(x) for x in of)}"
        if self.caps:
            task.tools = [t.name for t in self.caps.match_tools(text)]
            task.skills = [s.name for s in self.caps.match_skills(text)]
        else:
            task.tools, task.skills = [], []
        # sourcing mode decides whether we gather and/or document sources
        mode = card.get("sourcing_mode", "cited")
        # always-on skills by task type
        cs = str(card.get("citation_style", "")).upper()
        # a citation-style formatter runs ONLY when sources will be documented
        if mode == "cited" and cs and cs != "UNSPECIFIED":
            task.skills.append("apa_formatter" if cs == "APA" else "mla_formatter")
        task.skills.append("arabic_rewriter"
                           if card.get("language", "ar") == "ar"
                           else "english_rewriter")
        # gather live web sources for any task that needs references — its
        # triggers rarely appear in a plain "اكتب بحثاً…", so add it explicitly.
        # "cited" and "uncited" both gather (uncited uses them to inform the
        # text but won't cite them); "none" gathers nothing.
        needs_sources = mode != "none" and (
            card.get("needs_academic_search")
            or "academic_search" in task.tools
            or (mode == "cited" and cs and cs != "UNSPECIFIED")
            or card.get("reference_count")
            or str(card.get("task_type", "")).lower() in
            ("بحث", "research", "دراسة", "report", "تقرير", "مراجعة أدبيات",
             "literature review", "analysis", "تحليل", "أطروحة", "thesis"))
        if needs_sources:
            task.tools.append("web_search")
        if mode == "none":
            # explicit no-sources request: strip every source-gathering tool
            task.tools = [t for t in task.tools
                          if t not in ("web_search", "academic_search")]
            card.pop("needs_academic_search", None)
        task.tools = list(dict.fromkeys(task.tools))   # dedupe, keep order
        task.skills = list(dict.fromkeys(task.skills))

    async def _layer_3(self, task: Task, mem: TaskMemory):
        """٣: الفهم — تحليل المهمة وبناء بطاقتها ثم توجيه الأدوات/المهارات."""
        task.status = TaskStatus.LAYER_3
        mem.set_status(3, "تحليل المهمة")

        if self.llm_fn:
            from pipeline.prompts import PROMPT_LAYER_3_UNDERSTAND
            from core.llm import extract_json
            prompt = PROMPT_LAYER_3_UNDERSTAND.format(
                task_description=task.description)
            try:
                raw = self.llm_fn(prompt, system=self.system_main,
                                  temperature=0.2)
                task.task_card = extract_json(raw)
            except Exception as e:
                mem.set_status(3, f"فهم (تخطّي للنموذج: {e})")
                task.task_card = self._placeholder_card(task)
        else:
            task.task_card = self._placeholder_card(task)

        # normalize output_format to a list (prompt/canonical form)
        of = task.task_card.get("output_format")
        if isinstance(of, str):
            task.task_card["output_format"] = [of]
        elif not of:
            task.task_card["output_format"] = ["DOCX"]

        # how the user wants sourcing handled (cited / uncited / none). Detected
        # from the RAW request so an explicit "بدون مصادر" / "دون توثيقها" is
        # honoured even if the model didn't surface it in the card.
        task.task_card["sourcing_mode"] = self._sourcing_mode(task.description)

        # Phase 3: route tools & skills once
        self._route(task)

    async def _layer_4(self, task: Task, mem: TaskMemory):
        """٤: البحث — أكاديمي (PaperQA) + بحث ويب حي (SearXNG). يُشغَّل ما وُجّهت
        إليه طبقة الفهم فقط، ونتائج الويب تُخزَّن كمصادر للطبقتين ٥ و٦."""
        task.status = TaskStatus.LAYER_4
        want_academic = ("academic_search" in task.tools
                         or task.task_card.get("needs_academic_search"))
        want_web = "web_search" in task.tools
        if not want_academic and not want_web:
            mem.set_status(4, "لا يلزم بحث — تخطّي")
            return
        if want_academic:
            from pipeline.layers.layer_4_research import run as _layer4_run
            await _layer4_run(task, mem)
        if want_web:
            await self._web_search(task, mem)

    @staticmethod
    def _searx_query(instance: str, query: str, lang: str, limit: int,
                     timeout: int = 8):
        """Direct SearXNG JSON search. Returns a list of {title,url,content}
        or None when the instance is unreachable / returns nothing usable."""
        import urllib.parse
        import urllib.request
        import json as _json
        instance = (instance or "").rstrip("/")
        if not instance:
            return None
        params = {"q": query, "format": "json", "categories": "general"}
        if lang:
            params["language"] = lang
        url = instance + "/search?" + urllib.parse.urlencode(params)
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "WeaverWrite/1.0"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = _json.loads(resp.read().decode("utf-8"))
        except Exception:
            return None
        return [{"title": r.get("title", ""), "url": r.get("url", ""),
                 "content": r.get("content", "")}
                for r in (data.get("results", []) or [])[:limit]]

    @staticmethod
    def _doh_resolve(host: str, timeout: int = 10):
        """Resolve a hostname to an IPv4 via DNS-over-HTTPS, using resolvers
        addressed BY IP — so it needs NO working system DNS. This is the fix
        for Termux/Android where getaddrinfo fails with 'No address associated
        with hostname' even though HTTPS itself works. Returns an IP or None."""
        import urllib.parse
        import urllib.request
        import json as _json
        if not host:
            return None
        # Cloudflare (1.1.1.1) and Google (8.8.8.8) both present valid certs for
        # their own IPs, so https-by-IP validates without any name lookup.
        for base in ("https://1.1.1.1/dns-query",
                     "https://8.8.8.8/resolve",
                     "https://1.0.0.1/dns-query"):
            try:
                url = base + "?name=" + urllib.parse.quote(host) + "&type=A"
                req = urllib.request.Request(
                    url, headers={"accept": "application/dns-json"})
                with urllib.request.urlopen(req, timeout=timeout) as r:
                    data = _json.loads(r.read().decode("utf-8"))
                for ans in (data.get("Answer") or []):
                    if ans.get("type") == 1 and ans.get("data"):
                        return str(ans["data"]).strip()
            except Exception:
                continue
        return None

    @classmethod
    def _http_get(cls, url: str, headers: dict, timeout: int = 15):
        """HTTP GET that survives broken system DNS. Tries the normal resolver
        first; on a name-resolution failure it resolves the host via DoH
        (_doh_resolve) and retries by pinning getaddrinfo to that IP (TLS SNI /
        Host stay correct because the hostname is preserved). Returns decoded
        text, or None on any failure."""
        import urllib.request
        import urllib.error
        import urllib.parse
        import socket
        req = urllib.request.Request(url, headers=headers or {})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read().decode("utf-8", "replace")
        except Exception as e:
            reason = getattr(e, "reason", None)
            msg = (str(reason) + " " + str(e)).lower()
            is_dns = isinstance(reason, socket.gaierror) or isinstance(
                e, socket.gaierror) or ("address associated" in msg) or (
                "name or service" in msg) or ("name resolution" in msg) or (
                "getaddrinfo" in msg)
            if not is_dns:
                return None
        # DNS path: resolve via DoH and pin it
        host = urllib.parse.urlparse(url).hostname
        ip = cls._doh_resolve(host) if host else None
        if not ip:
            return None
        orig = socket.getaddrinfo

        def _pinned(h, p, *a, **k):
            if h == host:
                return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, p))]
            return orig(h, p, *a, **k)

        socket.getaddrinfo = _pinned
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read().decode("utf-8", "replace")
        except Exception:
            return None
        finally:
            socket.getaddrinfo = orig

    @staticmethod
    def _ddg_search(query: str, lang: str, limit: int, timeout: int = 12):
        """Direct DuckDuckGo search — NO server required (works on the phone as
        is). Hits the html.duckduckgo.com endpoint over plain HTTP, decoding
        DDG's redirect links. Prefers UniWeb/curl_impersonate (real browser
        fingerprint, beats bot-blocking) and falls back to urllib. Returns a
        list of {title,url,content} or None when nothing usable comes back."""
        import urllib.parse
        import urllib.request
        import html as _html
        import re
        q = (query or "").strip()
        if not q:
            return None
        params = {"q": q}
        if lang == "ar":
            params["kl"] = "xa-ar"      # region/language hint (best-effort)
        endpoint = ("https://html.duckduckgo.com/html/?"
                    + urllib.parse.urlencode(params))
        ua = ("Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/122.0.0.0 Mobile Safari/537.36")
        raw = None
        # 1) UniWeb (curl_impersonate) — best chance against anti-bot
        try:
            import os as _os, sys as _sys
            uw = _os.path.abspath(_os.path.join(
                _os.path.dirname(__file__), "..", "engines", "uniweb-core"))
            if uw not in _sys.path:
                _sys.path.insert(0, uw)
            import uniweb as _uniweb
            html = _uniweb.fetch(endpoint)
            if html and isinstance(html, str) and "result" in html:
                raw = html
        except Exception:
            raw = None
        # 2) urllib fallback — DNS-safe (works even when the phone's resolver
        #    fails: it retries over DNS-over-HTTPS). This is the path that makes
        #    search work on Termux/Android with broken getaddrinfo.
        if not raw:
            raw = WeaverOrchestrator._http_get(endpoint, {
                "User-Agent": ua, "Accept": "text/html",
                "Accept-Language": ("ar,en;q=0.8" if lang == "ar"
                                    else "en-US,en;q=0.8")}, timeout)
        if not raw:
            return None

        def _clean(s: str) -> str:
            return _html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", s))).strip()

        def _real_url(href: str) -> str:
            href = _html.unescape(href)
            m = re.search(r"[?&]uddg=([^&]+)", href)
            if m:
                return urllib.parse.unquote(m.group(1))
            if href.startswith("//"):
                return "https:" + href
            return href

        results = []
        for m in re.finditer(
                r'<a[^>]+class="[^"]*result__a[^"]*"[^>]+href="([^"]+)"[^>]*>'
                r'(.*?)</a>', raw, re.S):
            url = _real_url(m.group(1))
            if not url.startswith("http"):
                continue
            results.append({"title": _clean(m.group(2)), "url": url,
                            "content": ""})
            if len(results) >= limit:
                break
        # attach snippets (aligned by document order, best-effort)
        snips = re.findall(r'class="result__snippet"[^>]*>(.*?)</a>', raw, re.S)
        for i, s in enumerate(snips[:len(results)]):
            results[i]["content"] = _clean(s)
        return results or None

    async def _tool_web_search(self, query: str, lang: str, limit: int):
        """Fallback: the packaged web_search tool. Returns a results list
        (possibly empty) and never raises."""
        try:
            from capabilities.tools import tool_web_search
        except Exception:
            return []
        inputs = {"query": query, "language": lang, "limit": limit}
        inst = os.environ.get("WEAVER_SEARXNG_URL", "").strip()
        if inst:
            inputs["instance"] = inst
        try:
            res = await tool_web_search.run(inputs)
        except Exception:
            return []
        if not getattr(res, "ok", False):
            return []
        return [{"title": r.get("title", ""), "url": r.get("url", ""),
                 "content": r.get("content", "")}
                for r in (res.data or {}).get("results", [])]

    async def _extract_full(self, url: str):
        """Read a page's full text. Order: (0) UniWeb browser (curl_impersonate)
        → (1) tool_web_document (HTML via trafilatura, text PDFs via pdfplumber,
        SCANNED PDFs & images via OCR) → (2) plain trafilatura → None. Every
        branch degrades safely when a library/service is missing."""
        if not url:
            return None
        # 0) UniWeb browser (curl_impersonate: real browser fingerprint, beats
        #    bot-blocking). firecrawl is removed; needs curl_cffi on the device.
        try:
            import os as _os, sys as _sys
            uw = _os.path.abspath(_os.path.join(
                _os.path.dirname(__file__), "..", "engines", "uniweb-core"))
            if uw not in _sys.path:
                _sys.path.insert(0, uw)
            import uniweb as _uniweb
            html = _uniweb.fetch(url)
            if html and isinstance(html, str) and len(html.strip()) > 200:
                # clean the fetched HTML to article text via trafilatura
                try:
                    from trafilatura import extract as _tex
                    txt = _tex(html, output_format="markdown",
                               include_comments=False, include_tables=True)
                    if txt and txt.strip():
                        return txt
                except Exception:
                    pass
                return html
        except Exception:
            pass
        # 1) web_document: HTML + text-PDF + scanned-PDF(OCR) + image(OCR)
        try:
            from capabilities.tools import tool_web_document
            res = await tool_web_document.run({"url": url, "ocr_lang": "ara+eng"})
            if getattr(res, "ok", False):
                d = res.data or {}
                if d.get("text"):
                    return d["text"]
                pages = d.get("pages") or []
                joined = "\n\n".join(p.get("text", "") for p in pages
                                     if p.get("text"))
                if joined.strip():
                    return joined
        except Exception:
            pass
        # 2) fallback: plain HTML extractor (trafilatura only)
        try:
            from capabilities.tools import tool_web_extract
            res = await tool_web_extract.run({"url": url, "format": "markdown"})
            if getattr(res, "ok", False):
                return (res.data or {}).get("text")
        except Exception:
            pass
        # 3) last resort: DNS-safe raw GET (survives broken phone DNS) then
        #    clean with trafilatura if available, else return the raw HTML.
        try:
            ua = ("Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/122.0.0.0 Mobile Safari/537.36")
            html = self._http_get(url, {"User-Agent": ua, "Accept": "text/html"})
            if html and len(html.strip()) > 200:
                try:
                    from trafilatura import extract as _tex
                    txt = _tex(html, output_format="markdown",
                               include_comments=False, include_tables=True)
                    if txt and txt.strip():
                        return txt
                except Exception:
                    pass
                return html
        except Exception:
            pass
        return None

    async def _web_search(self, task: Task, mem: TaskMemory):
        """Live web research. If a SearXNG instance is reachable (WEAVER_SEARXNG_URL
        or the default http://127.0.0.1:8080), query it directly, take the top 3
        links and READ each page in full via tool_web_document (HTML, text/
        scanned PDFs with OCR, images); the rest are kept as snippets. If
        SearXNG is unreachable, fall back to the packaged
        web_search tool. Everything degrades safely — a missing library or a
        down service just yields fewer/no sources, never an error."""
        card = task.task_card
        query = (card.get("topic") or task.description or "").strip()
        if not query:
            return
        lang = "ar" if card.get("language", "ar") == "ar" else "en"
        limit = int(card.get("reference_count") or 8)

        # 1) SearXNG (env or default 8080), probed by actually querying it
        instance = os.environ.get("WEAVER_SEARXNG_URL", "").strip() or "http://127.0.0.1:8080"
        results = self._searx_query(instance, query, lang, limit)
        used = "searxng:" + instance
        # 2) DuckDuckGo direct — NO server needed (works on the phone as is)
        if not results:
            ddg = self._ddg_search(query, lang, limit)
            if ddg:
                results = ddg
                used = "duckduckgo"
        # 3) fall back to the packaged tool as a last resort
        if not results:
            results = await self._tool_web_search(query, lang, limit)
            used = "web_search"
        if not results:
            mem.set_status(4, "بحث ويب: لا نتائج (تدهور آمن)")
            return

        srcs = card.setdefault("sources", [])
        full_reads = 0
        for i, r in enumerate(results):
            url = r.get("url", "")
            title = r.get("title", "")
            snippet = r.get("content", "")
            content = snippet
            is_full = False
            if i < 3:  # read the top 3 links in full
                text = await self._extract_full(url)
                if text:
                    content = text
                    is_full = True
                    full_reads += 1
            srcs.append({"key": (title or url)[:60], "url": url, "title": title,
                         "content": content, "full": is_full})
            mem.add_reference(f"[ويب] {title} — {content[:300]} ({url})",
                              source_key=url)
        card["web_full_reads"] = full_reads
        mem.set_status(4, f"بحث ويب ({used}): {len(results)} نتيجة، "
                          f"قراءة كاملة لـ {full_reads} صفحة")

    async def _layer_5(self, task: Task, mem: TaskMemory):
        """٥: المصداقية — تمرير كل مصدر عبر check_source وإسقاط المرفوض."""
        task.status = TaskStatus.LAYER_5
        mem.set_status(5, "تقييم مصداقية المصادر")

        sources = task.task_card.get("sources") or []
        if not sources:
            return  # لا مصادر مُنظّمة لتصفيتها — أبقِ السلوك الافتراضي
        try:
            import os as _os, sys as _sys
            sp = _os.path.abspath(_os.path.join(
                _os.path.dirname(__file__), "..", "capabilities", "skills",
                "credibility_scorer", "scripts"))
            if sp not in _sys.path:
                _sys.path.insert(0, sp)
            import source_reliability as _sr
        except Exception as e:
            mem.set_status(5, f"مصداقية (تخطّي: {e})")
            return
        lang = task.task_card.get("language", "ar")
        kept, dropped = [], []
        for s in sources:
            url = s.get("url", "") if isinstance(s, dict) else str(s)
            r = _sr.check_source(url, task.task_card, lang)
            if r.get("allowed"):
                kept.append(s)
            else:
                dropped.append({"source": s, "reason": r.get("reason"),
                                "alternative": r.get("alternative")})
        task.task_card["sources"] = kept
        task.task_card["credibility"] = {"kept": len(kept), "dropped": dropped}
        mem.set_status(5, f"مصداقية: قُبل {len(kept)}، رُفض {len(dropped)}")

    async def _layer_6(self, task: Task, mem: TaskMemory):
        """٦: الصياغة — بناء البنية ثم المنهجية ثم كتابة كل قسم.
        كل خطوة تستخدم مهارة/قالباً موجوداً؛ عند غياب النموذج تبقى مسودة فارغة."""
        task.status = TaskStatus.LAYER_6
        mem.set_status(6, "صياغة البحث")
        card = task.task_card
        lang = card.get("language", "ar")

        # techniques for the model strength — shown in the tool-call/thinking UI,
        # never written into the output document. We already write per-section.
        try:
            card["reliability"] = self._skill_call(
                "weak_model_support", "weak_model_support", "reliability_plan",
                card.get("model_strength", "medium"))
        except Exception:
            pass

        # 1) البنية — تخطّى إذا كانت المهمة تُحدّد بنيتها بنفسها (build_structure→None)
        sections_plan = card.get("sections")
        if not sections_plan:
            try:
                plan = self._skill_call("research_structure", "structures",
                                        "build_structure", card, lang)
                if plan and plan.get("sections"):
                    sections_plan = plan["sections"]
                    card["sections"] = sections_plan
                    card.setdefault("tier", plan.get("tier"))
            except Exception as e:
                mem.set_status(6, f"بنية (تخطّي: {e})")
        if not sections_plan:
            sections_plan = [{"title": card.get("topic", "") or task.description,
                              "level": 1}]

        # 2) المنهجية — إن لزمت وغابت
        try:
            has_m = self._skill_call("research_methodology", "methodology",
                                     "has_methodology", card)
            if (not has_m and card.get("task_type", "") in
                    ("بحث", "research", "دراسة", "thesis", "report", "تقرير",
                     "analysis", "تحليل")):
                m = self._skill_call("research_methodology", "methodology",
                                     "build_methodology", card, lang)
                if m:
                    card["methodology"] = m
        except Exception as e:
            mem.set_status(6, f"منهجية (تخطّي: {e})")

        # 3) كتابة كل قسم بحقن سياقات RAG الخاصة به
        rag = mem.get_references(card.get("topic", "") or task.description,
                                 limit=20) or []
        rag_ctx = "\n".join(str(x) for x in rag)
        no_ctx = (not rag_ctx) or rag_ctx.strip() in ("", "(none)")
        mode = card.get("sourcing_mode", "cited")
        # In "cited" mode with NO retrieved context, don't refuse — write from
        # the model's knowledge and flag it so a clear note is added later.
        if mode == "cited" and no_ctx:
            card["sources_unavailable"] = True
        parts, out_sections = [], []
        for sec in sections_plan:
            title = sec.get("title") or sec.get("heading") or ""
            body = ""
            if self.llm_fn:
                from pipeline import prompts as _p
                if mode == "uncited":
                    prompt = _p.PROMPT_LAYER_6_WRITE_UNCITED.format(
                        section_name=title, topic=card.get("topic", ""),
                        length=card.get("page_count", ""),
                        rag_contexts=rag_ctx or "(none)", prior_content="")
                    system = _p.SYSTEM_PROMPT_WRITE_NO_SOURCES
                elif mode == "none" or no_ctx:
                    # explicit no-sources request, OR sources were required but
                    # none could be retrieved — write from knowledge, no refusal
                    prompt = _p.PROMPT_LAYER_6_WRITE_NO_SOURCES.format(
                        section_name=title, topic=card.get("topic", ""),
                        length=card.get("page_count", ""), prior_content="")
                    system = _p.SYSTEM_PROMPT_WRITE_NO_SOURCES
                else:
                    prompt = _p.PROMPT_LAYER_6_WRITE.format(
                        section_name=title, topic=card.get("topic", ""),
                        citation_style=card.get("citation_style", ""),
                        length=card.get("page_count", ""),
                        rag_contexts=rag_ctx or "(none)", prior_content="")
                    # dedicated WRITING system prompt: forbids clarifying
                    # questions/greetings that a chatty model would emit
                    system = _p.SYSTEM_PROMPT_WRITE
                try:
                    body = self.llm_fn(prompt, system=system, temperature=0.5)
                except Exception as e:
                    mem.set_status(6, f"كتابة قسم (تخطّي: {e})")
                # guard: a conversational model may answer with a greeting /
                # clarifying question / options menu instead of content. Detect
                # it and retry ONCE with a blunt content-only instruction.
                if self._looks_conversational(body):
                    firm = (prompt + "\n\n"
                            + ("اكتب نص هذا القسم كاملاً ومباشرةً الآن. ممنوع منعاً "
                               "باتاً: التحية، طرح أي سؤال، طلب توضيح، أو عرض "
                               "خيارات. ابدأ بالمحتوى فوراً."
                               if lang == "ar" else
                               "Write the full text of this section directly "
                               "now. Absolutely no greeting, no question, no "
                               "request for clarification, no options. Begin "
                               "with the content immediately."))
                    try:
                        retry = self.llm_fn(firm, system=_p.SYSTEM_PROMPT_WRITE,
                                            temperature=0.4)
                        if retry and not self._looks_conversational(retry):
                            body = retry
                        elif self._looks_conversational(body):
                            body = ""   # drop the chat turn rather than ship it
                    except Exception:
                        pass
            parts.append((f"{title}\n{body}").strip())
            out_sections.append({"heading": title, "body": body})
        task.draft = "\n\n".join(p for p in parts if p)
        task.sections = out_sections
        mem.set_status(6, f"صياغة: {len(out_sections)} قسم ({mode})")

    async def _layer_6_5(self, task: Task, mem: TaskMemory):
        """٦.٥: إعادة الصياغة والتنظيف — أنسنة النص وإزالة البصمة الآلية.

        تُطبّق صامتةً: تحمي الاستشهادات، تستبدل كلمات AI بمرادفات بشرية،
        وتزيل البصمات البصرية (الشرطات الطويلة، الرموز الزخرفية، الخلط اللغوي)
        حسب نوع الملف — مع إبقاء الرموز في عروض PowerPoint.
        """
        task.status = TaskStatus.LAYER_6_5
        mem.set_status(65, "إعادة الصياغة والتنظيف")

        lang = task.task_card.get("language", "ar")
        fmt = self._primary_format(task.task_card)
        file_type = {"pptx": "pptx", "xlsx": "xlsx", "pdf": "pdf"}.get(fmt, "docx")

        import os, sys
        # اختر السكربت حسب اللغة
        skill = "arabic_rewriter" if lang == "ar" else "english_rewriter"
        fname = "rewrite_ar" if lang == "ar" else "rewrite_en"
        scripts = os.path.join(os.path.dirname(__file__), "..", "capabilities",
                               "skills", skill, "scripts")
        scripts = os.path.abspath(scripts)
        if scripts not in sys.path:
            sys.path.insert(0, scripts)
        try:
            mod = __import__(fname)
            draft = task.draft or task.task_card.get("draft", "")
            if draft:
                # Protect citations from the AI-fingerprint cleaner (which would
                # otherwise strip "(Smith, 2023)" as a Latin-in-Arabic mix). We
                # mask them, humanize, then restore them intact.
                masked, cites = self._mask_citations(draft)
                result = mod.humanize_text(masked, file_type=file_type)
                task.draft = self._unmask_citations(result["text"], cites)
                task.task_card["humanized"] = True
                task.task_card["cleaning_issues"] = result.get("issues", [])
        except Exception as e:
            mem.set_status(65, f"إعادة الصياغة (تخطّي: {e})")

    # citation guards — keep (Author, Year) / (key, p. N) / (…، ص. N) intact
    _CITE_RE = None

    @classmethod
    def _mask_citations(cls, text: str):
        """Replace parenthesised citations with digit-only placeholders so the
        humanizer's Latin/decoration cleaning can't damage them."""
        import re
        if cls._CITE_RE is None:
            cls._CITE_RE = re.compile(
                r"\([^()]*(?:\b\d{4}\b|p\.?\s*\d+|ص\.?\s*\d+)[^()]*\)")
        cites = []

        def _sub(m):
            cites.append(m.group(0))
            return "" + str(len(cites) - 1) + ""
        return cls._CITE_RE.sub(_sub, text), cites

    @staticmethod
    def _unmask_citations(text: str, cites: list) -> str:
        import re
        if not cites:
            return text
        return re.sub(r"(\d+)",
                      lambda m: cites[int(m.group(1))]
                      if int(m.group(1)) < len(cites) else m.group(0), text)

    @staticmethod
    def _allowed_keys(task: Task) -> list:
        """Citation keys that really exist in the retrieved references."""
        keys = []
        for s in task.task_card.get("sources", []) or []:
            if isinstance(s, dict) and s.get("key"):
                keys.append(s["key"])
        pq = task.task_card.get("paperqa_result", {}) or {}
        for c in (pq.get("citations") or []):
            if isinstance(c, dict) and c.get("key"):
                keys.append(c["key"])
        return keys

    async def _layer_7(self, task: Task, mem: TaskMemory):
        """٧: التحقق من التوثيق — PaperQA truth-check ثم strict-RAG صارم:
        يُسقط أي استشهاد مفتاحه غير موجود فعلاً في المراجع المسترجَعة."""
        from pipeline.layers.layer_7_verify import run as _layer7_run
        await _layer7_run(task, mem)

        # No-citation modes: the text must carry NO in-text citations. Strip any
        # the model produced anyway (none / uncited / sources-were-unavailable).
        card = task.task_card
        if task.draft and (card.get("sourcing_mode") in ("none", "uncited")
                           or card.get("sources_unavailable")):
            task.draft = self._strip_citations(task.draft)
            task.sections = [{**s, "body": self._strip_citations(s.get("body", ""))}
                             for s in (task.sections or [])]
            return

        allowed = self._allowed_keys(task)
        # نُطبّق strict-RAG فقط حين توجد مفاتيح فعلية — وإلا فقد نحذف كل شيء
        if task.draft and allowed:
            try:
                res = self._skill_call("weak_model_support", "weak_model_support",
                                       "enforce_strict_rag", task.draft, allowed)
                task.draft = res["text"]
                task.task_card["citations_removed"] = res.get("removed", [])
                if res.get("removed"):
                    mem.set_status(7, f"حُذف {len(res['removed'])} استشهاد مُختلَق")
            except Exception as e:
                mem.set_status(7, f"تحقق صارم (تخطّي: {e})")


    @staticmethod
    def _resolve_output_dir() -> str:
        """Where finished files are written. Priority:
        1) WEAVER_OUTPUT_DIR (explicit override),
        2) the phone's shared storage in a "Weaver Write" folder — on
           Termux/Android (~/storage/shared, /storage/emulated/0, /sdcard),
        3) the project's outputs/ folder (desktop / when storage isn't set up).
        The chosen directory is created if missing."""
        import os
        env = os.environ.get("WEAVER_OUTPUT_DIR", "").strip()
        if env:
            d = os.path.expanduser(env)
            try:
                os.makedirs(d, exist_ok=True)
                return d
            except OSError:
                pass
        for base in (os.path.expanduser("~/storage/shared"),
                     "/storage/emulated/0", "/sdcard"):
            if os.path.isdir(base):
                d = os.path.join(base, "Weaver Write")
                try:
                    os.makedirs(d, exist_ok=True)
                    return d
                except OSError:
                    continue
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        d = os.path.join(root, "outputs")
        os.makedirs(d, exist_ok=True)
        return d

    def _export_fallback(self, out_dir: str, safe: str, task: Task) -> str:
        """Always writes a REAL file to disk (Markdown) even when a format's
        library is missing — so an output always exists."""
        import os
        out = os.path.join(out_dir, safe + ".md")
        body = task.draft or ""
        if not body and task.sections:
            body = "\n\n".join(f"# {s.get('heading','')}\n{s.get('body','')}"
                               for s in task.sections)
        with open(out, "w", encoding="utf-8") as f:
            f.write(body or "(لا يوجد محتوى بعد — لم يُضبط مفتاح النموذج)")
        return out

    @staticmethod
    def _resolve_font(card: dict) -> str:
        """Resolve the document font through fonts-core (engines/fonts-core).
        Keeps the requested name (Office renders it) but validates it against
        the bundled families. Falls back to a sane per-language default."""
        import os as _os, sys as _sys
        lang = card.get("language", "ar")
        requested = card.get("font") or (
            "Kufyan Arabic" if lang == "ar" else "Times New Roman")
        try:
            fc = _os.path.abspath(_os.path.join(
                _os.path.dirname(__file__), "..", "engines", "fonts-core"))
            if fc not in _sys.path:
                _sys.path.insert(0, fc)
            import fonts as _fonts
            info = _fonts.resolve_named_font(requested)
            return info.get("requested") or requested
        except Exception:
            return requested

    def _maybe_chart(self, task: Task, out_dir: str):
        """Build a chart PNG via chart_builder when the task provides a chart
        spec, or when charts are requested and tabular data exists. Returns the
        image path or None. Degrades safely if matplotlib is missing."""
        import os as _os, re as _re
        card = task.task_card
        spec = card.get("chart")
        if not spec:
            extras = card.get("extras") or {}
            data = card.get("data")
            if extras.get("charts") and isinstance(data, list) and len(data) >= 2:
                labels, vals = [], []
                for r in data:
                    if isinstance(r, (list, tuple)) and len(r) >= 2:
                        try:
                            vals.append(float(r[1]))
                            labels.append(str(r[0]))
                        except (TypeError, ValueError):
                            labels, vals = [], []
                            break
                if labels and vals and len(labels) == len(vals):
                    spec = {"type": "bar",
                            "data": {"labels": labels, "values": vals},
                            "title": card.get("topic", "")}
        if not spec or not spec.get("data"):
            return None
        base = _re.sub(r"\W+", "", (card.get("topic") or "chart"))[:30] or "chart"
        png = _os.path.join(out_dir, "chart_" + base + ".png")
        try:
            res = self._skill_call(
                "chart_builder", "build_chart", "build_chart",
                spec.get("type", "bar"), spec["data"], png,
                title=spec.get("title", ""), lang=card.get("language", "ar"))
            if isinstance(res, dict) and res.get("ok") is False:
                return None
            return png if _os.path.exists(png) else None
        except Exception:
            return None

    def _export(self, task: Task) -> str:
        """Route to the right builder by output_format and WRITE the file to
        the resolved output directory (the phone's "Weaver Write" folder on
        Android; see _resolve_output_dir). No download links. Any builder
        failure (e.g. a missing library) degrades to a real Markdown file."""
        import os, re
        card = task.task_card
        lang = card.get("language", "ar")
        fmt = self._primary_format(card)
        out_dir = self._resolve_output_dir()
        topic = (card.get("topic") or task.description or "document").strip()
        safe = re.sub(r'[\\/:*?"<>|]+', "", topic)
        safe = re.sub(r"\s+", "_", safe)[:60] or "document"
        title = topic
        sections = task.sections or [{"heading": title, "body": task.draft}]
        references = (card.get("paperqa_result") or {}).get("references")
        font = self._resolve_font(card)

        # generate a chart when requested/derivable and append it as an image
        chart_png = self._maybe_chart(task, out_dir)
        if chart_png:
            sections = sections + [{
                "heading": ("الرسم البياني" if lang == "ar" else "Chart"),
                "body": "",
                "image": {"path": chart_png, "caption": card.get("topic", "")}}]
            card["chart_path"] = chart_png

        try:
            if fmt == "docx":
                out = os.path.join(out_dir, safe + ".docx")
                cover = (card.get("cover") if self._skill_call(
                    "docx_builder", "docx_frontmatter", "should_add_cover", card)
                    else None)
                toc_pos = self._skill_call(
                    "docx_builder", "docx_frontmatter", "resolve_toc_position",
                    card) or "after_cover"
                self._skill_call(
                    "docx_builder", "docx_advanced", "build_rich_docx",
                    title=title, sections=sections, output_path=out, lang=lang,
                    font=font, references=references, toc=bool(card.get("toc")),
                    cover=cover, toc_position=toc_pos)
                return out
            if fmt == "pdf":
                out = os.path.join(out_dir, safe + ".pdf")
                self._skill_call("pdf_builder", "build_pdf", "build_pdf",
                                 sections=sections, output_path=out,
                                 title=title, lang=lang, references=references)
                return out
            if fmt == "pptx":
                out = os.path.join(out_dir, safe + ".pptx")
                slides = [{"title": s.get("heading", ""),
                           "bullets": [ln for ln in
                                       (s.get("body", "") or "").split("\n")
                                       if ln.strip()]}
                          for s in sections]
                self._skill_call("pptx_builder", "build_pptx", "build_pptx",
                                 slides=slides, output_path=out, lang=lang,
                                 title=title)
                return out
            if fmt == "xlsx":
                out = os.path.join(out_dir, safe + ".xlsx")
                data = card.get("data") or [[s.get("heading", ""),
                                             s.get("body", "")]
                                            for s in sections]
                headers = card.get("headers") or (
                    ["القسم", "المحتوى"] if lang == "ar"
                    else ["Section", "Content"])
                self._skill_call("xlsx_builder", "build_xlsx", "build_xlsx",
                                 data=data, output_path=out, headers=headers,
                                 lang=lang)
                return out
        except Exception:
            return self._export_fallback(out_dir, safe, task)
        return self._export_fallback(out_dir, safe, task)

    def _source_note(self, task: Task):
        """Prepend a short, honest note when the document was written without
        external sources: either because the user asked for that ("none"), or
        because sources were required but none could be retrieved on the device
        ("cited" + sources_unavailable). The "uncited" mode gets no note — the
        user deliberately chose not to document sources."""
        card = task.task_card
        mode = card.get("sourcing_mode", "cited")
        lang = card.get("language", "ar")
        note = None
        if mode == "none":
            note = ("أُعدّ هذا المستند دون مصادر خارجية بناءً على طلبك."
                    if lang == "ar" else
                    "This document was prepared without external sources, as "
                    "requested.")
        elif mode != "uncited" and card.get("sources_unavailable"):
            note = ("تعذّر الوصول إلى مصادر خارجية أثناء الإعداد، فحُرّر المحتوى "
                    "من المعرفة العامة."
                    if lang == "ar" else
                    "External sources could not be retrieved, so the content was "
                    "written from general knowledge.")
        if not note:
            return
        head = "ملاحظة" if lang == "ar" else "Note"
        if task.sections and (task.sections[0].get("heading") or "") == head:
            return
        task.sections = [{"heading": head, "body": note}] + (task.sections or [])
        if task.draft:
            task.draft = note + "\n\n" + task.draft
        card["source_note"] = note

    @staticmethod
    def _is_ref_heading(h: str) -> bool:
        h = (h or "").strip().lower()
        return any(k in h for k in ("مراجع", "مصادر", "references", "works cited",
                                    "bibliography"))

    def _append_references(self, task: Task):
        """Build the full reference list from the retrieved sources via the
        citation-style skill (apa_formatter / mla_formatter) and put it as the
        LAST section of the report, replacing any placeholder references
        heading. No sources → nothing added."""
        card = task.task_card
        # no-citation modes never get a references list
        if card.get("sourcing_mode") in ("none", "uncited"):
            return
        sources = card.get("sources") or []
        pq_refs = (card.get("paperqa_result") or {}).get("references")
        if not sources and not pq_refs:
            return
        lang = card.get("language", "ar")
        style = str(card.get("citation_style", "APA")).upper()
        skill = "mla_formatter" if style == "MLA" else "apa_formatter"
        module = "format_mla" if style == "MLA" else "format_apa"
        try:
            refs = self._skill_call(skill, module, "build_bibliography",
                                    sources, lang, pq_refs)
        except Exception:
            # minimal fallback list if the skill can't be loaded
            lines = []
            for i, s in enumerate(sources, 1):
                if isinstance(s, dict):
                    lines.append(f"{i}. {s.get('title') or s.get('key') or ''} "
                                 f"{s.get('url','')}".strip())
            refs = "\n".join(lines)
            if pq_refs:
                refs = (refs + "\n" + str(pq_refs)).strip()
        if not (refs or "").strip():
            return
        head = "قائمة المراجع" if lang == "ar" else "References"
        # drop any earlier placeholder references section, then append the real one
        task.sections = [s for s in (task.sections or [])
                         if not self._is_ref_heading(s.get("heading", ""))]
        task.sections.append({"heading": head, "body": refs})
        # also reflect it at the end of the chat draft
        if task.draft:
            task.draft = task.draft.rstrip() + "\n\n" + head + "\n" + refs
        card["references_list"] = refs

    async def _layer_8(self, task: Task, mem: TaskMemory):
        """٨: الإخراج — كتابة الملف النهائي على القرص في outputs/."""
        task.status = TaskStatus.LAYER_8
        mem.set_status(8, "توليد الملف النهائي")
        # honest note when the document was written without external sources
        try:
            self._source_note(task)
        except Exception as e:
            mem.set_status(8, f"ملاحظة المصادر (تخطّي: {e})")
        # append the full reference list at the very end of the report
        try:
            self._append_references(task)
        except Exception as e:
            mem.set_status(8, f"قائمة المراجع (تخطّي: {e})")
        # إضافة تقرير التحقق للوثيقة النهائية
        try:
            from pipeline.layers.layer_7_verify import format_verification_report
            verify_text = format_verification_report(
                task.task_card, lang=task.task_card.get("language", "ar")
            )
            if verify_text:
                mem.add_reference(f"[تقرير التحقق]\n{verify_text}", source_key="layer_8")
        except Exception:
            pass
        # كتابة الملف الفعلي على القرص
        try:
            task.output_path = self._export(task)
            mem.set_status(8, f"أُخرج الملف: {task.output_path}")
        except Exception as e:
            mem.set_status(8, f"إخراج (تخطّي: {e})")

    # ── تشغيل متزامن لطلب واحد عبر خط الأنابيب الكامل ──

    def _result(self, task: Task) -> dict:
        """Shape one finished task into a reply dict for the chat / terminal."""
        card = task.task_card
        reply = card.get("reply") or task.draft or ""
        return {
            "reply": reply,
            "output_path": task.output_path,
            "topic": card.get("topic"),
            "task_type": card.get("task_type"),
            "language": card.get("language"),
            "output_format": card.get("output_format"),
            "tools": task.tools,
            "skills": task.skills,
            "status": getattr(task.status, "value", str(task.status)),
        }

    def _emit(self, kind: str, label: str = "", detail: str = ""):
        """Push a progress event to the optional progress callback (used by the
        streaming chat endpoint to show tool-use steps live and in order)."""
        cb = getattr(self, "_progress", None)
        if not cb:
            return
        try:
            cb({"t": kind, "label": label, "detail": detail})
        except Exception:
            pass

    async def run_once(self, description: str, input_files: list = None,
                       sandbox: bool = False, progress=None) -> dict:
        """Run ONE request through the full pipeline (layers 0→8) and return the
        reply + output file path. Used by the web chat and the terminal so every
        request goes through the whole system. Isolated: its own task memory,
        created and closed here. Sandbox is off by default (text chat needs no
        package installs); pass sandbox=True for tasks with input files.
        `progress(ev)` receives step events for a live tool-use timeline."""
        self._progress = progress
        ar = (self._detect_lang(description) == "ar")
        L = (lambda a, e: a if ar else e)  # localized label helper
        task = Task(description=description, input_files=input_files or [])
        task.started_at = time.time()
        mem = self.memory.create_task(task.task_id)
        sb = None
        try:
            if sandbox:
                try:
                    sb = await self.sandbox.create_for_task(task.task_id)
                except Exception:
                    sb = None

            # conduct guard (before Layer 0): stay professional under abuse
            try:
                g = self._skill_call("conduct_guard", "conduct_guard",
                                     "guard_response", description,
                                     self._detect_lang(description))
                task.task_card["conduct"] = g
                if g.get("hostile") and not g.get("do_task"):
                    task.task_card["reply"] = g.get("reply_prefix", "")
                    task.status = TaskStatus.COMPLETED
                    return self._result(task)
            except Exception:
                pass

            await self._layer_0(task, mem)
            try:
                await self._layer_1(task, mem, sb)
            except Exception as e:
                mem.set_status(1, f"بنية تحتية (تخطّي: {e})")
            try:
                await self._layer_2(task, mem)
            except Exception as e:
                mem.set_status(2, f"إدخال (تخطّي: {e})")

            self._emit("step", L("فهم الطلب", "Understanding the request"))
            await self._layer_3(task, mem)
            self._emit("detail", "",
                       L("الأدوات: ", "Tools: ") + ", ".join(task.tools or []))

            if "academic_search" in task.tools or task.task_card.get("needs_academic_search"):
                self._emit("step", L("بحث أكاديمي", "Academic search"))
            if "web_search" in task.tools:
                self._emit("step", L("بحث في الويب", "Searching the web"))
            await self._layer_4(task, mem)
            _nsrc = len(task.task_card.get("sources", []) or [])
            _nfull = task.task_card.get("web_full_reads", 0)
            if _nsrc:
                d = L(f"{_nsrc} مصدر", f"{_nsrc} sources")
                if _nfull:
                    d += L(f" (قراءة كاملة لـ {_nfull})", f" ({_nfull} read in full)")
                self._emit("detail", "", d)

            self._emit("step", L("فحص مصداقية المصادر", "Checking source credibility"))
            await self._layer_5(task, mem)

            self._emit("step", L("كتابة المحتوى", "Writing the content"))
            await self._layer_6(task, mem)
            self._emit("detail", "",
                       L(f"{len(task.sections or [])} قسم",
                         f"{len(task.sections or [])} sections"))

            self._emit("step", L("تنظيف وأنسنة النص", "Cleaning up the text"))
            await self._layer_6_5(task, mem)

            self._emit("step", L("التحقق من التوثيق", "Verifying citations"))
            await self._layer_7(task, mem)

            self._emit("step", L("توليد الملف", "Generating the file"))
            await self._layer_8(task, mem)
            if task.output_path:
                self._emit("detail", "", task.output_path)

            task.status = TaskStatus.COMPLETED
            task.completed_at = time.time()
            return self._result(task)
        finally:
            self._progress = None
            try:
                if sb is not None:
                    await self.sandbox.destroy(task.task_id)
            except Exception:
                pass
            self.memory.close_task(task.task_id)

    # ── حالة النظام ──

    def status(self) -> dict:
        """حالة النظام الكاملة."""
        return {
            "active_tasks": len(self._active),
            "queued_tasks": len(self._queue),
            "completed_tasks": len(self._completed),
            "max_parallel": MAX_TASKS,
            "slots_available": MAX_TASKS - len(self._active),
            "tasks": {
                tid: {
                    "description": t.description[:40],
                    "status": t.status.value,
                    "elapsed": f"{t.elapsed():.0f}ث",
                }
                for tid, t in self._active.items()
            },
        }

    async def shutdown(self):
        """إيقاف نظيف للنظام."""
        await self.sandbox.destroy_all()
        self.memory.close_all()


import os  # needed for layer_2


# ── intent: is this a document/generation task, or a quick question? ──
# A quick question is answered directly by the model (fast, no file). A task
# with a creation intent (write/report/presentation/analysis/export …) goes
# through the full pipeline. Bilingual triggers; substring match.
_TASK_TRIGGERS = (
    # Arabic — creation verbs
    "اكتب", "أكتب", "اكتبي", "اعمل", "أعمل", "اصنع", "أنشئ", "انشئ", "صمم",
    "صمّم", "جهّز", "جهز", "حضّر", "حضر", "ولّد", "ولد", "أخرج", "اخرج", "لخّص",
    "لخص", "حلّل", "حلل",
    # Arabic — document nouns
    "بحث", "بحثاً", "مقال", "مقالة", "تقرير", "دراسة", "أطروحة", "رسالة علمية",
    "عرض", "بوربوينت", "شرائح", "ملف", "مستند", "وثيقة", "صفحة", "صفحات",
    "مراجع", "مرجع", "استشهاد", "جدول", "جداول", "رسم بياني", "مخطط", "واجب",
    "ملخص", "خطة", "سيرة ذاتية", "تحليل بيانات",
    # English — creation verbs + document nouns
    "write", "create", "generate", "make ", "design", "draft", "compose",
    "essay", "report", "article", "research", "paper", "presentation",
    "slides", "powerpoint", "deck", "document", "docx", "pptx", "xlsx", "pdf",
    "references", "citation", "table", "chart", "analyze data", "analyse data",
    "thesis", "dissertation", "summariz", "summaris", "outline", "resume",
    "cv ", "assignment",
)


def is_document_task(text: str) -> bool:
    """True when the message asks to produce/analyse a document (→ full
    pipeline); False for a quick conversational question (→ direct answer)."""
    t = (text or "").lower()
    return any(trig in t for trig in _TASK_TRIGGERS)


# ── synchronous entry point (used by web/server.py and weaver.py) ──
_SHARED_ORCH = None

import threading as _threading  # noqa: E402
import heapq as _heapq  # noqa: E402
import itertools as _itertools  # noqa: E402


class _PriorityGate:
    """A concurrency gate of `limit` slots with a PRIORITY wait queue: when all
    slots are busy, waiting callers are admitted highest-priority-first (FIFO on
    ties) as slots free — not in arrival order. Thread-safe; used to gate the
    sync pipeline across all request threads."""

    def __init__(self, limit):
        self.limit = limit
        self._lock = _threading.Lock()
        self._running = 0
        self._heap = []                      # (-priority, seq, Event)
        self._seq = _itertools.count()

    def acquire(self, priority: int = 0):
        with self._lock:
            if self._running < self.limit:
                self._running += 1
                return
            ev = _threading.Event()
            _heapq.heappush(self._heap, (-int(priority), next(self._seq), ev))
        ev.wait()   # a releaser hands us the slot (running already counts us)

    def release(self):
        with self._lock:
            if self._heap:
                _, _, ev = _heapq.heappop(self._heap)  # highest priority next
                ev.set()                                # slot handed over
            else:
                self._running = max(0, self._running - 1)

    def free_slots(self):
        with self._lock:
            return max(0, self.limit - self._running)

    def waiting(self):
        with self._lock:
            return len(self._heap)


# At most MAX_TASKS pipelines run at once across all request threads; extras
# wait in a priority queue (highest priority admitted first).
_PIPELINE_GATE = _PriorityGate(MAX_TASKS)

# words that bump a request's priority (so "عاجل …" jumps the queue)
_URGENT_WORDS = ("عاجل", "مستعجل", "أولوية عالية", "urgent", "asap",
                 "high priority", "بسرعة")


def task_priority(text: str) -> int:
    """Priority for a request: higher = admitted sooner when the 5 slots are
    full. Bumped by urgent keywords; default 0."""
    t = (text or "").lower()
    return 10 if any(w in t for w in _URGENT_WORDS) else 0


def pipeline_slots():
    """Free parallel slots right now (for diagnostics)."""
    return _PIPELINE_GATE.free_slots()


def run_pipeline_sync(description: str, input_files: list = None,
                      llm_fn=None, progress=None, priority: int = 0) -> dict:
    """Run one request through the full pipeline and return the reply dict.
    Safe to call from a synchronous context (a threaded HTTP handler, or the
    CLI): it spins its own event loop and its own isolated task memory. Each
    call builds the LLM client fresh from config/.env, so a key added at
    runtime is picked up without a restart. `progress(ev)` streams step
    events. At most MAX_TASKS (5) run concurrently; extras wait in a PRIORITY
    queue — higher `priority` is admitted first."""
    import asyncio
    import tempfile

    _PIPELINE_GATE.acquire(priority)
    try:
        fd, db = tempfile.mkstemp(prefix="weaver_", suffix=".db")
        os.close(fd)
        orch = WeaverOrchestrator(db_path=db, llm_fn=llm_fn)
        try:
            return asyncio.run(orch.run_once(description, input_files,
                                             sandbox=bool(input_files),
                                             progress=progress))
        finally:
            try:
                os.remove(db)
            except OSError:
                pass
    finally:
        _PIPELINE_GATE.release()
