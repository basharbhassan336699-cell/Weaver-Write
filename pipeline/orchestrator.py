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

# Built-in public SearXNG fallbacks, tried AUTOMATICALLY (no manual setup) only
# after the user's own instance/fallbacks AND DuckDuckGo have failed — so the
# reliable no-server path (DuckDuckGo) is never slowed by them. Public instances
# are flaky and many disable format=json, so each is attempted at most once per
# process (see _SEARX_DEAD) with a short timeout. Override/extend via the
# WEAVER_SEARXNG_FALLBACKS env var, which is tried earlier (before DuckDuckGo).
_DEFAULT_SEARXNG_FALLBACKS = [
    "https://searx.be",
    "https://search.inetol.net",
    "https://priv.au",
    "https://searx.tiekoetter.com",
]
_SEARX_DEAD = set()   # instances that failed this process — skipped next time

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
            await self._layer_6_6(task, mem)
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

    # explicit output-language directives (request words → language name the model
    # will write in). Order matters only for display; matching is substring-based.
    _LANG_NAMED = (
        ("العربية", ("بالعربية", "بالعربي", "باللغة العربية", "اكتبها بالعربية",
                     "اكتبه بالعربية", " عربي ", " عربى ", "in arabic", " arabic")),
        ("الإنجليزية", ("بالانجليزية", "بالإنجليزية", "بالانكليزية", "بالإنكليزية",
                        " انجليزي ", " إنجليزي ", "in english", " english")),
        ("الفرنسية", ("بالفرنسية", "بالفرنسي", "in french", " french")),
        ("الإسبانية", ("بالاسبانية", "بالإسبانية", "in spanish", " spanish")),
        ("الألمانية", ("بالالمانية", "بالألمانية", "in german", " german")),
        ("التركية", ("بالتركية", "in turkish", " turkish")),
        ("الروسية", ("بالروسية", "in russian", " russian")),
        ("الصينية", ("بالصينية", "in chinese", " chinese")),
        ("الأردية", ("بالاردية", "بالأردية", "in urdu", " urdu")),
        ("الفارسية", ("بالفارسية", "in persian", " persian", " farsi")),
        ("الهندية", ("بالهندية", "in hindi", " hindi")),
    )
    _LANG_SOURCE = (
        "اللغة الاصلية", "اللغة الأصلية", "بلغتها الاصلية", "بلغتها الأصلية",
        "بلغته الاصلية", "بلغته الأصلية", "بلغة الاصلية", "بلغة الأصلية",
        "بلغة الفيديو", "لغة الفيديو", "بلغة المصدر", "بلغة النص الاصلي",
        "بلغة النص الأصلي", "كما هي بلغتها", "بنفس اللغة", "بنفس لغة",
        "original language", "source language", "same language",
        "in its original", "keep the language", "keep it in",
    )

    # markers of a FULL-document write request — when present, the broad
    # (non-"only") reference/outline phrasings below are NOT treated as a limiting
    # scope (so "اكتب بحثاً عن X مع مراجع" stays a full research, not references-only).
    _WRITE_FULL_MARK = (
        "اكتب بحث", "اكتب لي بحث", "اكتب مقال", "اكتب دراسة", "اكتب تقرير",
        "اكتب موضوع", "اعمل بحث", "أعد بحث", "اعد بحث", "حضّر بحث", "حضر بحث",
        "جهّز بحث", "بحثاً كاملاً", "بحث كامل", "بحثا كاملا",
        "write a research", "write an essay", "write a report", "write a paper",
        "full research", "research paper")

    @staticmethod
    def _task_scopes(text):
        """Return the SET of limiting scopes a request asks for (composable):
        'references' (find/list sources, no writing), 'outline' (structure only),
        'plan' (a research proposal), 'part' (a specific part only). Empty set →
        a full document. Broad natural phrasings resolve here; the "only"/"فقط"
        forms fire unconditionally, while the softer forms fire only when the
        request is NOT a full-document write (so composites like "مراجع وهيكلة
        فقط" work, and "اكتب بحثاً + مراجع" stays a full research)."""
        t = " " + (text or "").lower() + " "
        writing = any(k in t for k in WeaverOrchestrator._WRITE_FULL_MARK)
        scopes = set()

        # ── references / sources / prior studies ──
        refs_only = ("مراجع فقط", "المراجع فقط", "فقط المراجع", "فقط مراجع",
                     "دراسات سابقة فقط", "فقط الدراسات", "الدراسات فقط",
                     "فقط المصادر", "المصادر فقط", "قائمة مراجع", "قائمة المراجع",
                     "قائمة مصادر", "قائمة الدراسات", "دون كتابة الموضوع",
                     "بلا كتابة", "references only", "just references",
                     "only references", "list of references", "sources only",
                     "only sources", "list sources", "bibliography")
        refs_soft = ("اوجد مراجع", "أوجد مراجع", "إيجاد مراجع", "ايجاد مراجع",
                     "جمع مراجع", "تجميع مصادر", "توفير مصادر", "حصر المراجع",
                     "ابحث عن مراجع", "ابحث لي عن مراجع", "البحث عن مراجع",
                     "جد مراجع", "هات مراجع", "هاتلي مراجع", "جيبلي مصادر",
                     "اعطني مراجع", "أعطني مراجع", "اعطني مصادر", "اعطني دراسات",
                     "زوّدني بمراجع", "زودني بمراجع", "دلّني على مراجع",
                     "اجمع لي مراجع", "احضر لي مصادر", "اجلب لي مراجع",
                     "مراجع عن", "مراجع حول", "مصادر عن", "مصادر حول",
                     "دراسات سابقة عن", "أدبيات الموضوع", "الأدبيات السابقة",
                     "find references", "find sources", "gather sources",
                     "collect references", "literature list")
        _limiting = ("فقط" in t or " only " in t or " just " in t)
        if any(k in t for k in refs_only) or (
                not writing and any(k in t for k in refs_soft)) or (
                # bare "مراجع/مصادر/دراسات" counts ONLY with a limiting cue and
                # no full-write verb — so composites like "مراجع وهيكلة فقط" work
                # while "اكتب بحثاً عن مصادر الطاقة" stays a full research.
                not writing and _limiting and any(
                    w in t for w in ("مراجع", "مصادر", "دراسات سابقة",
                                     "references", "sources"))):
            scopes.add("references")

        # ── research proposal (خطة/مقترح/بروبوزال) — distinct from an outline ──
        plan_kw = ("خطة بحثية", "خطة بحث", "خطة الدراسة", "خطة دراسة",
                   "خطة رسالة", "خطة أطروحة", "خطة اطروحة", "خطة ماجستير",
                   "خطة دكتوراه", "مقترح بحثي", "المقترح البحثي", "مقترح بحث",
                   "تصور مقترح", "تصوّر مقترح", "بروبوزال", "بروبوزل", "بروبزال",
                   "proposal", "research proposal", "thesis proposal",
                   "dissertation proposal", "study plan")
        if any(k in t for k in plan_kw):
            scopes.add("plan")

        # ── outline / structure (headings only) ──
        out_only = ("هيكل فقط", "الهيكل فقط", "فقط الهيكل", "العناصر فقط",
                    "فقط العناصر", "عناصر البحث فقط", "جدول المحتويات",
                    "الخطوط العريضة", "outline only", "just an outline",
                    "only an outline", "structure only", "just the outline",
                    "table of contents", "only outline")
        out_soft = ("هيكلة", "هيكل بحث", "هيكل الموضوع", "هيكل البحث",
                    "بنية البحث", "بنية الموضوع", "عناصر البحث", "عناصر الموضوع",
                    "أقسام البحث", "اقسام البحث", "فهرس البحث", "مخطط البحث",
                    "رؤوس الأقسام", "اعمل هيكل", "صمم هيكل", "صمّم هيكل",
                    "قسّم لي الموضوع", "قسم لي الموضوع", "outline", "structure of")
        if any(k in t for k in out_only) or (
                not writing and any(k in t for k in out_soft)):
            scopes.add("outline")

        # ── a specific part only ──
        part = ("اكتب فقط", "فقط اكتب", "جزء فقط", "فقط جزء", "المقدمة فقط",
                "فقط المقدمة", "قسم فقط", "فقط قسم", "فقرة فقط", "فقط الخاتمة",
                "الخاتمة فقط", "فصل فقط", "فقط هذا الجزء",
                "only the introduction", "only the conclusion",
                "just write the", "only write the", "write only the",
                "just the section", "only this part", "only this section")
        if any(k in t for k in part):
            scopes.add("part")
        return scopes

    @staticmethod
    def _task_scope(text):
        """Back-compat single-scope view of _task_scopes: the primary limiting
        scope, by priority references > plan > outline > part, or None."""
        scopes = WeaverOrchestrator._task_scopes(text)
        for s in ("references", "plan", "outline", "part"):
            if s in scopes:
                return s
        return None

    @staticmethod
    def _deliverable_contradicted(requirements):
        """Is a LIMITING deliverable (outline/references/plan/part) contradicted
        by the model's own requirements checklist? Returns a short Arabic reason
        or None.

        This is not keyword matching: it reads the TYPED fields the model itself
        produced (`kind` + numeric `target`) and asks whether they can coexist
        with a headings-only / sources-only deliverable. A real outline request
        carries no page target, no word target and no source count — so when any
        of those is present as a MUST, the limiting judgement is inconsistent with
        the very checklist that accompanies it. Used in ONE safe direction only:
        toward the fuller deliverable. Never raises."""
        try:
            hits = []
            for r in (requirements or []):
                if not isinstance(r, dict) or not r.get("must", True):
                    continue
                kind = str(r.get("kind") or "").lower()
                tgt = r.get("target")
                num = tgt if isinstance(tgt, int) and not isinstance(tgt, bool) \
                    else None
                # a length ask (pages/words) is impossible for a bare outline
                if kind == "length" and (num or 0) >= 3:
                    hits.append(f"طول مطلوب: {num}")
                # several sources to document belong to a written document
                elif kind == "source" and (num or 0) >= 3:
                    hits.append(f"مصادر مطلوبة: {num}")
                # depth of structure: sub-sections under sections (e.g. مطالب
                # inside مباحث) describe a document's body, not a heading list
                elif kind == "structure" and (num or 0) >= 2:
                    hits.append(f"بنية مفصّلة: {num}")
            # one signal alone can be a coincidence; two independent ones cannot
            uniq = {h.split(":")[0] for h in hits}
            if len(uniq) >= 2:
                return "، ".join(hits[:3])
            # a length ask on its own is already decisive: an outline has no
            # page count, so this single signal settles it
            for h in hits:
                if h.startswith("طول مطلوب"):
                    return h
            return None
        except Exception:
            return None

    @staticmethod
    def _task_action(text):
        """Detect an ACTION performed on EXISTING/PREVIOUS content rather than a
        fresh research: 'rewrite' | 'summarize' | 'translate' | 'convert' |
        'edit' | None. Broad natural phrasings. Order = priority."""
        t = " " + (text or "").lower() + " "
        edit = ("أضف إلى الملف", "أضف على الملف", "زد على نفس الملف", "عدّل الملف",
                "عدل الملف", "كمّل الملف", "أكمل الملف", "أكمل عليه", "نفس الملف",
                "أضف فقرة", "أضف قسم", "احذف قسم", "غيّر في الملف", "نسخة معدّلة",
                "نسخة أخرى", "edit the file", "append", "same file",
                "another version", "add to the file")
        convert = ("حوّل هذا الملف", "حول هذا الملف", "حوّله إلى", "حوله الى",
                   "اجعله بصيغة", "صدّر الناتج", "صدر الناتج", "حوّل الناتج",
                   "خذ الملخص واعمله", "نفس المحتوى بصيغة", "أخرجه بصيغة",
                   "convert to", "convert this", "export the previous",
                   "same content as")
        translate = ("ترجم", "ترجمه", "ترجم لي", "ترجمة النص", "بالإنجليزي",
                     "بالانجليزي", "إلى الإنجليزية", "الى الانجليزية", "بالعربي",
                     "إلى العربية", "translate", "in english", "into english",
                     "into arabic", "to arabic", "to english")
        summarize = ("لخّص", "لخص", "لخّصلي", "لخصلي", "لخّص لي", "اختصر",
                     "اختصار", "ملخّص", "ملخص", "أعطني ملخصاً", "باختصار",
                     "أهم النقاط", "اهم النقاط", "النقاط الرئيسية", "خلاصة",
                     "زبدة", "summary", "summarize", "summarise", "tl;dr",
                     "tldr", "key points", "in short")
        rewrite = ("أعد صياغة", "اعد صياغة", "صُغ من جديد", "صغ من جديد",
                   "أعد كتابة", "اعد كتابة", "حسّن الصياغة", "حسن الصياغة",
                   "هذّب النص", "هذب النص", "نقّح", "نقح النص", "طوّر الأسلوب",
                   "اجعله أكثر بشرية", "أنسِن", "انسن", "بأسلوب بشري",
                   "بصياغة أفضل", "بأسلوب أكاديمي", "بلغة أبسط", "أعد صياغة الملف",
                   "reword", "rephrase", "rewrite", "paraphrase", "humanize",
                   "improve wording", "improve the writing")
        for name, kws in (("edit", edit), ("convert", convert),
                          ("translate", translate), ("summarize", summarize),
                          ("rewrite", rewrite)):
            if any(k in t for k in kws):
                return name
        return None

    @staticmethod
    def _wants_table(text):
        """True when the user wants a TABLE inserted into the document (distinct
        from an Excel FILE, which is a format)."""
        t = " " + (text or "").lower() + " "
        return any(k in t for k in (
            "أدرج جدول", "ادرج جدول", "أضف جدول", "اضف جدول", "اعمل جدول",
            "ضع جدولاً", "ضع جدول", "رتّبه في جدول", "رتبه في جدول",
            "في جدول", "على شكل جدول", "بشكل جدول", "جدول يوضّح", "جدول مقارنة",
            "جدولاً", "insert a table", "add a table", "in a table",
            "as a table", "tabulate", "comparison table"))

    @staticmethod
    def _wants_chart(text):
        """True when the user wants a CHART/GRAPH drawn."""
        t = " " + (text or "").lower() + " "
        return any(k in t for k in (
            "رسم بياني", "رسمة بيانية", "رسماً بيانياً", "مخطط بياني",
            "مخطط أعمدة", "مخطط دائري", "مخطط خطي", "رسوم بيانية", "شارت",
            "تشارت", "بيان بياني", "رسم توضيحي بالأرقام", "chart", "graph",
            "plot", "bar chart", "pie chart", "line chart", "diagram of data",
            "visualize"))

    @staticmethod
    def _wants_data(text):
        """True when the user asks to FIND/GATHER data (numbers/statistics) about
        a topic or from a link (as opposed to writing a full research)."""
        t = " " + (text or "").lower() + " "
        return any(k in t for k in (
            "أوجد بيانات", "اوجد بيانات", "ابحث عن بيانات", "جمع بيانات",
            "جمّع بيانات", "بيانات عن", "بيانات حول", "إحصائيات عن",
            "احصائيات عن", "إحصاءات عن", "أرقام عن", "ارقام عن", "معطيات عن",
            "بيانات من", "استخرج بيانات", "استخرج البيانات", "بيانات من الرابط",
            "find data", "gather data", "data about", "statistics about",
            "numbers about", "extract data", "data from"))

    # documentation styles the pipeline can actually format. These are proper
    # NOUNS the user types literally ("APA"), not something to be inferred, so
    # matching them by name is exact — not the keyword-guessing we removed.
    _CITATION_STYLES = {
        "APA": ("apa", "أيه بي أيه", "ابا"),
        "MLA": ("mla", "إم إل إيه"),
        "CHICAGO": ("chicago", "شيكاغو"),
        "HARVARD": ("harvard", "هارفارد"),
        "IEEE": ("ieee", "آي تريبل إي"),
        "VANCOUVER": ("vancouver", "فانكوفر"),
    }

    @classmethod
    def _enrich_sources_for_citation(cls, sources, timeout=8, cap=10):
        """Fill in real authors/year/journal for sources that carry a DOI, by
        asking Crossref. Runs ONLY when the user asked for a documentation
        style — a proper APA/MLA entry cannot be built from {title, url}, which
        is all a web result carries. Bounded (cap + short timeout), fully
        guarded, and it never overwrites a field that is already known.
        Returns how many sources were enriched."""
        import json as _json
        done = 0
        for s in (sources or []):
            if done >= cap:
                break
            if not isinstance(s, dict) or s.get("authors") or s.get("author"):
                continue
            doi = str(s.get("doi") or "").strip()
            if not doi:
                continue
            try:
                raw = cls._http_get(
                    "https://api.crossref.org/works/"
                    + doi.replace(" ", ""),
                    {"User-Agent": cls._ACAD_UA, "Accept": "application/json"},
                    timeout)
                msg = (_json.loads(raw) or {}).get("message") or {} if raw else {}
            except Exception:
                continue
            if not msg:
                continue
            auths = []
            for a in (msg.get("author") or [])[:6]:
                nm = " ".join(x for x in (a.get("family"), a.get("given")) if x)
                if nm.strip():
                    auths.append(nm.strip())
            if auths:
                s["authors"] = auths
            yr = ((msg.get("issued") or {}).get("date-parts") or [[None]])[0][0]
            if yr and not s.get("year"):
                s["year"] = str(yr)
            ct = msg.get("container-title") or []
            if ct and not s.get("venue"):
                s["venue"] = ct[0]
            done += 1
        return done

    @staticmethod
    def _enrich_source(s):
        """Mine a gathered source for the metadata a citation style needs.
        Deterministic and offline: pulls a DOI out of the URL (…/10.21608/…),
        a 4-digit year out of the DOI/URL/title, and leaves everything else
        untouched. Never raises; unknown fields are simply absent."""
        import re
        if not isinstance(s, dict):
            return s
        url = str(s.get("url") or "")
        title = str(s.get("title") or "")
        if not s.get("doi"):
            m = re.search(r'(10\.\d{4,9}/[^\s"\'<>?#]+)', url)
            if m:
                s["doi"] = m.group(1).rstrip('.,);')
        if not s.get("year"):
            # a year inside the DOI path ("…/mjaf.2024.259661") or the URL/title
            for cand in (str(s.get("doi") or ""), url, title):
                m = re.search(r'(?<!\d)(19[5-9]\d|20[0-4]\d)(?!\d)', cand)
                if m:
                    s["year"] = m.group(1)
                    break
        return s

    @classmethod
    def _requested_citation_style(cls, text):
        """The documentation style the user asked for by NAME, or None.
        Nothing ever extracted this from the request: citation_style was only
        set by the layer-3 card (when the model happened to fill it in), so the
        writing prompt received an EMPTY "Citation style:" line and the writer
        invented its own citation format."""
        t = " " + (text or "").lower() + " "
        for style, names in cls._CITATION_STYLES.items():
            if any(n in t for n in names):
                return style
        return None

    @staticmethod
    def _wants_cover(text):
        """True when the user explicitly asks for a cover / title page."""
        t = " " + (text or "").lower() + " "
        return any(k in t for k in (
            "صفحة غلاف", "صفحة الغلاف", "غلاف", "بغلاف", "مع غلاف",
            "صفحة عنوان", "صفحة العنوان", "cover page", "title page",
            "with a cover", "add a cover"))

    @staticmethod
    def _wants_toc(text):
        """True when the user explicitly asks for a table of contents / index."""
        t = " " + (text or "").lower() + " "
        return any(k in t for k in (
            "فهرس", "صفحة فهرس", "صفحة الفهرس", "فهرست", "جدول المحتويات",
            "قائمة المحتويات", "صفحة المحتويات", "جدول محتويات",
            "table of contents", " toc ", "with a toc", "index page"))

    @staticmethod
    def _requirements_directive(card=None, section_name: str = "",
                                lang: str = "ar") -> str:
        """STAGE (ب) — turn the requirements checklist (from extract_requirements)
        into a SHORT directive appended to a section's writing prompt, so every
        section is written with the user's whole plan in view. Like the style
        director, it is guidance the model APPLIES WHERE IT FITS — never forced,
        and never imposed on a references list. Returns "" when there is no
        checklist or nothing writing-relevant. Pure logic; never raises."""
        reqs = (card or {}).get("requirements") or []
        if not isinstance(reqs, list) or not reqs:
            return ""
        n = (section_name or "").lower()
        if any(k in n for k in ("مراجع", "مصادر", "references", "bibliography")):
            return ""
        styles, contents, want_table = [], [], False
        for r in reqs:
            if not isinstance(r, dict):
                continue
            k = r.get("kind")
            t = (r.get("text") or "").strip()
            if not t:
                continue
            if k == "style":
                styles.append(t)
            elif k == "content":
                contents.append(t)
            elif k == "insert" and any(w in t.lower() for w in (
                    "جدول", "جداول", "table")):   # match the plural «جداول» too
                # keep the requirement's OWN wording: it says what the table must
                # CONTAIN. Only the flag used to survive, and the writer then got
                # a generic "a comparison or a set of terms" line — so a request
                # for «جداول تحتوي المصطلحات التقنية وشرحها» came back as
                # classification tables, exactly as that generic line asked.
                want_table = t
        if not (styles or contents or want_table):
            return ""
        if lang == "en":
            lines = ["Request requirements to honour in THIS section (apply "
                     "where they fit — never force):"]
            if styles:
                lines.append("- Keep to the requested style: "
                             + "؛ ".join(styles) + ".")
            if contents:
                lines.append("- Make sure to cover, where relevant: "
                             + "؛ ".join(contents) + ".")
            if want_table:
                lines.append(
                    "- Tables were requested as: “" + str(want_table) + "”. "
                    "Where this section's content fits THAT description, present "
                    "it as a Markdown table (| … | … |) whose columns match what "
                    "was asked for, instead of prose."
                    if isinstance(want_table, str) else
                    "- Where this section's content is a comparison or a set of "
                    "terms/values, present it as a Markdown table (| … | … |) "
                    "instead of prose.")
            return "\n".join(lines)
        lines = ["متطلّبات الطلب التي تُراعى في هذا القسم (طبّقها حيث تناسب، "
                 "دون إقحام):"]
        if styles:
            lines.append("- التزم بالأسلوب المطلوب: " + "؛ ".join(styles) + ".")
        if contents:
            lines.append("- احرص على تغطية ما يناسب هذا القسم مِن: "
                         + "؛ ".join(contents) + ".")
        if want_table:
            lines.append(
                "- الجداول مطلوبةٌ بنصّ المستخدم: «" + str(want_table) + "». "
                "فحيث يناسب محتوى هذا القسم هذا الوصف بالتحديد، اعرضه في جدولٍ "
                "بصيغة ماركداون (| … | … |) تكون أعمدته مطابقةً لما طُلب "
                "(لا جدول تصنيفٍ أو مقارنةٍ عامّاً بدلاً منه)."
                if isinstance(want_table, str) else
                "- حين يكون محتوى هذا القسم مقارنةً أو مجموعةَ مصطلحاتٍ/قيَم، "
                "اعرضه في جدولٍ بصيغة ماركداون (| … | … |) بدل السرد.")
        return "\n".join(lines)

    def _intent_router(self, request):
        """UNDERSTANDING FIRST: ask the connected model to read the user's own
        current request and return a structured intent — instead of matching our
        keyword lists. This is what lets any phrasing (and combinations, and
        counts like "3 مباحث لكل منها 3 مطالب") be understood without hand-coding
        a trigger for each. Returns a normalized dict, or None when the model is
        unavailable or its reply is unusable (then the keyword detectors stand in
        as a fallback). Classification only — it never writes or executes."""
        return classify_intent(request, self.llm_fn, self.system_main)

    @staticmethod
    def _normalize_intent(d):
        """Clean/validate the router's JSON into safe types."""
        def _int(v):
            try:
                n = int(v)
                return n if 1 <= n <= 1000 else None
            except (TypeError, ValueError):
                return None
        out = {}
        act = str(d.get("action", "") or "").lower().strip()
        out["action"] = act if act in (
            "research", "rewrite", "summarize", "translate", "convert",
            "edit", "chat") else None
        out["on_previous"] = bool(d.get("on_previous"))
        sc = d.get("scopes") or []
        if isinstance(sc, str):
            sc = [sc]
        out["scopes"] = [s for s in (str(x).lower().strip() for x in sc)
                         if s in ("references", "outline", "plan", "part")]
        fmt = str(d.get("format", "") or "").lower().strip()
        out["format"] = fmt if fmt in (
            "docx", "pdf", "pptx", "xlsx", "csv", "txt", "html",
            "inline") else None
        out["mabhath_count"] = _int(d.get("mabhath_count"))
        out["matlab_count"] = _int(d.get("matlab_count"))
        out["slide_count"] = _int(d.get("slide_count"))
        out["words"] = _int(d.get("words"))
        out["pages"] = _int(d.get("pages"))
        lang = str(d.get("language", "") or "").lower().strip()
        out["language"] = lang if lang in ("ar", "en") else None
        out["wants_table"] = bool(d.get("wants_table"))
        out["wants_chart"] = bool(d.get("wants_chart"))
        out["wants_data"] = bool(d.get("wants_data"))
        # TRI-STATE (True / False / None): does the answer genuinely need EXTERNAL
        # sources (web/academic search)? None = the model didn't say, so behaviour
        # is unchanged (never coerce a missing key to False — that would strip
        # search from real research). Only an EXPLICIT boolean is honoured.
        _ns = d.get("needs_sources", None)
        if isinstance(_ns, bool):
            out["needs_sources"] = _ns
        elif isinstance(_ns, str) and _ns.strip().lower() in (
                "true", "false", "yes", "no", "1", "0"):
            out["needs_sources"] = _ns.strip().lower() in ("true", "yes", "1")
        else:
            out["needs_sources"] = None
        return out

    @staticmethod
    def _as_int(v, default=None):
        """Robustly coerce a model-provided value to an int. Handles ranges
        ("5-8" → 5), floats, and stray text — the model may return a range or
        words where a number is expected, and a bare int() would crash. Returns
        `default` when no digit is found."""
        if isinstance(v, bool):
            return default
        if isinstance(v, int):
            return v
        if isinstance(v, float):
            return int(v)
        try:
            import re
            m = re.search(r'\d+', str(v))
            return int(m.group(0)) if m else default
        except Exception:
            return default

    @staticmethod
    def _counted_structure(lang, n_mabhath, m_matlab):
        """Build a plan of EXACTLY n مباحث, each with m مطالب, plus intro /
        conclusion / references. Abstract labels here get descriptive names
        later by _descriptive_titles. Honors an explicit "N مباحث × M مطالب"."""
        n_mabhath = max(1, min(WeaverOrchestrator._as_int(n_mabhath, 1) or 1, 30))
        m_matlab = max(0, min(WeaverOrchestrator._as_int(m_matlab, 0) or 0, 20))
        mab = "المبحث" if lang == "ar" else "Section"
        mat = "المطلب" if lang == "ar" else "Subsection"
        secs = [{"key": "intro",
                 "title": "المقدمة" if lang == "ar" else "Introduction",
                 "level": 1}]
        for i in range(1, n_mabhath + 1):
            secs.append({"key": "body", "title": f"{mab} {i}", "level": 1})
            for j in range(1, m_matlab + 1):
                secs.append({"key": "body", "title": f"{mat} {i}.{j}",
                             "level": 2})
        secs.append({"key": "conclusion",
                     "title": "الخاتمة" if lang == "ar" else "Conclusion",
                     "level": 1})
        secs.append({"key": "references",
                     "title": "قائمة المراجع" if lang == "ar" else "References",
                     "level": 1})
        return secs

    @staticmethod
    def _proposal_sections(lang):
        """The standard sections of a research proposal (خطة بحثية)."""
        if lang == "ar":
            titles = ["مشكلة البحث", "أسئلة البحث", "أهداف البحث", "أهمية البحث",
                      "فرضيات البحث", "منهج البحث وأدواته", "حدود البحث",
                      "مصطلحات البحث", "الدراسات السابقة", "الهيكل المقترح للبحث"]
        else:
            titles = ["Research Problem", "Research Questions", "Objectives",
                      "Significance", "Hypotheses", "Methodology and Tools",
                      "Scope and Limitations", "Key Terms", "Literature Review",
                      "Proposed Structure"]
        return [{"title": t, "level": 1, "key": "proposal"} for t in titles]

    def _format_references_only(self, card, lang):
        """Build a plain numbered references list from the gathered sources."""
        srcs = card.get("sources") or []
        if not srcs:
            return ("لم يُعثر على مراجع/مصادر لهذا الموضوع الآن — جرّب لاحقاً أو "
                    "وسّع الصياغة." if lang == "ar"
                    else "No references/sources were found for this topic.")
        lines, seen, n = [], set(), 1
        for s in srcs:
            url = (s.get("url") or "").strip()
            title = (s.get("title") or url or "").strip()
            if not title or title in seen:
                continue
            seen.add(title)
            auth = ", ".join(s.get("authors") or [])
            year = str(s.get("year") or "").strip()
            doi = (s.get("doi") or "").strip()
            meta = " — ".join(x for x in (auth, year) if x)
            tail = (("doi:" + doi) if doi else url).strip()
            lines.append(f"{n}. {title}"
                         + (f" — {meta}" if meta else "")
                         + (f". {tail}" if tail else "."))
            n += 1
        return "\n".join(lines)

    @classmethod
    def _requested_output_lang(cls, text):
        """Detect an EXPLICIT output-language directive in the request. Returns
        ("source", None) for the content's own/original language, ("name", <lang>)
        when a language is named, or (None, None) when unspecified. Substring
        match on a space-padded, lowercased copy so word forms are tolerant."""
        t = " " + (text or "").lower() + " "
        if any(k in t for k in cls._LANG_SOURCE):
            return ("source", None)
        for lang, kws in cls._LANG_NAMED:
            if any(k in t for k in kws):
                return ("name", lang)
        return (None, None)

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
    def _requested_format(text):
        """Detect an EXPLICIT output format in the request (Word/PDF/PowerPoint/
        Excel/HTML/Text/Markdown) — broad natural phrasings. None otherwise."""
        t = " " + (text or "").lower() + " "
        if any(k in t for k in (
                "بوربوينت", "باوربوينت", "بوربوينت", "باور بوينت", "بور بوينت",
                "powerpoint", "power point", "pptx", "ppt ", "عرض تقديمي",
                "عرض بوربوينت", "شرائح", "شريحة", "بريزنتيشن", " slides",
                " presentation", "deck")):
            return "PPTX"
        if any(k in t for k in (
                " csv", ".csv", "ملف csv", "سي اس في", "قيم مفصولة بفواصل",
                "comma separated", "comma-separated")):
            return "CSV"
        if any(k in t for k in (
                "اكسل", "إكسل", "اكسيل", "excel", "xlsx", "xls ", "جدول بيانات",
                "جدول اكسل", "شيت", "spreadsheet", "sheet")):
            return "XLSX"
        if any(k in t for k in (
                " html", " htm ", "اتش تي ام ال", "صفحة ويب", "صفحة انترنت",
                "صفحه ويب", "webpage", "web page", "html file")):
            return "HTML"
        if any(k in t for k in (
                " pdf", "pdf ", "بي دي اف", "بيدياف", "بي دي إف", "ملف pdf")):
            return "PDF"
        if any(k in t for k in (
                "وورد", "word", "docx", "doc ", "ملف وورد", "مستند وورد",
                "مايكروسوفت وورد", "ورد ", "word document")):
            return "DOCX"
        if any(k in t for k in (
                "ملف نصي", "ملف نصّي", "نص عادي", "نصي فقط", "txt", ".txt",
                "text file", "plain text", "as text")):
            return "TXT"
        if any(k in t for k in (
                "ماركداون", "ماركدوان", "markdown", ".md", " md ", "نص فقط")):
            return "INLINE"
        return None

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

    @staticmethod
    def _model_strength() -> str:
        """Estimate the running model's strength — "small" | "medium" | "large".

        Order: an explicit override (WEAVER_MODEL_STRENGTH) wins; otherwise the
        model NAME (WEAVER_MODEL) is matched against size hints. Purpose: let
        every layer adapt depth/temperature/length to the model's ceiling so a
        small model works reliably at its own peak, and a large one is used to
        its full depth — without changing any skill. Unknown → "medium"."""
        import os as _os
        ov = (_os.environ.get("WEAVER_MODEL_STRENGTH", "") or "").strip().lower()
        if ov in ("small", "weak", "low", "tiny", "ضعيف", "صغير"):
            return "small"
        if ov in ("medium", "mid", "متوسط"):
            return "medium"
        if ov in ("large", "strong", "high", "big", "كبير", "قوي"):
            return "large"
        name = (_os.environ.get("WEAVER_MODEL", "") or "").lower()
        large_kw = ("opus", "ultra", "pro", "70b", "72b", "65b", "405b", "110b",
                    "large", "huge", "32b", "34b", "-max", "gpt-4o", "gpt-4.1",
                    "o1", "o3", "sonnet-4", "sonnet-5", "opus-5")
        small_kw = ("flash", "mini", "nano", "lite", "tiny", "small", "0.5b",
                    "1b", "1.5b", "2b", "3b", "4b", "7b", "8b", "9b", "haiku")
        # a small/flash/mini variant is small even inside a large family
        # (e.g. gpt-4o-mini, gemini-flash) → check the small hints first.
        # BUT a "flash"/"mini" of a CURRENT generation is not a weak model:
        # deepseek-v4-flash was being told "النموذج محدود الطاقة… الدقّة أهمّ من
        # الطول" on every section, capping the quality of a capable model. A
        # small hint carried by a modern version marker means "fast variant",
        # not "weak", so it lands on medium rather than small.
        if any(k in name for k in small_kw):
            import re as _re
            _modern = _re.search(r'(?:^|[^0-9a-z])v?([4-9])(?:[._-]|$)', name)
            _param = any(k in name for k in ("0.5b", "1b", "1.5b", "2b", "3b",
                                             "4b", "7b", "8b", "9b"))
            if _modern and not _param:
                return "medium"
            return "small"
        if any(k in name for k in large_kw):
            return "large"
        return "medium"

    @staticmethod
    def _strength_profile(strength: str) -> dict:
        """Per-strength writing profile: model temperature, target words for a
        specialized intro, and a depth directive appended to the generic section
        prompt. Adapts OUTPUT to the model ceiling — never fabricates capability
        a small model lacks; it raises the reliable floor and unlocks depth on a
        capable model. Returns a dict always usable (unknown → medium)."""
        s = (strength or "medium").lower()
        if s == "small":
            return {
                "temp": 0.35,
                "intro_words": 220,
                "depth": (
                    "النموذج محدود الطاقة: اكتب بجُملٍ قصيرة واضحة ومباشرة، وركّز "
                    "على النقاط الجوهرية دون حشوٍ أو استطراد، ورتّب الأفكار في "
                    "فقراتٍ قصيرة. الدقّة والوضوح والالتزام بالمصادر أهمّ من الطول "
                    "(استهدف نحو 180–260 كلمة لهذا القسم)."),
                "depth_en": (
                    "The model has limited capacity: write short, clear, direct "
                    "sentences; focus on the essential points with no padding; "
                    "keep paragraphs short. Accuracy, clarity and staying on "
                    "sources matter more than length (aim ~180–260 words)."),
            }
        if s == "large":
            return {
                "temp": 0.6,
                "intro_words": 650,
                "depth": (
                    "استغلّ طاقة النموذج الكاملة: حلّل بعمق، واعرض وجهات النظر "
                    "المختلفة، واربط الأفكار ببعضها بنقدٍ علميّ وأمثلةٍ دقيقة، مع "
                    "التزامٍ صارمٍ بالمصادر (استهدف نحو 500–800 كلمة لهذا القسم)."),
                "depth_en": (
                    "Use the model's full capacity: analyze in depth, present "
                    "differing viewpoints, and connect ideas with scholarly "
                    "critique and precise examples, strictly grounded in the "
                    "sources (aim ~500–800 words)."),
            }
        return {"temp": 0.5, "intro_words": 400, "depth": "", "depth_en": ""}

    @staticmethod
    def _section_kind(title: str):
        """Classify a section title into a purpose-built writer kind:
        "intro" | "conclusion" | "results" | None (→ generic writer)."""
        t = (title or "").strip().lower()
        if not t:
            return None
        intro_kw = ("مقدمة", "المقدمة", "تمهيد", "introduction", "intro")
        concl_kw = ("خاتمة", "الخاتمة", "خلاصة", "الخلاصة", "استنتاج",
                    "الاستنتاجات", "التوصيات", "توصيات", "conclusion",
                    "recommendation", "closing")
        res_kw = ("النتائج", "نتائج", "تحليل النتائج", "عرض النتائج",
                  "results", "findings")
        if any(k in t for k in intro_kw):
            return "intro"
        if any(k in t for k in concl_kw):
            return "conclusion"
        if any(k in t for k in res_kw):
            return "results"
        return None

    @staticmethod
    def _apa_key(s):
        """An APA-style in-text key for a source: "المؤلف، 2024". Falls back to
        a SHORT title fragment (never the full title) and finally to the year
        alone. This is what the section writers put between brackets, so a bad
        key turns into a citation that swallows a whole sentence."""
        if not isinstance(s, dict):
            return str(s)[:40]
        year = str(s.get("year") or "").strip()
        a = s.get("author") or s.get("authors")
        _many = False
        if isinstance(a, (list, tuple)):
            a = [str(x).strip() for x in a if str(x).strip()]
            _many = len(a) > 1
            a = a[0] if a else ""
        a = (str(a).strip() if a else "")
        if a:
            # APA cites the SURNAME only. Sources store "اللقب، الاسم الأول",
            # so passing the whole field produced "(المطيري، علياء زيد، 2022)" —
            # three commas and a given name inside an in-text citation.
            _sur = a.replace("،", ",").split(",")[0].strip() or a
            if _many:
                _sur += " وآخرون"
            return f"{_sur}، {year}" if year else _sur
        t = (s.get("title") or s.get("key") or "").strip()
        t = " ".join(t.split()[:4])            # keep it short, never a full title
        if t:
            return f"{t}، {year}" if year else t
        return year or "مصدر"

    @staticmethod
    def _conclusion_parts(card, lang="ar"):
        """Which conclusion sub-sections to write. Reads the REQUIREMENTS
        checklist the model extracted (plus the request text) and returns the
        headings to keep, or None to keep the default four. A summary and an
        answer to the research question always belong in a conclusion;
        recommendations and future-research are added ONLY when asked for."""
        base_ar = ["ملخص النتائج", "الإجابة على سؤال البحث"]
        base_en = ["Summary of Findings", "Answer to the Research Question"]
        rec_ar, fut_ar = "التوصيات", "مقترحات للبحوث المستقبلية"
        rec_en, fut_en = "Recommendations", "Future Research"
        card = card or {}
        blob = " ".join([
            str(card.get("topic") or ""),
            " ".join(str(r.get("text", "")) for r in (card.get("requirements")
                                                      or [])
                     if isinstance(r, dict)),
        ]).lower()
        if not blob.strip():
            return None                    # no signal → unchanged behaviour
        want_rec = any(k in blob for k in ("توصيات", "توصية",
                                           "recommend"))
        want_fut = any(k in blob for k in ("مقترحات", "بحوث مستقبلية",
                                           "دراسات مستقبلية", "future research",
                                           "further research"))
        keep = list(base_en if lang == "en" else base_ar)
        if want_rec:
            keep.append(rec_en if lang == "en" else rec_ar)
        if want_fut:
            keep.append(fut_en if lang == "en" else fut_ar)
        return keep

    def _write_section_specialized(self, title, card, lang, mode, no_ctx,
                                   prior_sections, prof):
        """Route a section to its purpose-built writer skill when the section
        type AND sourcing mode fit, returning prose text — or None to let the
        generic writer handle it. Purely additive: every skill call is guarded
        by the caller, so any miss falls back to the existing generic path.

        Bindings (skills already present, only wired here):
          intro       → research_intro.build_intro
          conclusion  → conclusion_writer.build_conclusion
          results     → results_formatter.format_results (also uses table_builder)
        """
        if not self.llm_fn:
            return None
        kind = self._section_kind(title)
        if not kind:
            return None
        topic = card.get("topic", "") or title
        if kind == "intro" and mode == "cited" and not no_ctx:
            refs = []
            for s in (card.get("sources") or [])[:12]:
                if isinstance(s, dict):
                    refs.append({
                        "key": self._apa_key(s),
                        "text": (s.get("content") or s.get("title", "") or "")[:160],
                        "page": s.get("page", "")})
            out = self._skill_call(
                "research_intro", "build_intro", "build_intro",
                topic, refs, int(prof.get("intro_words", 400)), lang, self.llm_fn)
            return (out or {}).get("text") or None
        if kind == "conclusion" and mode != "none":
            findings = []
            for sec in (prior_sections or [])[-8:]:
                b = (sec.get("body") or "").strip()
                if b:
                    first = b.split("\n", 1)[0].strip()[:200]
                    if first:
                        findings.append(first)
            # non-standard closing: hand the specialized conclusion writer the
            # style director's closing directive (guarded + toggleable). None →
            # unchanged behaviour.
            _hint = None
            if os.environ.get("WEAVER_STYLE_DIRECTOR", "1").strip().lower() \
                    not in ("0", "false", "off", "no"):
                try:
                    _hint = self._skill_call(
                        "style_director", "style_directives",
                        "conclusion_directive", lang)
                except Exception:
                    _hint = None
            # Only write the conclusion parts the user actually asked for.
            # All four ("ملخص النتائج"/"الإجابة"/"التوصيات"/"مقترحات") used to be
            # imposed on every document, which is why recommendations and future
            # research showed up unrequested (and twice).
            _inc = None
            try:
                _inc = self._conclusion_parts(card, lang)
            except Exception:
                _inc = None
            out = self._skill_call(
                "conclusion_writer", "build_conclusion", "build_conclusion",
                topic, findings, lang, self.llm_fn, _hint, _inc)
            return (out or {}).get("text") or None
        if kind == "results" and mode != "none":
            out = self._skill_call(
                "results_formatter", "format_results", "format_results",
                [{"title": title, "note": ""}], lang, self.llm_fn)
            return (out or {}).get("text") or None
        return None

    # ── task.skills dispatch ─────────────────────────────────────────────────
    # _route() matches skills to the task; this turns that match into real
    # execution. A skill runs ONLY when the task actually selected it (its name
    # is in task.skills), keeping behaviour targeted. Skills already invoked at
    # a fixed point (structure/methodology/rewriters/formatters/builders and the
    # per-section writers above) are NOT re-run here — this dispatch adds the
    # remaining enrichment skills that had no wiring. Every handler is guarded,
    # idempotent, and additive; on any miss the draft is left unchanged.
    def _skill_handlers(self):
        """skill name → write-stage handler(self, task, card, lang, mem)->bool.
        A skill absent here is either wired elsewhere (a fixed layer point) or
        context-gated for a later increment; its match is simply skipped."""
        return {
            "literature_review": self._sk_literature_review,
        }

    def _dispatch_skills(self, task: Task, card: dict, lang: str, mem):
        """Run the matched skills (task.skills) that have a write-stage handler.
        Guarded per skill; a failure never breaks the draft."""
        handlers = self._skill_handlers()
        for name in list(task.skills or []):
            h = handlers.get(name)
            if not h:
                continue
            try:
                if h(task, card, lang, mem):
                    mem.set_status(6, f"مهارة موزّعة: {name} ✓")
            except Exception as e:
                mem.set_status(6, f"مهارة {name} (تخطّي: {e})")

    @staticmethod
    def _is_literature_title(title: str) -> bool:
        t = (title or "").strip().lower()
        return any(k in t for k in (
            "الدراسات السابقة", "دراسات سابقة", "أدبيات", "الأدبيات",
            "الإطار النظري", "مراجعة الأدبيات", "literature", "related work",
            "prior work", "background"))

    def _sk_literature_review(self, task: Task, card: dict, lang: str,
                              mem) -> bool:
        """Enrich an EXISTING literature/theoretical-framework section with a
        theme-organized view of the gathered sources (organize_by_theme). Never
        invents a section: if no literature section was written, it does nothing.
        Additive — appends beneath the section's current body."""
        sources = [s for s in (card.get("sources") or []) if isinstance(s, dict)]
        if len(sources) < 2 or not task.sections:
            return False
        lit_idx = next((i for i, s in enumerate(task.sections)
                        if self._is_literature_title(s.get("heading", ""))), None)
        if lit_idx is None:
            return False
        refs = [{"key": s.get("key") or (s.get("title", "") or "")[:40],
                 "text": (s.get("content") or s.get("title", "") or "")}
                for s in sources]
        groups = self._skill_call("literature_review", "organize_by_theme",
                                  "organize_by_theme", refs, None) or {}
        lines = []
        for theme, items in groups.items():
            if theme == "unclassified" or not items:
                continue
            keys = "؛ ".join((it.get("key") or "")[:60] for it in items[:6]) \
                if lang == "ar" else \
                "; ".join((it.get("key") or "")[:60] for it in items[:6])
            lines.append(f"- **{theme}**: {keys}")
        if not lines:
            return False
        header = ("\n\n**تنظيم الدراسات موضوعياً:**\n" if lang == "ar"
                  else "\n\n**Thematic grouping of studies:**\n")
        cur = task.sections[lit_idx].get("body", "") or ""
        task.sections[lit_idx]["body"] = cur + header + "\n".join(lines)
        # rebuild the chat/preview draft to reflect the enriched section
        task.draft = "\n\n".join(
            (f"{s.get('heading', '')}\n{s.get('body', '')}").strip()
            for s in task.sections if (s.get("heading") or s.get("body")))
        return True

    # ── statistical_analysis: real stats when a data file is attached ─────────
    @staticmethod
    def _data_files(task: Task):
        """Attached data files (csv/xlsx/xls) the stats skill can analyze."""
        exts = (".csv", ".xlsx", ".xls")
        return [f for f in (task.input_files or [])
                if isinstance(f, str) and f.lower().endswith(exts)]

    @staticmethod
    def _format_statistics(res, lang: str):
        """Render analyze()'s REAL computed numbers as a Markdown block
        (descriptives table + reliability + an honest 'computed, not estimated'
        note). Returns None on error/empty so nothing fake is ever injected."""
        if not isinstance(res, dict) or res.get("error"):
            return None
        dd = (res.get("descriptives") or {})
        desc = dd.get("descriptives") or {}
        n = dd.get("n") or res.get("n")
        if not desc:
            return None
        cols = list(desc.keys())
        order = ["count", "mean", "std", "min", "25%", "50%", "75%", "max"]
        first = desc[cols[0]] if cols else {}
        stats = [k for k in order if k in first] or list(first.keys())
        labels_ar = {"count": "العدد", "mean": "المتوسط",
                     "std": "الانحراف المعياري", "min": "الأدنى",
                     "25%": "الربيع الأول", "50%": "الوسيط",
                     "75%": "الربيع الثالث", "max": "الأعلى"}

        def _fmt(v):
            try:
                return str(round(float(v), 3))
            except Exception:
                return str(v)
        head_stat = "الإحصاء" if lang == "ar" else "Statistic"
        rows = ["| " + head_stat + " | " + " | ".join(str(c) for c in cols) + " |",
                "|" + "---|" * (len(cols) + 1)]
        for st in stats:
            label = labels_ar.get(st, st) if lang == "ar" else st
            rows.append("| " + " | ".join(
                [label] + [_fmt(desc[c].get(st, "")) for c in cols]) + " |")
        out = []
        out.append(("حجم العينة: %s. الإحصاءات الوصفية للمتغيّرات العددية:" % n)
                   if lang == "ar" else
                   ("Sample size: %s. Descriptive statistics for numeric "
                    "variables:" % n))
        out.append("\n".join(rows))
        rel = res.get("reliability")
        if isinstance(rel, dict) and "cronbach_alpha" in rel:
            out.append(
                ("**ثبات المقياس (كرونباخ ألفا):** %s (%s عبارة، ن=%s) — %s."
                 % (rel.get("cronbach_alpha"), rel.get("n_items", ""),
                    rel.get("n", ""), rel.get("interpretation", "")))
                if lang == "ar" else
                ("**Reliability (Cronbach's α):** %s (%s items, n=%s) — %s."
                 % (rel.get("cronbach_alpha"), rel.get("n_items", ""),
                    rel.get("n", ""), rel.get("interpretation", ""))))
        out.append("_" + ("الأرقام أعلاه محسوبة فعلياً من الملف المرفق، لم "
                          "تُقدَّر أو تُختلق." if lang == "ar" else
                          "The figures above are computed directly from the "
                          "attached file, not estimated.") + "_")
        return "\n\n".join(out)

    def _inject_statistics(self, task: Task, card: dict, lang: str, mem):
        """When a data file is attached, run statistical_analysis.analyze on it
        and inject the REAL computed results into the document — into a results
        section if one exists, else as its own 'التحليل الإحصائي' section. Never
        fabricates numbers: on a library/read error it adds an honest note only.
        Additive and fully guarded."""
        files = self._data_files(task)
        if not files:
            return
        path = files[0]
        try:
            res = self._skill_call("statistical_analysis", "survey_analysis",
                                   "analyze", path)
            # add scale reliability when Likert-type items are detected
            vt = (res or {}).get("variable_types") or {}
            likert = [c for c, t in vt.items()
                      if "likert" in str(t).lower() or "ليكرت" in str(t)]
            if isinstance(res, dict) and "error" not in res and len(likert) >= 2:
                res2 = self._skill_call("statistical_analysis",
                                        "survey_analysis", "analyze", path,
                                        likert)
                if isinstance(res2, dict) and "error" not in res2:
                    res = res2
        except Exception as e:
            mem.set_status(6, f"إحصاء (تخطّي: {e})")
            return
        card["statistics"] = res
        block = self._format_statistics(res, lang)
        head = "التحليل الإحصائي" if lang == "ar" else "Statistical Analysis"
        if not block:
            # honest, actionable note — never fake numbers
            err = res.get("error") if isinstance(res, dict) else "unknown"
            block = (("تعذّر تنفيذ التحليل الإحصائي على الملف المرفق: %s. "
                      "قد تحتاج تثبيت المكتبات: pip install pandas scipy." % err)
                     if lang == "ar" else
                     ("Could not run the statistical analysis on the attached "
                      "file: %s. You may need: pip install pandas scipy." % err))
        idx = next((i for i, s in enumerate(task.sections or [])
                    if self._section_kind(s.get("heading", "")) == "results"),
                   None)
        if idx is not None:
            cur = task.sections[idx].get("body", "") or ""
            sub = ("\n\n**التحليل الإحصائي:**\n\n" if lang == "ar"
                   else "\n\n**Statistical analysis:**\n\n")
            task.sections[idx]["body"] = cur + sub + block
        else:
            task.sections = (task.sections or []) + [{"heading": head,
                                                      "body": block}]
        task.draft = "\n\n".join(
            (f"{s.get('heading', '')}\n{s.get('body', '')}").strip()
            for s in task.sections if (s.get("heading") or s.get("body")))
        mem.set_status(6, "أُدرج التحليل الإحصائي (أرقام محسوبة فعلياً)")

    # ── quran_hadith_citation: correct marks for Islamic content ─────────────
    @staticmethod
    def _is_islamic_content(text: str) -> bool:
        """True when the text quotes/discusses Quran or Hadith (so the marks
        skill should enforce ﴿ ﴾ for verses and « » for hadith)."""
        t = text or ""
        kw = ("قال الله", "قال تعالى", "يقول الله", "سبحانه وتعالى", "عز وجل",
              "قال رسول الله", "قال النبي", "عن النبي", "صلى الله عليه وسلم",
              "ﷺ", "رواه البخاري", "رواه مسلم", "حديث شريف", "الحديث الشريف",
              "القرآن", "قرآن كريم", "آية كريمة", "الآية الكريمة",
              "﴾", "«", "السنة النبوية", "السيرة النبوية")
        return any(k in t for k in kw)

    # the writing directive appended for Islamic content (skill's conventions)
    _ISLAMIC_DIRECTIVE_AR = (
        "عند الاستشهاد بآية قرآنية: ضعها بين قوسي الآية ﴿ ﴾ (لا أقواس عادية ولا "
        "علامات اقتباس) وأتبِعها بالمصدر (السورة: رقم الآية). وعند الاستشهاد بحديث "
        "نبوي: ضعه بين علامتي « » (لا أقواس الآية) وأتبِعه بالتخريج (رواه فلان، "
        "الحكم). لا تخلط بين العلامتين إطلاقاً.")
    _ISLAMIC_DIRECTIVE_EN = (
        "When quoting a Quranic verse, enclose it in the ornamental brackets "
        "﴿ ﴾ (never normal quotes/parentheses) and follow it with (Surah: Ayah). "
        "When quoting a hadith, enclose it in « » (never the Quran brackets) and "
        "follow it with its takhrij. Never mix the two marks.")

    def _apply_islamic_marks(self, task: Task, card: dict, lang: str, mem):
        """For Islamic content, enforce the skill's marks at the TEXT level so
        every export format is correct: a verse introduced by an explicit Quran
        lead-in gets ﴿ ﴾, a hadith introduced by an explicit lead-in gets « ».
        ONLY the delimiter marks are changed — the quoted text itself is kept
        verbatim (never rewritten). Then the skill's validate_marks flags any
        remaining misuse. Additive, guarded, and a no-op for non-Islamic text.

        Note: this normalizes the MARKS across all formats; the skill's richer
        Word styling (bold verse, Kufyan font) via add_quran_verse/add_hadith
        needs a docx object and stays a later, docx-only step."""
        import re
        sections = task.sections or []
        joined = "\n".join((s.get("body", "") or "") for s in sections) \
            or (task.draft or "")
        if not self._is_islamic_content(joined + " " + str(card.get("topic", ""))):
            return
        # wire to the skill module: real marks + validator (no docx needed here)
        try:
            import importlib, sys as _sys, os as _os
            sp = _os.path.abspath(_os.path.join(
                _os.path.dirname(__file__), "..", "capabilities", "skills",
                "quran_hadith_citation", "scripts"))
            if sp not in _sys.path:
                _sys.path.insert(0, sp)
            qh = importlib.import_module("quran_hadith")
        except Exception as e:
            mem.set_status(6, f"تنسيق إسلامي (تخطّي: {e})")
            return
        QO, QC = qh.QURAN_OPEN, qh.QURAN_CLOSE
        HO, HC = qh.HADITH_OPEN, qh.HADITH_CLOSE
        q = '["“”]'      # straight or curly double quotes
        qlead = (r'(?:قال\s+الله\s+تعالى|قال\s+تعالى|قال\s+الله|'
                 r'يقول\s+الله(?:\s+تعالى)?|قال\s+عز\s+وجل)')
        hlead = (r'(?:قال\s+رسول\s+الله(?:\s*ﷺ|\s*صلى\s+الله\s+عليه\s+وسلم)?|'
                 r'قال\s+النبي(?:\s*ﷺ|\s*صلى\s+الله\s+عليه\s+وسلم)?|عن\s+النبي)')
        q_re = re.compile(r'(' + qlead + r'\s*[:：]?\s*)' + q +
                          r'([^"“”\n]{3,300})' + q)
        h_re = re.compile(r'(' + hlead + r'\s*[:：]?\s*)' + q +
                          r'([^"“”\n]{3,400})' + q)

        def _norm(txt):
            txt = q_re.sub(
                lambda m: f'{m.group(1)}{QO} {m.group(2).strip()} {QC}', txt)
            txt = h_re.sub(
                lambda m: f'{m.group(1)}{HO} {m.group(2).strip()} {HC}', txt)
            return txt

        changed = 0
        for s in sections:
            b = s.get("body", "") or ""
            nb = _norm(b)
            if nb != b:
                s["body"] = nb
                changed += 1
        if changed:
            task.draft = "\n\n".join(
                (f"{s.get('heading', '')}\n{s.get('body', '')}").strip()
                for s in sections if (s.get("heading") or s.get("body")))
        elif task.draft:
            task.draft = _norm(task.draft)
        # validate remaining marks (skill's own check) and record honestly
        try:
            v = qh.validate_marks(task.draft or joined) or {}
        except Exception:
            v = {}
        card["islamic_marks"] = v
        if v.get("warnings"):
            mem.set_status(6, "تنسيق إسلامي: " + "؛ ".join(v["warnings"]))
        else:
            mem.set_status(6, f"تنسيق إسلامي: علامات مضبوطة ({changed} تصحيح)")

    def _style_islamic_docx(self, path, card):
        """Post-pass on the built .docx: embolden Quran verses (﴿…﴾) and hadith
        («…») using the quran_hadith_citation skill's own _set_run, preserving
        the surrounding paragraph font/size. Touches only paragraphs that carry
        a complete mark span. Fully guarded — any failure (no python-docx, read
        error) leaves the file exactly as built. No-op for non-Islamic docs.

        This is the richer Word-only step the text-level _apply_islamic_marks
        deferred: marks are already correct in every format; here the verse and
        matn also become bold, per the skill's typographic rule."""
        if not card.get("islamic"):
            return
        try:
            import importlib, sys as _sys, os as _os, re as _re
            sp = _os.path.abspath(_os.path.join(
                _os.path.dirname(__file__), "..", "capabilities", "skills",
                "quran_hadith_citation", "scripts"))
            if sp not in _sys.path:
                _sys.path.insert(0, sp)
            qh = importlib.import_module("quran_hadith")
            from docx import Document
        except Exception:
            return
        QO, QC = qh.QURAN_OPEN, qh.QURAN_CLOSE
        HO, HC = qh.HADITH_OPEN, qh.HADITH_CLOSE
        span_re = _re.compile(
            "(" + _re.escape(QO) + ".*?" + _re.escape(QC) + "|"
            + _re.escape(HO) + ".*?" + _re.escape(HC) + ")")

        def _is_span(seg):
            return ((seg.startswith(QO) and seg.endswith(QC))
                    or (seg.startswith(HO) and seg.endswith(HC)))
        try:
            doc = Document(path)
        except Exception:
            return
        changed = False
        for p in doc.paragraphs:
            txt = p.text
            if not span_re.search(txt):
                continue
            base = p.runs[0] if p.runs else None
            base_font = base.font.name if base else None
            base_size = base.font.size if base else None
            for r in list(p.runs):
                r._element.getparent().remove(r._element)
            for seg in span_re.split(txt):
                if not seg:
                    continue
                run = p.add_run(seg)
                if _is_span(seg):
                    qh._set_run(run, bold=True,
                                font=(base_font or "Kufyan Arabic"))
                else:
                    if base_font:
                        run.font.name = base_font
                if base_size:
                    run.font.size = base_size
            changed = True
        if changed:
            try:
                doc.save(path)
            except Exception:
                pass

    def _route(self, task: Task):
        """Phase 3: from the understood task_card, compute ONCE the tools &
        skills the task needs, so later layers act only on what's required
        (each tool/skill invoked only when needed — no overlap)."""
        card = task.task_card
        of = card.get("output_format", [])
        of = of if isinstance(of, list) else [of]
        text = f"{card.get('topic','')} " \
               f"{self._strip_injected_memory(task.description)} " \
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
        # genuinely academic tasks also gather peer-reviewed sources (free
        # scholarly APIs). Not for "none" mode, and not for news/recency.
        acad_types = ("بحث", "research", "دراسة", "أطروحة", "thesis",
                      "مراجعة أدبيات", "literature review", "رسالة علمية",
                      "dissertation")
        if mode != "none" and (
                card.get("needs_academic_search")
                or str(card.get("task_type", "")).lower() in acad_types):
            task.tools.append("academic_search")
        # news/recency intent enables web_search even for non-academic tasks
        # (never academic_search — news isn't academic). Respect "none" mode below.
        if mode != "none" and self._is_recency_query(
                f"{card.get('topic','')} "
                f"{self._strip_injected_memory(task.description)}"):
            task.tools.append("web_search")
        if mode == "none":
            # explicit no-sources request: strip every source-gathering tool
            task.tools = [t for t in task.tools
                          if t not in ("web_search", "academic_search")]
            card.pop("needs_academic_search", None)
        task.tools = list(dict.fromkeys(task.tools))   # dedupe, keep order
        task.skills = list(dict.fromkeys(task.skills))
        self._dedupe_tools(task)                        # collapse redundant tools

    # canonical provider for every registered tool. The pipeline ACTS only on
    # the layer-4 research tools ("active"); every other capability is already
    # served by a skill or by inline code ("skill"/"inline"), and a few have no
    # wired path yet ("inactive"). This map resolves the tool/skill duplication
    # WITHOUT removing any registry entry or file — it only records where each
    # capability really runs so a matched tool is never double-counted as a
    # separate action.
    _TOOL_DELEGATION = {
        # active — consulted by layer 4 as real actions
        "web_search": ("active", None),
        "academic_search": ("active", "_scholarly_search (inline)"),
        "web_extract": ("active", None),
        "web_document": ("active", None),
        "youtube": ("active", None),
        # served by a skill (export/format/scoring) — driven by output_format /
        # the relevant layer, not by task.tools
        "word": ("skill", "docx_builder"),
        "powerpoint": ("skill", "pptx_builder"),
        "excel": ("skill", "xlsx_builder"),
        "pdf": ("skill", "pdf_builder"),
        "doc_export": ("skill", "docx/pdf/pptx/xlsx_builder"),
        "chart": ("skill", "chart_builder"),
        "credibility_check": ("skill", "credibility_scorer"),
        # served by inline code elsewhere
        "doc_read": ("inline", "web.server._extract_bytes + core.ocr"),
        "memory_store": ("inline", "TaskMemory + config/chats"),
        # csv is now a real export format served in _export
        "csv": ("inline", "_export csv branch"),
        # present in the registry but with no wired path yet
        "diagram": ("inactive", None),
        "calendar": ("inactive", None),
        "scheduler": ("inactive", None),
        "mcp_connector": ("inactive", None),
    }

    def _dedupe_tools(self, task: Task):
        """Keep in task.tools only the tools the pipeline actually acts on
        ("active"); record every other matched tool under card['tool_delegation']
        with the skill/inline path that really serves it, then drop it from the
        action list. Unknown tools are kept untouched. Additive and safe: no
        registry entry or tool file is removed."""
        deleg, kept = {}, []
        for t in (task.tools or []):
            d = self._TOOL_DELEGATION.get(t)
            if d is None:
                kept.append(t)                 # unknown → leave as-is
            elif d[0] == "active":
                kept.append(t)
            else:
                deleg[t] = {"via": d[0], "by": d[1]}   # served elsewhere
        task.tools = list(dict.fromkeys(kept))
        if deleg:
            task.task_card["tool_delegation"] = deleg

    # markers of APPENDED context the web layer adds AFTER the real request:
    # cross-chat memory ("[للسياق فقط …]") and its follow-up instruction. These
    # are for the WRITER only — detectors must NEVER read them, or a link/verb
    # recalled from another conversation hijacks the current request.
    _INJECTED_CTX_MARKERS = (
        "[للسياق فقط", "[تعليمة]", "[مهام سابقة", "[سياق مهام",
        "[for context only", "[note]")

    @staticmethod
    def _strip_injected_memory(text):
        """Remove ONLY the appended cross-chat memory / instruction block, while
        keeping the current request and this conversation's own history. Used by
        detectors so recalled content from OTHER chats is never acted upon."""
        t = text or ""
        cut = len(t)
        for m in WeaverOrchestrator._INJECTED_CTX_MARKERS:
            i = t.find(m)
            if i != -1 and i < cut:
                cut = i
        return t[:cut]

    @staticmethod
    def _current_request(text):
        """Return ONLY the current request: drop the threaded history the web
        prefixes as "[سياق المحادثة السابقة] … [الطلب الحالي] …", AND drop any
        appended cross-chat memory block. So a link or verb from an earlier turn
        — or recalled from another conversation — never hijacks the request now
        (e.g. "لخّص ما عملناه" must not re-summarize an old video, and asking for
        an outline must not turn into transcribing a video from memory)."""
        t = text or ""
        if "[الطلب الحالي]" in t:
            t = t.rsplit("[الطلب الحالي]", 1)[-1]
        return WeaverOrchestrator._strip_injected_memory(t).strip()

    @staticmethod
    def _conversation_context(text):
        """Return THIS conversation's own prior turns — the web layer's
        "[سياق المحادثة السابقة] … [الطلب الحالي]" block — stripped of any
        appended CROSS-chat memory. Empty when there is no in-conversation
        history. Used to recover the SUBJECT for a follow-up that only adjusts
        the format ("اجعلها 3 مباحث") without naming the topic again — this is
        THIS chat's history, so it is safe context, unlike recalled other-chat
        memory."""
        t = WeaverOrchestrator._strip_injected_memory(text or "")
        if "[سياق المحادثة السابقة]" in t and "[الطلب الحالي]" in t:
            seg = t.split("[سياق المحادثة السابقة]", 1)[1]
            seg = seg.split("[الطلب الحالي]", 1)[0]
            return seg.strip()
        return ""

    @staticmethod
    def _extract_slide_count(text):
        """Extract a requested slide count from the request. None if unstated.
        Feeds design_slides so "اعمل عرض 30 شريحة" honours 30. (tested)"""
        import re
        if not text:
            return None
        patterns = [
            r'(\d{1,3})\s*(?:شريحة|شرائح|slides?|slide)',
            r'(?:شريحة|شرائح|slides?|عرض)\D{0,10}?(\d{1,3})',
            r'(?:عدد|count|number)\D{0,15}?(\d{1,3})',
        ]
        for p in patterns:
            m = re.search(p, text, re.I)
            if m:
                n = int(m.group(1))
                if 1 <= n <= 100:
                    return n
        return None

    @staticmethod
    def extract_length_target(text):
        """→ {'words': int|None, 'pages': int|None} from the request; None if
        unstated. Pages → estimated words (~500 words/academic page) when the
        word count itself isn't given. (tested)"""
        import os as _os, re
        if not text:
            return {"words": None, "pages": None,
                    "max_words": None, "max_pages": None}
        try:
            wpp = int(_os.environ.get("WEAVER_WORDS_PER_PAGE", "300") or 300)
        except Exception:
            wpp = 300
        words = pages = None
        m = re.search(r'(\d{2,6})\s*(?:كلمة|كلمات|words?|word)', text, re.I)
        if m:
            words = int(m.group(1))
        m = re.search(r'(\d{1,4})\s*(?:صفحة|صفحات|pages?|page)', text, re.I)
        if m:
            pages = int(m.group(1))
        # An explicit CEILING ("ولا يزيد عن 12 صفحة" / "at most 12 pages" /
        # a "10-12" range) was never captured, so nothing ever stopped the
        # expansion loop from overshooting it.
        max_pages = max_words = None
        mx = re.search(r'(?:لا\s*يزيد\s*(?:عن|على)|بحد\s*أقصى|حد\s*أقصى|'
                       r'no\s*more\s*than|at\s*most|up\s*to|maximum\s*of)'
                       r'\s*(\d{1,6})\s*(صفحة|صفحات|pages?|page|كلمة|كلمات|words?)?',
                       text, re.I)
        if mx:
            n = int(mx.group(1))
            unit = (mx.group(2) or "").lower()
            if unit.startswith(("كلم", "word")):
                max_words = n
            else:
                max_pages = n
        if max_pages is None and max_words is None:
            rng = re.search(r'(\d{1,4})\s*(?:-|–|إلى|الى|to)\s*(\d{1,4})\s*'
                            r'(?:صفحة|صفحات|pages?|page)', text, re.I)
            if rng:
                pages = int(rng.group(1))       # the LOW end is the minimum
                max_pages = int(rng.group(2))
                words = None                    # recomputed from the low end
        if words is None and pages:
            words = pages * wpp
        if max_words is None and max_pages:
            max_words = max_pages * wpp
        return {"words": words, "pages": pages,
                "max_words": max_words, "max_pages": max_pages}

    @staticmethod
    def count_words(text):
        """Deterministic word count — Arabic + Latin, after light markdown
        stripping. This is arithmetic (len of tokens), never an estimate."""
        import re
        if not text:
            return 0
        clean = re.sub(r'[#*_`>\-]+', ' ', text)
        return len([w for w in clean.split() if any(c.isalnum() for c in w)])

    @staticmethod
    def verify_sections_coverage(required_titles, sections):
        """Return the required titles NOT covered by any written section
        (flexible two-way substring match). (tested)"""
        present = [(s.get("heading") or "").strip() for s in sections
                   if (s.get("heading") or s.get("body"))]
        present_l = [p.lower() for p in present if p]
        joined = " ".join(present_l)
        missing = []
        for req in required_titles:
            r = (req or "").strip().lower()
            if not r:
                continue
            if r in joined:
                continue
            if any(r in p or p in r for p in present_l):
                continue
            missing.append(req)
        return missing

    @staticmethod
    def _detect_youtube_intent(text):
        """Keyword heuristic for what to do with a YouTube link. Returns
        {"mode", "with_timing", "explicit"} where `explicit` is True only when a
        clear transcript/summary signal was found (so the caller can fall back to
        the model for genuinely ambiguous phrasings). Broad synonym lists so most
        natural wordings resolve here without an extra model call."""
        t = " " + (text or "").lower() + " "
        transcript_kw = (
            "فرّغ", "فرغ", "فرّغلي", "فرغلي", "تفريغ", "التفريغ", "فرِّغ",
            "النص الكامل", "النص كامل", "كامل النص", "نص الفيديو", "نصّ الفيديو",
            "النص الحرفي", "النص حرفي", "حرفي", "حرفياً", "حرفيا",
            "كلمة بكلمة", "كلمة كلمة", "انسخ النص", "انسخ الكلام", "انسخ لي النص",
            "اكتب ما قيل", "اكتب ما قِيل", "اكتب النص", "اكتب الكلام", "اكتب كل ما",
            "المحتوى النصي", "سكربت", "السكربت", "سكريبت", "السكريبت",
            "transcribe", "transcript", "full text", "verbatim",
            "word for word", "word-for-word", "captions", "subtitles", "script",
        )
        summary_kw = (
            "لخّص", "لخص", "لخّصلي", "لخصلي", "لخّص لي", "لخص لي", "ملخص", "ملخّص",
            "الملخص", "الملخّص", "اختصر", "اختصار", "باختصار", "أهم النقاط",
            "اهم النقاط", "أهم ما", "اهم ما", "النقاط الرئيسية", "النقاط المهمة",
            "الأفكار الرئيسية", "الافكار الرئيسية", "الخلاصة", "خلاصة", "زبدة",
            "لبّ الموضوع", "لب الموضوع", "عن ماذا يتحدث", "عن ماذا يتكلم",
            "ماذا يقول", "وش يقول", "ايش يقول", "شنو يقول", "فكرة الفيديو",
            "summary", "summarize", "summarise", "tl;dr", "tldr", "key points",
            "main points", "gist", "overview", "in short",
        )
        timing_kw = (
            "مع التوقيت", "مع التوقيتات", "بالتوقيت", "بالتوقيتات", "التوقيت",
            "توقيت", "الطوابع الزمنية", "طوابع زمنية", "الطابع الزمني",
            "الدقائق", "الدقيقة", "الثواني", "بالدقائق", "الوقت لكل",
            "timestamp", "timestamps", "with timing", "with time", "with times",
            "time codes", "timecodes", "time-stamps",
        )
        has_t = any(k in t for k in transcript_kw)
        has_s = any(k in t for k in summary_kw)
        with_timing = any(k in t for k in timing_kw)
        if has_t and has_s:
            mode = "both"
        elif has_t:
            mode = "transcript"
        else:
            mode = "summary"          # summary-only OR ambiguous default
        return {"mode": mode, "with_timing": with_timing,
                "explicit": bool(has_t or has_s)}

    def _classify_youtube_intent_llm(self, text):
        """Ask the model to classify a YouTube request into
        summary / transcript / timing — understands ANY phrasing. Returns
        {"mode", "with_timing"} or None when unavailable or unusable. Used only
        when the keyword heuristic is not decisive, to keep model calls rare."""
        if not self.llm_fn:
            return None
        try:
            from core.llm import extract_json
            prompt = (
                "صنّف طلب المستخدم المتعلّق بفيديو يوتيوب. قد يريد المستخدم: "
                "ملخصاً (summary)، أو تفريغاً حرفياً كاملاً للنص (transcript)، أو "
                "كليهما معاً، وقد يريد طوابع زمنية/توقيتاً (timing). افهم أيّ صياغة "
                "مهما اختلفت اللهجة أو الأسلوب. أعِد JSON فقط بلا أي نص آخر بالشكل:\n"
                '{"summary": true|false, "transcript": true|false, '
                '"timing": true|false}\n\nطلب المستخدم:\n' + (text or "")[:800]
            )
            data = extract_json(self.llm_fn(prompt, system=self.system_main,
                                            temperature=0.0)) or {}
            s = bool(data.get("summary"))
            tr = bool(data.get("transcript"))
            tm = bool(data.get("timing"))
            if not s and not tr:
                return None
            mode = "both" if (s and tr) else ("transcript" if tr else "summary")
            return {"mode": mode, "with_timing": tm}
        except Exception:
            return None

    async def _layer_3(self, task: Task, mem: TaskMemory):
        """٣: الفهم — تحليل المهمة وبناء بطاقتها ثم توجيه الأدوات/المهارات."""
        task.status = TaskStatus.LAYER_3
        mem.set_status(3, "تحليل المهمة")

        # ── YouTube link → dedicated transcript path, BEFORE the model. Builds a
        #    minimal card and returns early, so the video is summarized/
        #    transcribed instead of being treated as a research task (which
        #    produced empty مباحث/مطالب). Fully guarded: any failure, or a link
        #    with no captions, continues the normal path unchanged.
        try:
            import re as _re
            from capabilities.tools import tool_youtube as _yt
            # Look for a YouTube link (and read its intent) in the CURRENT request
            # ONLY — never the threaded conversation history. Otherwise a video
            # linked in an EARLIER turn hijacks an unrelated request now (e.g.
            # "لخّص ما قمنا بعمله في هذه المحادثة" would re-summarize that video
            # instead of the conversation).
            _cur = self._current_request(task.description)
            yurl = None
            for _u in _re.findall(r"https?://\S+", _cur):
                _u = _u.rstrip('.,)"\'،؛')
                if _yt.is_youtube_url(_u):
                    yurl = _u
                    break
            # Follow-up with NO link in the current message but a clear video
            # request ("فرّغه"، "لخّص الفيديو"، "أريده بالكامل") → reuse the LAST
            # YouTube link from the conversation. Guarded so a conversation-summary
            # request never re-summarizes an old video.
            if not yurl:
                _cl = " " + _cur.lower() + " "
                _refers_video = (self._detect_youtube_intent(_cur).get("explicit")
                                 or any(k in _cl for k in (
                                     "الفيديو", "الفيدو", "المقطع", "الحلقة",
                                     "المحاضرة", "بالكامل", "الكامل", " كامل ",
                                     " video ", " full ", " complete ")))
                if _refers_video:
                    _last = None
                    # reuse a link from THIS conversation's history, but NEVER
                    # from the appended cross-chat memory block.
                    for _u in _re.findall(
                            r"https?://\S+",
                            self._strip_injected_memory(task.description)):
                        _u = _u.rstrip('.,)"\'،؛')
                        if _yt.is_youtube_url(_u):
                            _last = _u        # keep the LAST match
                    yurl = _last
            if yurl:
                kw = self._detect_youtube_intent(_cur)
                if kw.get("explicit"):
                    intent = {"mode": kw["mode"],
                              "with_timing": kw["with_timing"]}
                else:
                    # ambiguous wording → let the model understand ANY phrasing;
                    # fall back to the heuristic (default summary) if unavailable.
                    intent = (self._classify_youtube_intent_llm(_cur)
                              or {"mode": kw["mode"],
                                  "with_timing": kw["with_timing"]})
                # ALWAYS fetch the video's ORIGINAL captions (never auto-translated
                # Arabic) — the transcript stays in the video's own language; the
                # summary is translated by the model per the output-language rule.
                res = await _yt.run({"url": yurl, "lang": "ar",
                                     "with_timing": intent["with_timing"],
                                     "prefer_original": True})
                if getattr(res, "ok", False) and (res.data or {}).get("text"):
                    # Output language for the SUMMARY: an explicit request wins;
                    # "source/original" → the video's own language; otherwise the
                    # language the request itself is written in (never assumed).
                    _lk, _ln = self._requested_output_lang(_cur)
                    task.task_card = {
                        "task_type": "youtube_" + intent["mode"],
                        "topic": "تلخيص/تفريغ فيديو يوتيوب",
                        "language": ("ar" if (_lk == "name" and _ln == "العربية")
                                     or (_lk is None
                                         and self._detect_lang(_cur) == "ar")
                                     else "en"),
                        "output_format": ["INLINE"],
                        "sourcing_mode": "none",
                        "youtube": {
                            "url": yurl, "mode": intent["mode"],
                            "with_timing": intent["with_timing"],
                            "transcript": res.data["text"],
                            "transcript_plain": (res.data or {}).get(
                                "text_plain", ""),
                            "out_lang_kind": _lk,      # None | "name" | "source"
                            "out_lang_name": _ln,      # e.g. "العربية"/"English"
                            "req_lang": self._detect_lang(_cur),
                        },
                    }
                    task.skills = []
                    task.tools = []
                    mem.set_status(3, f"يوتيوب: {intent['mode']} — نص "
                                      f"{len(res.data['text'])} حرف")
                    return
                # Fetch failed (no captions / throttled / library missing).
                # If the request is ALSO a research task (has other triggers),
                # let the normal path proceed. But for a pure YouTube ask, stay
                # in the youtube lane with an honest message instead of emitting
                # a spurious research report (the original complaint).
                _t = _cur.lower()
                _also_research = any(k in _t for k in _TASK_TRIGGERS)
                if not _also_research:
                    _why = getattr(res, "error", "") or "لا يوجد نص/ترجمة متاح"
                    task.task_card = {
                        "task_type": "youtube_" + intent["mode"],
                        "topic": "تفريغ/تلخيص فيديو يوتيوب",
                        "language": "ar",
                        "output_format": ["INLINE"],
                        "sourcing_mode": "none",
                        "youtube": {
                            "url": yurl, "mode": intent["mode"],
                            "with_timing": intent["with_timing"],
                            "transcript": "",
                            "error": str(_why),
                        },
                    }
                    task.skills = []
                    task.tools = []
                    mem.set_status(3, f"يوتيوب: تعذّر جلب النص ({_why})")
                    return
                mem.set_status(3, "يوتيوب: لا نص متاح — المسار العادي")
        except Exception:
            pass

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
        # an explicit format in the request wins (احفظه Word/PDF/بوربوينت/اكسل)
        _rf = self._requested_format(self._current_request(task.description))
        if _rf:
            task.task_card["output_format"] = [_rf]

        # Output-language rule: an explicit request wins; otherwise the language
        # of the task INSTRUCTIONS (the current request text), never the chat
        # language. The "follow the pasted file/link" case is finalized in
        # _read_pasted_urls once the file's own language is known.
        try:
            _cur3 = self._current_request(task.description)
            _lk3, _ln3 = self._requested_output_lang(_cur3)
            if _lk3 == "name":
                task.task_card["language"] = ("ar" if _ln3 == "العربية" else "en")
                task.task_card["lang_locked"] = True
            elif _lk3 == "source":
                task.task_card["lang_locked"] = "source"   # resolved from content
            else:
                task.task_card["language"] = self._detect_lang(_cur3)
        except Exception:
            pass

        # Safety net: never let an INJECTED context header (memory / attachment /
        # instruction block) become the document topic or filename. If the model
        # picked one up, fall back to the current request text.
        try:
            _tp = str(task.task_card.get("topic") or "").strip()
            _bad = ("مهام سابقة", "محتوى الملف", "تعليمات مهمة", "ذاكرة:",
                    "للسياق فقط", "الملفات المرفقة", "reference only",
                    "for context only")
            if _tp.startswith("[") or any(k in _tp for k in _bad):
                _clean = self._current_request(task.description).strip()
                # keep only the part before any injected marker
                for _m in ("\n[", "[محتوى الملف", "[للسياق", "[ذاكرة",
                           "[تعليم", "[سياق المحادثة"):
                    _i = _clean.find(_m)
                    if _i > 0:
                        _clean = _clean[:_i].strip()
                if _clean:
                    task.task_card["topic"] = _clean[:150]
        except Exception:
            pass

        # how the user wants sourcing handled (cited / uncited / none). Detected
        # from the RAW request so an explicit "بدون مصادر" / "دون توثيقها" is
        # honoured even if the model didn't surface it in the card.
        task.task_card["sourcing_mode"] = self._sourcing_mode(task.description)

        # documentation style named in the request (APA/MLA/…) — explicit wins.
        # Without this the writer was handed a blank "Citation style:".
        try:
            _cs = self._requested_citation_style(task.description)
            if _cs:
                task.task_card["citation_style"] = _cs
        except Exception:
            pass

        # scope that LIMITS the task: references-only / outline-only / part-only.
        _cur_req = self._current_request(task.description)
        task.task_card["scope"] = self._task_scope(_cur_req)
        # full composable set (references/outline/plan/part) for combined asks
        # like "مراجع وهيكلة فقط". Single-scope consumers keep using ["scope"].
        try:
            task.task_card["scopes"] = sorted(self._task_scopes(_cur_req))
        except Exception:
            task.task_card["scopes"] = []

        # requested slide count (e.g. "اعمل عرض 30 شريحة") → reaches
        # design_slides. Absent → None → default behaviour unchanged.
        try:
            _sc = self._extract_slide_count(task.description)
            if _sc and isinstance(task.task_card, dict):
                task.task_card["slide_count"] = _sc
        except Exception:
            pass

        # action + enrichment intents (rewrite/summarize/translate/convert/edit,
        # table, chart, find-data). Detection only here; safe wirings read these
        # flags below. Absent → nothing set → behaviour unchanged.
        try:
            if isinstance(task.task_card, dict):
                _act = self._task_action(_cur_req)
                if _act:
                    task.task_card["action"] = _act
                if self._wants_table(_cur_req):
                    task.task_card["want_table"] = True
                if self._wants_chart(_cur_req):
                    task.task_card["want_chart"] = True
                if self._wants_data(_cur_req):
                    task.task_card["want_data"] = True
                # explicit cover page / table-of-contents requests → set the
                # flags the docx builder reads (they were never wired, so
                # "صفحة غلاف وفهرس" produced neither). Additive.
                if self._wants_cover(_cur_req):
                    task.task_card["cover"] = True
                if self._wants_toc(_cur_req):
                    task.task_card["toc"] = True
        except Exception:
            pass

        # requested length (words/pages) → recorded for the writer/export and
        # read by layer 6.6. Absent → nothing set → behaviour unchanged.
        try:
            _lt = self.extract_length_target(task.description)
            if isinstance(task.task_card, dict):
                if _lt.get("words"):
                    task.task_card["target_words"] = _lt["words"]
                if _lt.get("pages"):
                    task.task_card["target_pages"] = _lt["pages"]
                # an explicit CEILING, so the writer can aim UNDER it instead of
                # overshooting (nothing in the pipeline ever trims)
                if _lt.get("max_words"):
                    task.task_card["max_words"] = _lt["max_words"]
                if _lt.get("max_pages"):
                    task.task_card["max_pages"] = _lt["max_pages"]
        except Exception:
            pass

        # ── UNDERSTANDING FIRST: let the model read the request and DECIDE the
        #    intent; its answer OVERRIDES the keyword guesses above (which now
        #    serve only as a fallback when the model is unavailable). This is the
        #    real fix — the system understands any phrasing instead of matching
        #    hand-coded words. Fully guarded and additive.
        try:
            # Prefer the UNIFIED brain: it reads THIS conversation's full history
            # + the capability catalog, so any phrasing is understood and a
            # follow-up never forgets the subject. Fall back to the single-line
            # keyword classifier only when the brain is unavailable/unusable — so
            # nothing is lost. The merge below is unchanged: it still treats an
            # explicit keyword scope as authoritative.
            _iv = None
            _plan = None
            try:
                _plan = understand_request(
                    self._conversation_context(task.description), _cur_req,
                    llm_fn=self.llm_fn, system=self.system_main)
            except Exception:
                _plan = None
            if _plan and _plan.get("tasks"):
                _iv = _plan["tasks"][0]                 # primary task
                if isinstance(task.task_card, dict):
                    task.task_card["plan"] = _plan       # kept for later steps
                    task.task_card["plan_tasks"] = _plan["tasks"]
                    # the plan saw the WHOLE conversation, so its topic is the
                    # reliable subject even when the current line is only a format
                    # instruction ("اجعلها 3 مباحث") — this is the general fix for
                    # "forgot the topic".
                    if _iv.get("topic"):
                        task.task_card["topic"] = _iv["topic"]
            if not _iv:
                _iv = self._intent_router(_cur_req)     # keyword-model fallback
            if _iv and isinstance(task.task_card, dict):
                c = task.task_card
                if _iv.get("action"):
                    c["action"] = _iv["action"]
                if _iv.get("scopes"):
                    # A keyword-detected LIMITING scope is EXPLICIT (an "فقط"/
                    # "only" cue) and authoritative — a weak on-device model must
                    # never override or dilute it (e.g. turn a crisp "هيكلة فقط"
                    # into a references search, which then forces the whole
                    # research pipeline). We adopt the model's scope reading ONLY
                    # when the keyword layer found NO limiting scope, so any
                    # phrasing the keyword lists missed is still understood.
                    if not (c.get("scopes") or c.get("scope")):
                        c["scopes"] = _iv["scopes"]
                        c["scope"] = next((s for s in ("references", "plan",
                                                       "outline", "part")
                                           if s in _iv["scopes"]), None)
                if _iv.get("format"):
                    c["output_format"] = [_iv["format"].upper()]
                if _iv.get("slide_count"):
                    c["slide_count"] = _iv["slide_count"]
                if _iv.get("words"):
                    c["target_words"] = _iv["words"]
                if _iv.get("pages"):
                    c["target_pages"] = _iv["pages"]
                if _iv.get("mabhath_count"):
                    c["mabhath_count"] = _iv["mabhath_count"]
                if _iv.get("matlab_count"):
                    c["matlab_count"] = _iv["matlab_count"]
                if _iv.get("wants_table"):
                    c["want_table"] = True
                if _iv.get("wants_chart"):
                    c["want_chart"] = True
                if _iv.get("wants_data"):
                    c["want_data"] = True
                if _iv.get("needs_sources") is not None:
                    c["needs_sources"] = _iv["needs_sources"]
                c["intent_source"] = "model"
                mem.set_status(3, "فهم النية (نموذج): "
                               + (c.get("scope") or c.get("action") or "بحث"))
        except Exception as e:
            mem.set_status(3, f"موجّه النية (تخطّي: {e})")

        # ── STAGE (أ) WIRING 1 — REQUIREMENTS CHECKLIST (build + store) ──
        # Build the dynamic requirements checklist from the FULL request (no
        # truncation) and store it on the card, so Layer 8 can verify what was
        # actually delivered. Skipped for a pure chat/INLINE answer so a quick
        # reply isn't slowed by an extra model call. Fully guarded and additive.
        #
        # ── STAGE (أ) WIRING 2 — deliverable GOVERNS the scope (the root fix) ──
        # When the model — reading the WHOLE request — judged this a complete
        # document (deliverable == "full_document") but a keyword guess limited
        # the scope to a structural/partial one, the model's MEANING wins and the
        # limiting scope is cleared, so it becomes a full research. This is the
        # proven fix for "بحث بالكامل … الهيكلة مكوّنة من…" being mis-read as an
        # outline: the keyword scope's source was a DESCRIPTION word («هيكلة»),
        # not a real «only» request. ONE safe direction only — toward the fuller
        # deliverable, never the reverse — and only on an explicit full_document
        # judgement (a missing/other deliverable changes nothing).
        try:
            if isinstance(task.task_card, dict) and self.llm_fn:
                _of = task.task_card.get("output_format") or []
                if list(_of) != ["INLINE"]:
                    _kw_scope = task.task_card.get("scope")
                    _req = extract_requirements(
                        self._conversation_context(task.description), _cur_req,
                        llm_fn=self.llm_fn, system=self.system_main)
                    if _req:
                        task.task_card["requirements"] = _req.get("requirements")
                        task.task_card["deliverable"] = _req.get("deliverable")
                        _n = len(_req.get("requirements") or [])
                        _dv = _req.get("deliverable")
                        mem.set_status(3, f"متطلّبات: {_n} بند"
                                       + (f" — {_dv}" if _dv else ""))
                        # ── the model's OWN checklist, checked against itself ──
                        # A limiting deliverable that the model contradicts in its
                        # own typed requirements (a page/word length, a count of
                        # sources) is self-inconsistent: nobody asks for a
                        # headings-only outline AND "10–12 pages" AND "9 APA
                        # references". This reads the model's structured fields —
                        # kind/target — not words in prose, and it only ever moves
                        # toward the FULLER deliverable, never the narrower one.
                        if _dv in ("outline", "references", "plan", "part"):
                            _why = self._deliverable_contradicted(
                                _req.get("requirements"))
                            if _why:
                                mem.set_status(
                                    3, f"حكم النموذج «{_dv}» يخالف متطلّباته "
                                       f"({_why}) → مستند كامل")
                                _dv = "full_document"
                                task.task_card["deliverable"] = _dv
                                task.task_card["deliverable_reason"] = _why
                        # ── WIRING 2 (v2): the MODEL RULES the scope ──
                        # When the model returned a judgement it now decides in
                        # BOTH directions, with no veto from the keyword guess:
                        # full_document clears a limiting scope, and a limiting
                        # deliverable sets one. The keyword lists survive only as
                        # the fallback for when there is no model judgement at all
                        # (offline / failed call) — a backstop, not the ruler.
                        _lim = {"outline", "references", "plan", "part"}
                        _cur_scopes = set(task.task_card.get("scopes") or [])
                        if _dv == "full_document":
                            if (task.task_card.get("scope") in _lim
                                    or (_cur_scopes & _lim)):
                                task.task_card["scope"] = None
                                task.task_card["scopes"] = []
                                task.task_card["deliverable_override"] = True
                                mem.set_status(
                                    3, "تصحيح النطاق: مستند كامل (بحسب معنى الطلب)")
                        elif _dv in _lim and task.task_card.get("scope") != _dv:
                            task.task_card["scope"] = _dv
                            task.task_card["scopes"] = sorted(
                                (_cur_scopes & _lim) | {_dv})
                            task.task_card["deliverable_override"] = True
                            mem.set_status(3, f"تصحيح النطاق: {_dv} (حكم النموذج)")
                    else:
                        task.task_card["deliverable_reason"] = "نداء المتطلّبات لم يُرجع حكماً"
                    # SHOW the judgement. It used to live only in the internal
                    # status, so a wrong route looked like a mystery from outside;
                    # on screen it is checkable in one test run.
                    self._emit(
                        "detail", "",
                        "حكم المخرَج: "
                        + (str((_req or {}).get("deliverable") or "—"))
                        + f" · تخمين الكلمات: {_kw_scope or 'مستند كامل'}"
                        + f" · النطاق النهائي: "
                        + (task.task_card.get("scope") or "مستند كامل"))
        except Exception as e:
            task.task_card["deliverable_reason"] = f"{type(e).__name__}: {e}"
            mem.set_status(3, f"استخراج المتطلّبات (تخطّي: {e})")
            self._emit("detail", "", f"حكم المخرَج: تعذّر ({type(e).__name__})"
                       f" · النطاق: {task.task_card.get('scope') or 'مستند كامل'}")

        # ── LAST-RESORT BACKSTOP (no model judgement at all) ──
        # With the model unreachable there is no judgement to rule, so the keyword
        # guess is all that remains — and that guess is exactly what produced a
        # 78-word outline for a request asking for 10–12 pages. This checks the
        # card's OWN already-extracted NUMBERS against the limiting scope: a
        # headings-only outline has no page count and no word count. Arithmetic on
        # extracted values, not word matching, and one safe direction only.
        # Disable with WEAVER_SCOPE_BACKSTOP=0.
        try:
            import os as _os
            if (_os.environ.get("WEAVER_SCOPE_BACKSTOP", "1") != "0"
                    and isinstance(task.task_card, dict)
                    and not task.task_card.get("deliverable")):
                _lim = {"outline", "references", "plan", "part"}
                _sc = task.task_card.get("scope")
                _scs = set(task.task_card.get("scopes") or [])
                if _sc in _lim or (_scs & _lim):
                    _pg = task.task_card.get("target_pages")
                    _wd = task.task_card.get("target_words")
                    _pg = _pg if isinstance(_pg, int) else 0
                    _wd = _wd if isinstance(_wd, int) else 0
                    if _pg >= 3 or _wd >= 600:
                        task.task_card["scope"] = None
                        task.task_card["scopes"] = []
                        task.task_card["deliverable_override"] = True
                        task.task_card["deliverable_reason"] = (
                            f"بلا حكم نموذج، وطولٌ مطلوب "
                            f"({_pg or '—'} صفحة / {_wd or '—'} كلمة) "
                            f"لا يتّفق مع «{_sc}»")
                        mem.set_status(3, "تصحيح النطاق (احتياط): مستند كامل — "
                                          "الطول المطلوب يخالف نطاقاً مُقيَّداً")
                        self._emit("detail", "",
                                   "احتياط النطاق: الطول المطلوب "
                                   f"({_pg or '—'} صفحة) يخالف «{_sc}» "
                                   "→ مستند كامل")
        except Exception as e:
            mem.set_status(3, f"احتياط النطاق (تخطّي: {e})")

        # Phase 3: route tools & skills once
        self._route(task)

        # references-only, a proposal, or any composite that includes references
        # must actually gather sources → force the search tools.
        _scs = set(task.task_card.get("scopes") or [])
        _scope = task.task_card.get("scope")
        if (_scope in ("references", "plan")
                or "references" in _scs or "plan" in _scs
                or task.task_card.get("want_data")):
            for _t in ("web_search", "academic_search"):
                if _t not in task.tools:
                    task.tools.append(_t)
            task.task_card["needs_academic_search"] = True
        # a PURELY structural scope (outline-only) needs NO sources — strip the
        # search tools so it returns the structure in seconds instead of running
        # the whole research pipeline (search + credibility). Composites that
        # also want references/plan/data keep gathering (handled above).
        elif _scope == "outline" and not ({"references", "plan"} & _scs):
            # No sourcing of ANY kind for a purely structural ask: drop the live
            # search tools AND the page/document readers. With no pasted URL there
            # is nothing for web_extract/web_document to read anyway, so keeping
            # them only mislabels the run (and shows as active tools) — the
            # structure is produced from the model directly, in seconds.
            task.tools = [t for t in task.tools
                          if t not in ("web_search", "academic_search",
                                       "web_extract", "web_document")]
            task.task_card.pop("needs_academic_search", None)

        # GENERAL-KNOWLEDGE gate: when the model judged the task needs NO external
        # sources (timeless knowledge — a definition/comparison, a table of known
        # facts, creative writing, or operating on a provided text) AND the user
        # did not explicitly ask for sourcing, DON'T run academic/web search —
        # answer directly (fast). This is the general fix for a simple ask (e.g.
        # «جدول مقارنة بين الخلية الحيوانية والنباتية») being pushed through the
        # whole research pipeline. Any explicit source signal keeps search ON, so
        # genuine research is never weakened. Only an EXPLICIT needs_sources==False
        # triggers this — a missing/None judgment leaves behaviour unchanged.
        if task.task_card.get("needs_sources") is False:
            _c = task.task_card
            _td = f"{_c.get('topic','')} " \
                  f"{self._strip_injected_memory(task.description)}"
            _txt = " " + (task.description or "").lower() + " "
            _src_words = ("مراجع", "مصادر", "استشهد", "توثيق", "دراسات",
                          "references", "citation", "peer-reviewed", "sources")
            _explicit = (
                _c.get("reference_count")
                or str(_c.get("citation_style", "")).upper()
                not in ("", "UNSPECIFIED")
                or _scope in ("references", "plan")
                or ({"references", "plan"} & _scs)
                or _c.get("want_data")
                or self._is_recency_query(_td)
                or any(w in _txt for w in _src_words))
            if not _explicit:
                task.tools = [t for t in task.tools
                              if t not in ("web_search", "academic_search")]
                _c.pop("needs_academic_search", None)
                try:
                    mem.set_status(3, "إجابة مباشرة (معرفة عامة، بلا بحث)")
                except Exception:
                    pass

    async def _layer_4(self, task: Task, mem: TaskMemory):
        """٤: البحث — أكاديمي (PaperQA) + بحث ويب حي (SearXNG). يُشغَّل ما وُجّهت
        إليه طبقة الفهم فقط، ونتائج الويب تُخزَّن كمصادر للطبقتين ٥ و٦."""
        task.status = TaskStatus.LAYER_4
        # read any URL pasted in the request as a PRIMARY source (page/YouTube),
        # regardless of routing — so "لخّص هذا الفيديو <url>" reads the video.
        await self._read_pasted_urls(task, mem)
        # when the user pasted a link, FOCUS on it: a link summary is never an
        # academic-paper task (skip academic), and if we actually read the link
        # we skip the generic topic web search too (it only adds off-topic
        # "how to summarize videos" noise). If the link couldn't be read, the
        # web search stays as a fallback.
        pasted_present = bool(task.task_card.get("pasted_present"))
        pasted_ok = bool(task.task_card.get("pasted_reads"))
        want_academic = (("academic_search" in task.tools
                          or task.task_card.get("needs_academic_search"))
                         and not pasted_present)
        want_web = ("web_search" in task.tools) and not pasted_ok
        if not want_academic and not want_web:
            if pasted_ok:
                mem.set_status(4, "الاعتماد على الرابط المُدرَج — تخطّي البحث العام")
            else:
                mem.set_status(4, "لا يلزم بحث — تخطّي")
            return
        if want_academic:
            from pipeline.layers.layer_4_research import run as _layer4_run
            await _layer4_run(task, mem)          # PaperQA (if installed)
            await self._academic_search(task, mem)  # free scholarly APIs
        if want_web:
            await self._web_search(task, mem)

    @staticmethod
    def _is_recency_query(text) -> bool:
        """True when the request wants fresh/current information (news, latest,
        today…), in Arabic or English. Used to switch on live web search and
        the recency-oriented ranking."""
        t = " " + (text or "").lower() + " "
        kws = ("أخبار", "آخر", "اليوم", "الآن", "حالياً", "حاليا", "مؤخراً",
               "مؤخرا", "أحدث", "جديد", "هذا الأسبوع", "هذا الشهر",
               "news", "latest", "today", "now", "recent", "breaking",
               "current", "this week", "this month")
        return any(k in t for k in kws)

    @staticmethod
    def _search_directives(text):
        """Explicit search constraints in the request: (site_domain, df).
        `site_domain` restricts results to one site; `df` is a date range
        (d/w/m/y). Either may be None."""
        import re
        tl = (text or "").lower()
        site = None
        m = re.search(r'site:\s*([a-z0-9.\-]+\.[a-z]{2,})', tl)
        if m:
            site = m.group(1)
        else:
            m = re.search(r'(?:موقع|from|on)\s+'
                          r'([a-z0-9\-]+\.[a-z]{2,}(?:\.[a-z]{2,})?)', tl)
            if m:
                site = m.group(1)
        df = None
        if any(k in tl for k in ("اليوم", "today", "آخر يوم", "اخر يوم",
                                 "past day", "last 24")):
            df = "d"
        elif any(k in tl for k in ("هذا الأسبوع", "هذا الاسبوع", "آخر أسبوع",
                                   "اخر اسبوع", "this week", "past week")):
            df = "w"
        elif any(k in tl for k in ("هذا الشهر", "آخر شهر", "اخر شهر",
                                   "this month", "past month")):
            df = "m"
        elif any(k in tl for k in ("هذا العام", "هذه السنة", "آخر سنة",
                                   "اخر سنة", "this year", "past year")):
            df = "y"
        return (site, df)

    @staticmethod
    def _augment_query_with_date(query, lang):
        """Append the current year (and month for daily/'today' intent) to a
        query so engines favour fresh results. The year/month are computed
        dynamically from datetime.now() — never hard-coded."""
        import datetime
        q = (query or "").strip()
        if not q:
            return q
        now = datetime.datetime.now()
        year = str(now.year)
        if year in q:
            return q                     # already dated — leave it
        daily = any(w in q.lower() for w in
                    ("اليوم", "الآن", "today", "now", "breaking", "عاجل"))
        if daily:
            if lang == "ar":
                months_ar = ["يناير", "فبراير", "مارس", "أبريل", "مايو",
                             "يونيو", "يوليو", "أغسطس", "سبتمبر", "أكتوبر",
                             "نوفمبر", "ديسمبر"]
                return q + " " + months_ar[now.month - 1] + " " + year
            return q + " " + now.strftime("%B") + " " + year
        return q + " " + year

    @staticmethod
    def _sort_results_by_recency(results):
        """Stable-sort results newest-first. Scores each by an explicit year
        (2020-2030) and relative-time phrases ('قبل ساعة/يوم', 'hours/days ago')
        in title+content; items with no time signal keep their relative order
        (stable sort). Never raises."""
        import re
        import datetime  # noqa: F401 (kept for clarity/extension)
        if not results:
            return results

        def score(r):
            try:
                t = (str(r.get("title", "")) + " "
                     + str(r.get("content", ""))).lower()
            except Exception:
                return 0
            best = 0
            for m in re.findall(r"\b(20[2-3]\d)\b", t):
                y = int(m)
                if 2020 <= y <= 2030:
                    best = max(best, 1000 + (y - 2000) * 10)
            rel = (
                (r"(?:قبل|منذ)\s*(?:دقيقة|دقائق|ساعة|ساعات)", 1400),
                (r"\b(?:minute|hour)s?\s+ago\b|just now", 1400),
                (r"(?:قبل|منذ)\s*(?:يوم|يومين|أيام)", 1350),
                (r"\bday(?:s)?\s+ago\b|yesterday|أمس", 1330),
                (r"(?:قبل|منذ)\s*(?:أسبوع|أسابيع)", 1300),
                (r"\bweek(?:s)?\s+ago\b", 1300),
                (r"(?:قبل|منذ)\s*(?:شهر|أشهر)", 1200),
                (r"\bmonth(?:s)?\s+ago\b", 1200),
            )
            for pat, w in rel:
                if re.search(pat, t):
                    best = max(best, w)
            return best
        # sorted() is stable, so equal-score items keep their original order
        return sorted(results, key=lambda r: -score(r))

    @staticmethod
    def _searx_query(instance: str, query: str, lang: str, limit: int,
                     timeout: int = 8, time_range=None, sort_by_date=False):
        """Direct SearXNG JSON search. Returns a list of {title,url,content}
        or None when the instance is unreachable / returns nothing usable.

        Optional (backward compatible — old calls without them still work):
          * time_range: "day"/"week"/"month"/"year" → SearXNG time filter.
          * sort_by_date: intent flag kept for callers; SearXNG's JSON API has
            no direct sort param, so newest-first ordering is applied later by
            _sort_results_by_recency.
        Uses _http_get so it survives broken device DNS (DoH retry)."""
        import urllib.parse
        import json as _json
        instance = (instance or "").rstrip("/")
        if not instance:
            return None
        params = {"q": query, "format": "json", "categories": "general"}
        if lang:
            params["language"] = lang
        if time_range in ("day", "week", "month", "year"):
            params["time_range"] = time_range
        url = instance + "/search?" + urllib.parse.urlencode(params)
        # a real browser UA: many public SearXNG instances reject bot-like UAs
        raw = WeaverOrchestrator._http_get(
            url, {"User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                                 "AppleWebKit/537.36 (KHTML, like Gecko) "
                                 "Chrome/122.0.0.0 Safari/537.36"),
                  "Accept": "application/json"}, timeout)
        if not raw:
            return None
        try:
            data = _json.loads(raw)
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
    def _ddg_search(query: str, lang: str, limit: int, timeout: int = 12,
                    df=None):
        """Direct DuckDuckGo search — NO server required (works on the phone as
        is). Hits the html.duckduckgo.com endpoint over plain HTTP, decoding
        DDG's redirect links. Prefers UniWeb/curl_impersonate (real browser
        fingerprint, beats bot-blocking) and falls back to urllib. Returns a
        list of {title,url,content} or None when nothing usable comes back.

        Optional (backward compatible): df is DuckDuckGo's time filter —
        'd' (day), 'w' (week), 'm' (month), 'y' (year)."""
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
        if df in ("d", "w", "m", "y"):
            params["df"] = df           # recency filter
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

    @staticmethod
    def _bing_search(query: str, lang: str, limit: int, timeout: int = 12):
        """Serverless Bing HTML search. Returns {title,url,content} list or None.
        Bing has a huge, independent index, so it broadens results beyond DDG.
        Degrades safely (parse/network failure → None). DNS-safe via _http_get."""
        import urllib.parse
        import html as _html
        import re
        q = (query or "").strip()
        if not q:
            return None
        params = {"q": q}
        if lang == "ar":
            params["setlang"] = "ar"
            params["cc"] = "XA"
        url = "https://www.bing.com/search?" + urllib.parse.urlencode(params)
        ua = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36")
        raw = WeaverOrchestrator._http_get(
            url, {"User-Agent": ua, "Accept": "text/html",
                  "Accept-Language": ("ar,en;q=0.8" if lang == "ar"
                                      else "en-US,en;q=0.8")}, timeout)
        if not raw:
            return None

        def _clean(s):
            return _html.unescape(re.sub(r"\s+", " ",
                                         re.sub(r"<[^>]+>", "", s or ""))).strip()
        results = []
        # tolerate nested tags between <h2> and its <a> (spans, etc.)
        for blk in re.findall(r'<li class="b_algo".*?</li>', raw, re.S):
            a = (re.search(r'<h2[^>]*>.*?<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>',
                           blk, re.S)
                 or re.search(r'<a[^>]+class="[^"]*tilk[^"]*"[^>]+'
                              r'href="([^"]+)"[^>]*>(.*?)</a>', blk, re.S))
            if not a:
                continue
            u = _html.unescape(a.group(1))
            title = _clean(a.group(2))
            if not u.startswith("http") or not title:
                continue
            if "bing.com" in u or "microsofttranslator" in u:
                continue
            cap = (re.search(r'<p class="b_[^"]*"[^>]*>(.*?)</p>', blk, re.S)
                   or re.search(r'<p[^>]*>(.*?)</p>', blk, re.S))
            results.append({"title": title, "url": u,
                            "content": _clean(cap.group(1) if cap else "")})
            if len(results) >= limit:
                break
        return results or None

    @staticmethod
    def _mojeek_search(query: str, lang: str, limit: int, timeout: int = 10):
        """Serverless Mojeek HTML search. Mojeek has its OWN independent crawler
        (not Google/Bing), so it genuinely broadens results. Returns
        {title,url,content} list or None; degrades safely. DNS-safe via
        _http_get."""
        import urllib.parse
        import html as _html
        import re
        q = (query or "").strip()
        if not q:
            return None
        url = "https://www.mojeek.com/search?" + urllib.parse.urlencode({"q": q})
        ua = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36")
        raw = WeaverOrchestrator._http_get(
            url, {"User-Agent": ua, "Accept": "text/html",
                  "Accept-Language": ("ar,en;q=0.8" if lang == "ar"
                                      else "en-US,en;q=0.8")}, timeout)
        if not raw:
            return None

        def _clean(s):
            return _html.unescape(re.sub(r"\s+", " ",
                                         re.sub(r"<[^>]+>", "", s or ""))).strip()
        mc = re.search(r'<ul class="results-standard">(.*?)</ul>', raw, re.S)
        body = mc.group(1) if mc else raw
        results = []
        for blk in re.findall(r'<li[^>]*>(.*?)</li>', body, re.S):
            # the real result title is an <a class="title"> (or the <h2> anchor)
            a = (re.search(r'<a[^>]+class="[^"]*title[^"]*"[^>]+'
                           r'href="(https?://[^"]+)"[^>]*>(.*?)</a>', blk, re.S)
                 or re.search(r'<h2[^>]*>\s*<a[^>]+href="(https?://[^"]+)"'
                              r'[^>]*>(.*?)</a>', blk, re.S))
            if not a:
                continue
            u, title = a.group(1), _clean(a.group(2))
            if not title or "mojeek.com" in u:      # skip logo/nav/empty rows
                continue
            snip = re.search(r'<p class="s"[^>]*>(.*?)</p>', blk, re.S)
            results.append({"title": title, "url": u,
                            "content": _clean(snip.group(1) if snip else "")})
            if len(results) >= limit:
                break
        return results or None

    @staticmethod
    def _startpage_search(query: str, lang: str, limit: int, timeout: int = 8):
        """Serverless Startpage HTML search (Google results, privacy proxy).
        BEST-EFFORT: Startpage has strong anti-bot protection, so it often
        returns nothing — that's fine, it simply contributes no results.
        DNS-safe via _http_get; never raises."""
        import urllib.parse
        import html as _html
        import re
        q = (query or "").strip()
        if not q:
            return None
        url = ("https://www.startpage.com/sp/search?"
               + urllib.parse.urlencode({"query": q}))
        ua = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36")
        raw = WeaverOrchestrator._http_get(
            url, {"User-Agent": ua, "Accept": "text/html",
                  "Accept-Language": ("ar,en;q=0.8" if lang == "ar"
                                      else "en-US,en;q=0.8")}, timeout)
        if not raw:
            return None

        def _clean(s):
            return _html.unescape(re.sub(r"\s+", " ",
                                         re.sub(r"<[^>]+>", "", s or ""))).strip()
        results = []
        for m in re.finditer(
                r'<a[^>]+class="[^"]*result[-_]?(?:link|title)[^"]*"[^>]+'
                r'href="(https?://[^"]+)"[^>]*>(.*?)</a>', raw, re.S):
            u = _html.unescape(m.group(1))
            if "startpage.com" in u:
                continue
            results.append({"title": _clean(m.group(2)), "url": u,
                            "content": ""})
            if len(results) >= limit:
                break
        snips = re.findall(r'<p[^>]+class="[^"]*description[^"]*"[^>]*>(.*?)</p>',
                           raw, re.S)
        for i, s in enumerate(snips[:len(results)]):
            results[i]["content"] = _clean(s)
        return results or None

    @classmethod
    def _multi_engine_search(cls, query, lang, limit, df=None):
        """SearXNG-like breadth WITHOUT a server: query several independent
        engines IN PARALLEL (DuckDuckGo + Bing + Mojeek + Startpage) and
        merge/dedupe by URL, interleaved so the mix stays diverse. Parallel, so
        total time ≈ the slowest engine, not the sum. Each engine degrades
        safely — a dead/blocked one just contributes nothing. Returns a merged
        list or None."""
        import itertools
        import concurrent.futures as _cf
        engines = [
            ("ddg", lambda: cls._ddg_search(query, lang, limit, df=df)),
            ("bing", lambda: cls._bing_search(query, lang, limit)),
            ("mojeek", lambda: cls._mojeek_search(query, lang, limit)),
            ("startpage", lambda: cls._startpage_search(query, lang, limit)),
        ]
        results_by_name = {}
        ex = _cf.ThreadPoolExecutor(max_workers=len(engines))
        try:
            futmap = {ex.submit(fn): name for name, fn in engines}
            done, _pending = _cf.wait(futmap, timeout=16)
            for fut, name in futmap.items():
                if fut in done:
                    try:
                        results_by_name[name] = fut.result() or []
                    except Exception:
                        results_by_name[name] = []
                else:
                    results_by_name[name] = []       # too slow → skip
        except Exception:
            # last-resort sequential fallback
            for name, fn in engines:
                try:
                    results_by_name[name] = fn() or []
                except Exception:
                    results_by_name[name] = []
        finally:
            ex.shutdown(wait=False, cancel_futures=True)
        lists = [results_by_name.get(name, []) for name, _ in engines]
        merged, seen = [], set()
        for r in itertools.chain.from_iterable(
                itertools.zip_longest(*lists)) if lists else []:
            if not r:
                continue
            u = (r.get("url") or "").split("#")[0].rstrip("/")
            if not u or u in seen or not (r.get("title") or "").strip():
                continue                              # drop dupes + empty rows
            seen.add(u)
            merged.append(r)
            if len(merged) >= max(limit, 8):
                break
        return merged or None

    # ── free academic sources (no API key) ────────────────────────────────
    # Each returns a list of {title,url,content,authors,year,doi,source} or
    # None; all go through _http_get (DoH-safe) and degrade safely. They index
    # Arabic works too, so Arabic queries return Arabic papers.
    _ACAD_UA = "WeaverWrite/1.0 (mailto:research@weaver.local)"

    @staticmethod
    def _openalex_search(query, lang, limit=6, timeout=12):
        import urllib.parse
        import json as _json
        q = (query or "").strip()
        if not q:
            return None
        url = "https://api.openalex.org/works?" + urllib.parse.urlencode(
            {"search": q, "per_page": min(int(limit) or 6, 10)})
        raw = WeaverOrchestrator._http_get(
            url, {"User-Agent": WeaverOrchestrator._ACAD_UA,
                  "Accept": "application/json"}, timeout)
        if not raw:
            return None
        try:
            data = _json.loads(raw)
        except Exception:
            return None
        out = []
        for w in (data.get("results") or [])[:limit]:
            title = w.get("title") or w.get("display_name") or ""
            if not title:
                continue
            doi = (w.get("doi") or "").replace("https://doi.org/", "")
            oa = (w.get("open_access") or {}).get("oa_url")
            url_ = oa or w.get("doi") or w.get("id") or ""
            auths = [(a.get("author") or {}).get("display_name", "")
                     for a in (w.get("authorships") or [])[:4]]
            abx = ""
            inv = w.get("abstract_inverted_index")
            if isinstance(inv, dict):
                pos = {}
                for word, ps in inv.items():
                    for p in ps:
                        pos[p] = word
                abx = " ".join(pos[k] for k in sorted(pos))[:400]
            out.append({"title": title, "url": url_, "content": abx,
                        "authors": [a for a in auths if a],
                        "year": str(w.get("publication_year") or ""),
                        "doi": doi, "source": "openalex"})
        return out or None

    @staticmethod
    def _crossref_search(query, lang, limit=6, timeout=12):
        import urllib.parse
        import json as _json
        import re
        q = (query or "").strip()
        if not q:
            return None
        url = "https://api.crossref.org/works?" + urllib.parse.urlencode(
            {"query": q, "rows": min(int(limit) or 6, 10)})
        raw = WeaverOrchestrator._http_get(
            url, {"User-Agent": WeaverOrchestrator._ACAD_UA,
                  "Accept": "application/json"}, timeout)
        if not raw:
            return None
        try:
            items = ((_json.loads(raw).get("message") or {}).get("items")) or []
        except Exception:
            return None
        out = []
        for it in items[:limit]:
            title = (it.get("title") or [""])[0]
            if not title:
                continue
            doi = it.get("DOI", "")
            url_ = it.get("URL") or (("https://doi.org/" + doi) if doi else "")
            year = ""
            dp = ((it.get("issued") or {}).get("date-parts")
                  or (it.get("published") or {}).get("date-parts"))
            if dp and dp[0]:
                year = str(dp[0][0])
            auths = [(a.get("given", "") + " " + a.get("family", "")).strip()
                     for a in (it.get("author") or [])[:4]]
            abx = re.sub(r"<[^>]+>", "", it.get("abstract", "") or "")[:400]
            out.append({"title": title, "url": url_, "content": abx,
                        "authors": [a for a in auths if a], "year": year,
                        "doi": doi, "source": "crossref"})
        return out or None

    @staticmethod
    def _arxiv_search(query, lang, limit=6, timeout=12):
        import urllib.parse
        import html as _html
        import re
        q = (query or "").strip()
        if not q:
            return None
        url = "http://export.arxiv.org/api/query?" + urllib.parse.urlencode(
            {"search_query": "all:" + q, "max_results": min(int(limit) or 6, 10)})
        raw = WeaverOrchestrator._http_get(
            url, {"User-Agent": WeaverOrchestrator._ACAD_UA,
                  "Accept": "application/atom+xml"}, timeout)
        if not raw:
            return None

        def _c(s):
            return _html.unescape(re.sub(r"\s+", " ", s or "")).strip()
        out = []
        for m in re.finditer(r"<entry>(.*?)</entry>", raw, re.S):
            e = m.group(1)
            t = re.search(r"<title>(.*?)</title>", e, re.S)
            if not t:
                continue
            idm = re.search(r"<id>(.*?)</id>", e, re.S)
            summ = re.search(r"<summary>(.*?)</summary>", e, re.S)
            pub = re.search(r"<published>(\d{4})", e)
            auths = re.findall(r"<name>(.*?)</name>", e, re.S)
            out.append({"title": _c(t.group(1)),
                        "url": (idm.group(1).strip() if idm else ""),
                        "content": (_c(summ.group(1))[:400] if summ else ""),
                        "authors": [_c(a) for a in auths[:4]],
                        "year": (pub.group(1) if pub else ""),
                        "doi": "", "source": "arxiv"})
            if len(out) >= limit:
                break
        return out or None

    @staticmethod
    def _semanticscholar_search(query, lang, limit=6, timeout=12):
        import urllib.parse
        import json as _json
        q = (query or "").strip()
        if not q:
            return None
        url = ("https://api.semanticscholar.org/graph/v1/paper/search?"
               + urllib.parse.urlencode(
                   {"query": q, "limit": min(int(limit) or 6, 10),
                    "fields": "title,abstract,year,authors,url,openAccessPdf"}))
        raw = WeaverOrchestrator._http_get(
            url, {"User-Agent": WeaverOrchestrator._ACAD_UA,
                  "Accept": "application/json"}, timeout)
        if not raw:
            return None
        try:
            data = _json.loads(raw).get("data") or []
        except Exception:
            return None
        out = []
        for p in data[:limit]:
            title = p.get("title") or ""
            if not title:
                continue
            pdf = (p.get("openAccessPdf") or {}).get("url")
            out.append({"title": title, "url": pdf or p.get("url") or "",
                        "content": (p.get("abstract") or "")[:400],
                        "authors": [a.get("name", "")
                                    for a in (p.get("authors") or [])[:4]],
                        "year": str(p.get("year") or ""), "doi": "",
                        "source": "semanticscholar"})
        return out or None

    @staticmethod
    def _doaj_search(query, lang, limit=6, timeout=12):
        import urllib.parse
        import json as _json
        q = (query or "").strip()
        if not q:
            return None
        url = ("https://doaj.org/api/search/articles/" + urllib.parse.quote(q)
               + "?" + urllib.parse.urlencode({"pageSize": min(int(limit) or 6, 10)}))
        raw = WeaverOrchestrator._http_get(
            url, {"User-Agent": WeaverOrchestrator._ACAD_UA,
                  "Accept": "application/json"}, timeout)
        if not raw:
            return None
        try:
            results = _json.loads(raw).get("results") or []
        except Exception:
            return None
        out = []
        for r in results[:limit]:
            b = r.get("bibjson") or {}
            title = b.get("title") or ""
            if not title:
                continue
            url_ = ""
            for L in (b.get("link") or []):
                if L.get("url"):
                    url_ = L["url"]
                    break
            auths = [a.get("name", "") for a in (b.get("author") or [])[:4]]
            out.append({"title": title, "url": url_,
                        "content": (b.get("abstract") or "")[:400],
                        "authors": [a for a in auths if a],
                        "year": str(b.get("year") or ""), "doi": "",
                        "source": "doaj"})
        return out or None

    @staticmethod
    def _europepmc_search(query, lang, limit=6, timeout=12):
        import urllib.parse
        import json as _json
        q = (query or "").strip()
        if not q:
            return None
        url = ("https://www.ebi.ac.uk/europepmc/webservices/rest/search?"
               + urllib.parse.urlencode(
                   {"query": q, "format": "json",
                    "pageSize": min(int(limit) or 6, 10)}))
        raw = WeaverOrchestrator._http_get(
            url, {"User-Agent": WeaverOrchestrator._ACAD_UA,
                  "Accept": "application/json"}, timeout)
        if not raw:
            return None
        try:
            results = ((_json.loads(raw).get("resultList") or {})
                       .get("result")) or []
        except Exception:
            return None
        out = []
        for r in results[:limit]:
            title = r.get("title") or ""
            if not title:
                continue
            doi = r.get("doi", "")
            url_ = (("https://doi.org/" + doi) if doi
                    else (("https://europepmc.org/abstract/"
                           + str(r.get("source", "")) + "/" + str(r.get("id", "")))
                          if r.get("id") else ""))
            out.append({"title": title, "url": url_, "content": "",
                        "authors": [r.get("authorString", "")],
                        "year": str(r.get("pubYear") or ""), "doi": doi,
                        "source": "europepmc"})
        return out or None

    @classmethod
    def _scholarly_search(cls, query, lang, limit, timeout=14):
        """Query all free scholarly sources IN PARALLEL (OpenAlex, Crossref,
        arXiv, Semantic Scholar, DOAJ, Europe PMC) and merge/dedupe by DOI/URL/
        title. Total time ≈ the slowest source. Each degrades safely. Returns a
        merged list or None."""
        import concurrent.futures as _cf
        import itertools
        engines = [
            ("openalex", lambda: cls._openalex_search(query, lang, limit)),
            ("crossref", lambda: cls._crossref_search(query, lang, limit)),
            ("arxiv", lambda: cls._arxiv_search(query, lang, limit)),
            ("s2", lambda: cls._semanticscholar_search(query, lang, limit)),
            ("doaj", lambda: cls._doaj_search(query, lang, limit)),
            ("europepmc", lambda: cls._europepmc_search(query, lang, limit)),
        ]
        res = {}
        ex = _cf.ThreadPoolExecutor(max_workers=len(engines))
        try:
            fm = {ex.submit(fn): n for n, fn in engines}
            done, _pending = _cf.wait(fm, timeout=timeout)
            for f, n in fm.items():
                try:
                    res[n] = (f.result() or []) if f in done else []
                except Exception:
                    res[n] = []
        except Exception:
            for n, fn in engines:
                try:
                    res[n] = fn() or []
                except Exception:
                    res[n] = []
        finally:
            ex.shutdown(wait=False, cancel_futures=True)
        lists = [res.get(n, []) for n, _ in engines]
        # relevance terms from the query (drop off-topic noise like random
        # physics papers arXiv returns for common words). Arabic tokens ≥3,
        # Latin tokens ≥4; ignore a short stop-list.
        terms = cls._query_terms(query)
        cap = max(int(limit) or 8, 8)
        merged, backup, seen = [], [], set()
        for r in itertools.chain.from_iterable(itertools.zip_longest(*lists)):
            if not r:
                continue
            key = (r.get("doi") or r.get("url") or r.get("title") or "")
            key = key.strip().lower().rstrip("/")
            if not key or key in seen or not (r.get("title") or "").strip():
                continue
            seen.add(key)
            blob = (str(r.get("title", "")) + " "
                    + str(r.get("content", ""))).lower()
            if not terms or any(t in blob for t in terms):
                merged.append(r)
            else:
                backup.append(r)          # off-topic → only if nothing relevant
            if len(merged) >= cap:
                break
        final = merged if merged else backup
        return final[:cap] or None

    @staticmethod
    def _query_terms(query):
        """Meaningful lowercased query terms for relevance filtering: Arabic
        tokens ≥3 chars, Latin tokens ≥4, minus a tiny stop-list."""
        import re
        stop = {"عن", "في", "من", "على", "the", "and", "for", "with", "about",
                "أثر", "تأثير", "دراسة", "بحث", "تقرير", "اكتب", "حول"}
        out = set()
        for tok in re.split(r"[\s,،.:؛()\[\]\"']+", (query or "").lower()):
            tok = tok.strip()
            if not tok or tok in stop:
                continue
            is_ar = any("؀" <= c <= "ۿ" for c in tok)
            if (is_ar and len(tok) >= 3) or (not is_ar and len(tok) >= 4):
                out.add(tok)
        return out

    async def _academic_search(self, task: Task, mem: TaskMemory):
        """Layer 4 academic path: gather peer-reviewed / open-access sources
        from the free scholarly APIs and add them to the task's sources + RAG
        memory. Degrades safely (no network / all down → nothing added)."""
        card = task.task_card
        query = (card.get("topic") or task.description or "").strip()
        if not query:
            return
        lang = "ar" if card.get("language", "ar") == "ar" else "en"
        limit = self._as_int(card.get("reference_count"), 8) or 8
        try:
            results = self._scholarly_search(query, lang, limit)
        except Exception:
            results = None
        if not results:
            mem.set_status(4, "بحث أكاديمي: لا نتائج (تدهور آمن)")
            return
        srcs = card.setdefault("sources", [])
        for r in results:
            title = r.get("title", "")
            url = r.get("url", "")
            auth = ", ".join(r.get("authors") or [])
            year = r.get("year", "")
            doi = r.get("doi", "")
            content = r.get("content") or ""
            srcs.append({"key": (title or url)[:60], "url": url, "title": title,
                         "content": content, "authors": r.get("authors") or [],
                         "year": year, "doi": doi,
                         "source": r.get("source", ""), "academic": True,
                         "full": False})
            mem.add_reference(
                f"[أكاديمي/{r.get('source','')}] {title} — {auth} ({year}) "
                f"{('doi:'+doi) if doi else ''} {content[:200]} ({url})",
                source_key=(url or doi or title))
        card["academic_reads"] = len(results)
        mem.set_status(4, f"بحث أكاديمي: {len(results)} مصدر محكّم")

    _URL_RE = None

    async def _read_pasted_urls(self, task: Task, mem: TaskMemory):
        """Read any URL the user pasted in the request (a web page or a YouTube
        video) as a PRIMARY source, via _extract_full (which routes YouTube to
        tool_youtube). Adds them to the task's sources + RAG memory. Safe: no
        URLs, or a failed read, just adds nothing."""
        import re
        # the dedicated YouTube path (Layer 3) already handled it — don't re-read
        if task.task_card.get("youtube"):
            return
        if self._URL_RE is None:
            type(self)._URL_RE = re.compile(r'https?://[^\s)>\]\"\'،]+')
        # only URLs in the CURRENT request — not ones pasted in earlier turns —
        # so an old link doesn't get re-read into an unrelated request now.
        urls = self._URL_RE.findall(self._current_request(task.description))
        card = task.task_card
        card["pasted_present"] = bool(urls)
        if not urls:
            return
        self._yt_lang = "ar" if card.get("language", "ar") == "ar" else "en"
        srcs = card.setdefault("sources", [])
        read = 0
        first_content = ""
        for u in urls[:3]:
            u = u.rstrip('.,)"،')
            try:
                txt = await self._extract_full(u)
            except Exception:
                txt = None
            if txt and txt.strip():
                full = txt.strip()
                if not first_content:
                    first_content = full
                srcs.append({"key": u[:60], "url": u, "title": u,
                             "content": full, "full": True, "pasted": True})
                # feed the FULL content into RAG in chunks (not a 300-char
                # snippet) so the writer can actually summarize the page/video.
                for i in range(0, min(len(full), 9000), 1500):
                    mem.add_reference(f"[رابط مُدرَج {u}] {full[i:i+1500]}",
                                      source_key=u)
                read += 1
        if read:
            card["pasted_reads"] = read
            mem.set_status(4, f"قراءة {read} رابط مُدرَج في الطلب")
            # "follow the file/link" rule: when the user did NOT lock a language
            # explicitly, the output follows the SOURCE content's own language.
            if card.get("lang_locked") is not True and first_content:
                card["language"] = self._detect_lang(first_content)

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
        # 0a) YouTube links → dedicated tool_youtube (transcript/Whisper). Fully
        #     guarded: any failure just falls through to the normal path below,
        #     so non-YouTube links are completely unaffected.
        try:
            from capabilities.tools import tool_youtube
            if tool_youtube.is_youtube_url(url):
                lang = getattr(self, "_yt_lang", None) or "ar"
                res = await tool_youtube.run({"url": url, "lang": lang})
                if getattr(res, "ok", False):
                    txt = (res.data or {}).get("text")
                    if txt and len(txt.strip()) > 200:
                        return txt
        except Exception:
            pass
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
        """Live web research — the search backbone of Layer 4.

        Layer wiring (the end-to-end flow, documented here):
          * Layer 3 (_route): detects a news/recency intent and turns on
            web_search (even for non-academic tasks; academic_search stays off).
          * Layer 4 (_layer_4 → _web_search): engine attempt order is
              SearXNG primary → SearXNG fallbacks → multi-engine (DuckDuckGo +
              Bing + Mojeek + Startpage, queried in parallel and merged) →
              built-in public SearXNG → packaged tool.
            The top 3 links are then read in full (HTML, text/scanned PDFs via
            OCR, images); the rest are kept as snippets. For recency queries it
            injects the current date into the query, applies a time filter
            (SearXNG time_range / DuckDuckGo df), and re-orders results
            newest-first before reading them.
          * Every engine degrades safely — a down service or missing library
            just yields fewer/no sources, never an error.
        """
        card = task.task_card
        query = (card.get("topic") or task.description or "").strip()
        if not query:
            return
        lang = "ar" if card.get("language", "ar") == "ar" else "en"
        limit = self._as_int(card.get("reference_count"), 8) or 8

        # news/recency intent → date-augmented query + time filter + recency sort
        is_recency = self._is_recency_query(
            (card.get("topic") or "") + " " + (task.description or ""))
        sx_time = ddg_df = None
        if is_recency:
            query = self._augment_query_with_date(query, lang)
            sx_time = "week"          # SearXNG time_range
            ddg_df = "w"              # DuckDuckGo df = past week

        # 1) SearXNG primary (env override, else the packaged default port 8888)
        instance = os.environ.get("WEAVER_SEARXNG_URL", "").strip() or "http://127.0.0.1:8888"
        results = self._searx_query(instance, query, lang, limit,
                                    time_range=sx_time, sort_by_date=is_recency)
        used = "searxng:" + instance
        # 2) SearXNG fallbacks (comma-separated list, tried in order)
        if not results:
            for fb in [u.strip() for u in
                       os.environ.get("WEAVER_SEARXNG_FALLBACKS", "").split(",")
                       if u.strip()]:
                r = self._searx_query(fb, query, lang, limit,
                                      time_range=sx_time, sort_by_date=is_recency)
                if r:
                    results = r
                    used = "searxng:" + fb
                    break
        # 3) serverless MULTI-ENGINE (DuckDuckGo + Bing + Mojeek + Startpage,
        #    queried in parallel and merged) — SearXNG-like breadth, NO server.
        if not results:
            multi = self._multi_engine_search(query, lang, limit, df=ddg_df)
            if multi:
                results = multi
                used = "multi-engine"
        # 4) built-in public SearXNG fallbacks — AUTOMATIC, zero setup. Reached
        #    only if everything above failed, so DuckDuckGo's fast path is never
        #    slowed. Each dead instance is memoized (skipped next time); short
        #    timeout so a hanging server can't stall the pipeline.
        if not results:
            for fb in _DEFAULT_SEARXNG_FALLBACKS:
                if fb in _SEARX_DEAD:
                    continue
                r = self._searx_query(fb, query, lang, limit, timeout=5,
                                      time_range=sx_time, sort_by_date=is_recency)
                if r:
                    results = r
                    used = "searxng-default:" + fb
                    break
                _SEARX_DEAD.add(fb)
        # 5) fall back to the packaged tool as a last resort
        if not results:
            results = await self._tool_web_search(query, lang, limit)
            used = "web_search"
        if not results:
            mem.set_status(4, "بحث ويب: لا نتائج (تدهور آمن)")
            return

        # recency queries: put the newest results first before reading top 3
        if is_recency:
            results = self._sort_results_by_recency(results)

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
        # A documentation style needs author/year — which a web result never
        # carries. When the user named a style, look the DOI up so the list can
        # actually be formatted in it. Guarded and bounded; a miss changes
        # nothing.
        try:
            _cs = str(task.task_card.get("citation_style", "")).upper()
            if _cs and _cs not in ("", "UNSPECIFIED", "NONE"):
                _n = self._enrich_sources_for_citation(kept)
                if _n:
                    mem.set_status(5, f"إثراء بيانات التوثيق: {_n} مصدر")
        except Exception as e:
            mem.set_status(5, f"إثراء التوثيق (تخطّي: {e})")
        mem.set_status(5, f"مصداقية: قُبل {len(kept)}، رُفض {len(dropped)}")

    def _descriptive_titles(self, topic, sections_plan, lang):
        """Replace the abstract structural labels ("المبحث 1"/"المطلب 1.1"/
        "Section 1"/"Subsection 1.2") with DESCRIPTIVE, topic-specific titles the
        model proposes — preserving each slot's position/key/level, and giving
        every section a DISTINCT sub-topic (which is what stops sibling sections
        from repeating the same generic definition).

        Uses a SIMPLE numbered line-per-item request (one title per line), which
        a weak model handles far more reliably than nested JSON — a strong model
        produces it just as well, so quality is never capped. Intro/conclusion/
        references are left untouched. Guarded: no model, an empty/garbled reply
        → the original plan is returned unchanged."""
        if not self.llm_fn or not sections_plan:
            return sections_plan
        import re
        abstract_re = re.compile(
            r'^\s*(?:المبحث|المطلب|Section|Subsection)\b', re.I)
        # collect the abstract body slots IN ORDER, each with a role label
        slots, main_no = [], 0        # slots: list of (plan_index, role_text)
        for i, s in enumerate(sections_plan):
            title = (s.get("title") or s.get("heading") or "").strip()
            if not abstract_re.match(title):
                continue
            lvl = int(s.get("level", 1) or 1)
            if lvl <= 1:
                main_no += 1
                role = (f"مبحث رئيسي رقم {main_no}" if lang == "ar"
                        else f"main section #{main_no}")
            else:
                role = (f"مطلب فرعي تحت المبحث {main_no}" if lang == "ar"
                        else f"subsection under section {main_no}")
            slots.append((i, role))
        if not slots:
            return sections_plan          # nothing abstract to rename

        def _clean(t):
            t = (t or "").strip().strip('"“”«»').strip()
            t = re.sub(r'^(?:المبحث|المطلب|Section|Subsection)\b[\s:،.\d]*', '',
                       t, flags=re.I).strip()
            return t

        def _valid(ct):
            # reject empty / single-word / truncated stubs (e.g. a cut-off "تو")
            # so a garbled reply can never leak a broken bullet into the outline.
            return bool(ct) and len(ct) >= 4 and len(ct.split()) >= 2

        def _ask(roles):
            """Ask the model for one descriptive title per role. Returns a list
            (same order) with '' where the reply was missing or invalid."""
            block = "\n".join(f"{n + 1}. {r}" for n, r in enumerate(roles))
            if lang == "ar":
                prompt = (
                    f"أريد عناوين وصفية دقيقة لبحث علمي عن: «{topic}».\n"
                    f"لكل بندٍ في القائمة التالية اكتب عنواناً وصفياً واحداً يخصّ "
                    f"الموضوع فعلاً، ومختلفاً عن البقية (لا تعريفات عامة مكرّرة)، "
                    f"بلا كلمتَي «مبحث»/«مطلب»:\n{block}\n\n"
                    f"أعِد {len(roles)} سطراً فقط، سطراً واحداً لكل عنوان وبنفس "
                    f"الترتيب، كلٌّ يبدأ برقمه هكذا: «1. العنوان».")
            else:
                prompt = (
                    f"I need precise descriptive titles for research on: "
                    f"\"{topic}\".\nFor each item below, write ONE descriptive, "
                    f"topic-specific title, distinct from the others (no repeated "
                    f"general definitions), without the words 'Section'/"
                    f"'Subsection':\n{block}\n\nReturn exactly {len(roles)} lines, "
                    f"one title per line in the same order, each starting with its "
                    f"number: \"1. Title\".")
            try:
                raw = self.llm_fn(prompt, system=self.system_main,
                                  temperature=0.3) or ""
            except Exception:
                return [""] * len(roles)
            out = [""] * len(roles)
            numbered = False
            for line in raw.splitlines():
                line = line.strip()
                if not line:
                    continue
                m = re.match(r'^[\(\[]?(\d{1,3})[\)\].\-:،]\s*(.+)$', line)
                if m:
                    numbered = True
                    n = int(m.group(1))
                    if 1 <= n <= len(roles):
                        ct = _clean(m.group(2))
                        if _valid(ct):
                            out[n - 1] = ct
            if not numbered:      # model ignored numbering → take lines in order
                lines = [re.sub(r'^[\-\*•\d\.\)\(:،\s]+', '', l).strip()
                         for l in raw.splitlines() if l.strip()]
                for k, l in enumerate([x for x in lines if x][:len(roles)]):
                    ct = _clean(l)
                    if _valid(ct):
                        out[k] = ct
            return out

        roles = [r for (idx, r) in slots]
        got = _ask(roles)
        # ONE short retry to fill only the slots still missing a valid title.
        missing = [k for k, t in enumerate(got) if not t]
        if missing and self.llm_fn:
            fill = _ask([roles[k] for k in missing])
            for j, k in enumerate(missing):
                if j < len(fill) and fill[j]:
                    got[k] = fill[j]
        # ALL-OR-NOTHING: rename only when EVERY abstract slot got a valid,
        # topic-specific title. Otherwise keep the clean abstract labels — never
        # a half-renamed mix, and never a truncated stub. Weak models half-fail,
        # and a consistent outline beats a patchy one.
        if any(not t for t in got):
            return sections_plan
        plan = [dict(s) for s in sections_plan]     # copy, don't mutate input
        for k, (idx, role) in enumerate(slots):
            # keep the structural label ("المبحث 1") in front of the descriptive
            # title, the way an Arabic thesis numbers its sections — dropping it
            # lost the numbering the user explicitly asked for.
            _orig = (sections_plan[idx].get("title")
                     or sections_plan[idx].get("heading") or "").strip()
            _new = got[k]
            plan[idx]["title"] = (f"{_orig}: {_new}"
                                  if _orig and not _new.startswith(_orig)
                                  else _new)
        return plan

    def _rich_outline_chunked(self, topic, card, lang, context=""):
        """Build the rich outline in SMALL per-section calls instead of one huge
        generation. A weak/slow on-device model returns an EMPTY completion on a
        big ask (that was the "رد فارغ" + 7-minute retry waste); small asks come
        back reliably and fast. One backbone call (proposed title + main section
        titles), then one small call per main section for its subsections, then a
        small references call. Returns assembled text, or None if the backbone is
        unusable (caller then tries the single-call path, then the flat list).

        Arabic only for now; other languages fall through to the single-call path.
        """
        import os, re
        if not self.llm_fn or lang != "ar":
            return None
        topic = (topic or "").strip()
        if not topic:
            return None
        _mc = self._as_int(card.get("mabhath_count"), 0) or 0
        _mm = self._as_int(card.get("matlab_count"), 0) or 0
        ctx = (context or "").strip()
        ctx_line = ("سياق هذه المحادثة (لتحديد الموضوع إن لزم، ولا تسأل عنه): "
                    + ctx[:800] + "\n\n") if ctx else ""
        try:
            _to = int(os.environ.get("WEAVER_OUTLINE_CHUNK_TIMEOUT", "120")
                      or 120)
        except Exception:
            _to = 120

        def _call(prompt, mx):
            try:
                return self.llm_fn(prompt, system=self.system_main,
                                   temperature=0.4, max_tokens=mx,
                                   timeout=_to) or ""
            except TypeError:
                try:
                    return self.llm_fn(prompt, system=self.system_main,
                                       temperature=0.4) or ""
                except Exception:
                    return ""
            except Exception:
                return ""

        def _clean_line(s):
            return s.strip().lstrip("-*•").strip().lstrip("0123456789").lstrip(
                ".)( \t").strip()

        # 1) BACKBONE: proposed title + main section (مبحث) titles.
        count_req = (f"اجعل عدد المباحث الرئيسية {_mc} بالضبط.\n" if _mc else
                     "اجعل عدد المباحث الرئيسية بين 3 و5 بحسب الموضوع.\n")
        bb = _call(
            ctx_line + f"لبحثٍ عن موضوع: «{topic}».\n{count_req}"
            "أعطِ الهيكل الأعلى فقط: سطر «العنوان: <عنوان مقترح للبحث>»، ثم سطرٌ "
            "لكل مبحث رئيسي بصيغة «مبحث: <عنوان موضوعي دالٌّ ودقيق>» (بلا أرقام "
            "وبلا مطالب وبلا شرح). سطر واحد لكل عنصر، ولا تكتب أي نصٍّ آخر.", 600)
        if not bb or not bb.strip():
            return None
        title, mains = "", []
        for line in bb.splitlines():
            s = _clean_line(line)
            if not s:
                continue
            if s.startswith("العنوان") and ":" in s:
                title = s.split(":", 1)[1].strip()
            elif s.startswith("مبحث") and ":" in s:
                t = s.split(":", 1)[1].strip()
                if t:
                    mains.append(t)
        if _mc:
            mains = mains[:_mc]
        mains = [m for m in mains if m][:30]
        if not mains:
            return None

        # 2) DETAIL each main section with its subsections (مطالب).
        ordn = ["الأول", "الثاني", "الثالث", "الرابع", "الخامس", "السادس",
                "السابع", "الثامن", "التاسع", "العاشر", "الحادي عشر",
                "الثاني عشر"]
        parts = []
        if title:
            parts.append(f"عنوان البحث: {title}")
        parts += ["المقدمة", "- تمهيد للموضوع وبيان أهميته.",
                  "- إشكالية البحث وأسئلته.", "- أهداف البحث.",
                  "- منهج البحث."]
        for i, mt in enumerate(mains):
            label = f"المبحث {ordn[i]}" if i < len(ordn) else f"المبحث {i + 1}"
            parts.append(f"{label}: {mt}")
            mreq = (f"اذكر {_mm} مطالب بالضبط" if _mm
                    else "اذكر 3 إلى 4 مطالب")
            det = _call(
                f"في بحثٍ عن «{topic}»، وضمن المبحث: «{mt}».\n{mreq}، كلُّ مطلبٍ "
                "بعنوانٍ دالٍّ يتبعه سطرٌ تعريفي موجز؛ وإن ناسب الموضوع (قرآني/"
                "علمي) فأشِر إلى الآية أو الدليل أو التطابق العلمي بإيجاز. اكتب "
                "كل مطلب في سطر بصيغة «مطلب: <العنوان> — <شرح موجز>»، ولا تكتب "
                "أي نصٍّ آخر.", 600)
            got = 0
            for line in (det or "").splitlines():
                s = _clean_line(line)
                if not s:
                    continue
                if s.startswith("مطلب") and ":" in s:
                    s = s.split(":", 1)[1].strip()
                if len(s) >= 4:
                    parts.append(f"- {s}")
                    got += 1
                if _mm and got >= _mm:
                    break
        parts += ["الخاتمة", "- خلاصة النتائج وأبرز التوصيات."]

        # 3) REFERENCES: a small call for named, concrete sources.
        refs = _call(
            f"لبحثٍ عن «{topic}»، اذكر من 4 إلى 6 مصادر ومراجع مقترحة بأسماء "
            "محدّدة (كتب/مؤلّفين/دراسات)، كلُّ مرجعٍ في سطرٍ يبدأ بـ«- »، بلا أي "
            "نصٍّ آخر.", 400)
        ref_lines = [("- " + _clean_line(l)) for l in (refs or "").splitlines()
                     if _clean_line(l)]
        parts.append("قائمة المصادر والمراجع")
        parts += (ref_lines[:8] if ref_lines
                  else ["- مصادر ومراجع تُختار بحسب دقّة الموضوع."])

        text = "\n".join(parts).strip()
        if len(text) < 200 or len([l for l in text.splitlines()
                                   if l.strip()]) < 6:
            return None
        return text

    def _rich_outline(self, topic, card, lang, context=""):
        """DESIGN a complete, richly-detailed research outline by UNLEASHING the
        model on the topic — instead of only naming pre-fixed structural slots.
        The model proposes a title, a structured introduction (تمهيد/إشكالية/
        أهداف/منهج), each main section with annotated sub-points, topic-relevant
        evidence hints (آيات/أدلة/تطابق علمي where fitting), a conclusion, and a
        suggested references list. Honors an explicit "N مباحث × M مطالب" count.

        This is the whole point of the outline path: the SAME model that returns
        a thin heading list when asked slot-by-slot returns a deep, useful outline
        when asked to author the structure itself — one call, no search.

        Returns ready-to-render markdown-ish text, or None when the model is
        unavailable or the reply is too thin (caller then falls back to the flat
        structural list, so nothing breaks and weak models still get output).
        Sets self._rich_reason to a short, on-screen-safe explanation so a
        fallback is never silent."""
        self._rich_reason = ""
        if not self.llm_fn:
            self._rich_reason = "لا نموذج"
            return None
        topic = (topic or "").strip()
        if not topic:
            self._rich_reason = "لا موضوع"
            return None
        import os, re
        # ONE call by default (like OpenClaw): with DeepSeek thinking disabled the
        # model returns the full outline in a single call fast (~40s), so the
        # multi-call chunked path (5 calls) is now only an opt-in fallback for
        # servers that still choke on one big generation. Enable with
        # WEAVER_OUTLINE_CHUNKED=1.
        if os.environ.get("WEAVER_OUTLINE_CHUNKED", "0").lower() in (
                "1", "true", "yes", "on"):
            try:
                _ch = self._rich_outline_chunked(topic, card, lang, context)
            except Exception:
                _ch = None
            if _ch:
                self._rich_reason = "نجح (دفعات)"
                return _ch
        _mc = self._as_int(card.get("mabhath_count"), 0) or 0
        _mm = self._as_int(card.get("matlab_count"), 0) or 0
        context = (context or "").strip()
        if lang == "ar":
            # a follow-up like "اجعلها 3 مباحث" carries no subject of its own —
            # recover it from THIS conversation's history so the model never asks
            # "ما الموضوع؟" or treats the format instruction as the subject.
            ctx_line = ""
            if context:
                ctx_line = (
                    "سياق هذه المحادثة (استعمِله لتحديد موضوع البحث إن كان الطلب "
                    "الحالي تعليمةَ تنسيق — كعدد المباحث — دون ذكر الموضوع، ولا "
                    "تسأل عن الموضوع ولا تعامل التعليمة كأنها الموضوع):\n"
                    f"{context[:1200]}\n\n")
            count_line = ""
            if _mc:
                count_line = (
                    f"اجعل الهيكل {_mc} مباحث رئيسية بالضبط، وكل مبحث {_mm or 3} "
                    f"مطالب، وتحت كل مطلب نقاط فرعية مرقّمة (أولاً، ثانياً، "
                    f"ثالثاً).\n")
            prompt = (
                f"أنت باحث أكاديمي متمرّس. {ctx_line}"
                f"صمّم هيكلاً بحثياً عميقاً ومتكاملاً لموضوع: «{topic}».\n"
                f"{count_line}"
                "المطلوب هيكلٌ (رؤوس أقسام منظّمة) لا بحثٌ مكتوب، فاجعله يتضمّن:\n"
                "- عنواناً مقترحاً دقيقاً للبحث.\n"
                "- مقدمة مقسّمة إلى: تمهيد، إشكالية، أهداف، منهج.\n"
                "- المباحث، كلٌّ بعنوان دالٍّ وتحته مطالب، وكل مطلب تحته نقاط "
                "فرعية.\n"
                "- إذا كان الموضوع شرعياً/قرآنياً فأشِر إلى الآية بموضعها هكذا "
                "[السورة: رقم] مع نصفِ سطرٍ لوجه الدلالة؛ وإن كان علمياً فاذكر وجه "
                "التطابق في نصف سطر.\n"
                "- خاتمة (خلاصة، نتائج، توصيات).\n"
                "- قائمة مصادر ومراجع بأسماء محدّدة (كتب/مؤلّفين/دراسات).\n\n"
                "قواعد صارمة للإخراج:\n"
                "• كل نقطة سطرٌ واحد موجزٌ ومركّز (لا فقرة، لا شرح مطوّل، لا نقل "
                "الآية كاملةً) — فهذا هيكلٌ لا محتوى.\n"
                "• أكمِل الهيكل كاملاً حتى قائمة المراجع؛ لا تتوقّف في المنتصف. "
                "الإيجاز في كل نقطة هو ما يضمن اكتماله.\n"
                "• عناوين واضحة كنصٍّ عادي («المبحث الأول: ...»، «المطلب الأول: "
                "...») ونقاط بادئة بـ«- »، دون تمهيد كلامي منك ودون رموز «#». "
                "اكتب بالعربية الفصحى.")
        else:
            ctx_line = ""
            if context:
                ctx_line = (
                    "Context of this conversation (use it to determine the "
                    "research SUBJECT if the current request is a formatting "
                    "instruction — like the number of sections — without naming "
                    "the topic; do not ask for the topic and do not treat the "
                    f"instruction as the topic):\n{context[:1200]}\n\n")
            count_line = ""
            if _mc:
                count_line = (
                    f"Make it exactly {_mc} main sections, each with {_mm or 3} "
                    f"subsections, and numbered sub-points under each.\n")
            prompt = (
                f"You are an experienced academic researcher. {ctx_line}"
                f"Design a deep, complete research OUTLINE (organized headings, "
                f"not a written paper) for: \"{topic}\".\n{count_line}"
                "Include: a proposed precise title; an introduction split into "
                "background, problem statement, objectives, methodology; the main "
                "sections, each with subsections and sub-points; topic-relevant "
                "evidence hints where fitting (a half-line each); a conclusion; and "
                "a references list with specific named sources.\n\n"
                "Strict output rules:\n"
                "- Each point is ONE short focused line (not a paragraph, no long "
                "explanation) — this is an outline, not content.\n"
                "- COMPLETE the whole outline through the references; never stop "
                "midway. Being concise per point is what keeps it complete.\n"
                "- Plain-text headings (\"Section 1: ...\") and \"- \" bullets, no "
                "conversational preamble and no '#' symbols.")
        # a rich outline is a long generation; a slow on-device model needs more
        # than the default 180s or it times out and silently falls back to the
        # thin list. Give it a generous, configurable budget (WEAVER_RICH_TIMEOUT).
        try:
            _rto = int(os.environ.get("WEAVER_RICH_TIMEOUT", "420") or 420)
        except Exception:
            _rto = 420
        # with thinking disabled the whole budget goes to the answer, so give it
        # room for a COMPLETE deep outline (references included) instead of being
        # cut off at finish_reason=length. Configurable via WEAVER_RICH_MAXTOK.
        try:
            _rmax = int(os.environ.get("WEAVER_RICH_MAXTOK", "8000") or 8000)
        except Exception:
            _rmax = 8000
        # LIVE STREAMING: show the outline as it is written (like OpenClaw) by
        # forwarding each token to the progress stream as a "delta" event. Guarded
        # by WEAVER_STREAM (default on) and only meaningful when a progress
        # callback is attached. A first "delta_start" lets the UI open a live area.
        _stream_on = os.environ.get("WEAVER_STREAM", "1").lower() not in (
            "0", "false", "no")
        _od = None
        if _stream_on and getattr(self, "_progress", None):
            self._emit("delta_start", "", "")

            def _od(piece):
                self._emit("delta", "", piece)
        try:
            raw = self.llm_fn(prompt, system=self.system_main,
                              temperature=0.4, max_tokens=_rmax,
                              timeout=_rto, on_delta=_od) or ""
        except TypeError:
            # older llm_fn without on_delta/timeout kwargs
            try:
                raw = self.llm_fn(prompt, system=self.system_main,
                                  temperature=0.4, max_tokens=2200) or ""
            except Exception as e:
                self._rich_reason = f"خطأ نداء: {type(e).__name__}"
                return None
        except Exception as e:
            self._rich_reason = f"تعذّر النداء: {type(e).__name__}"
            return None
        txt = (raw or "").replace("```", "").strip()
        # drop a leading conversational preamble ("بالتأكيد، إليك ..." / "Sure, ")
        txt = re.sub(r'^\s*(?:بالتأكيد|تمام|حسناً|حسنا|إليك|طبعاً|بكل سرور|'
                     r'sure|certainly|here(?:\'s| is))[^\n]*\n+', '', txt,
                     flags=re.I).strip()
        # validation: a real outline is substantial and multi-line
        lines = [l for l in txt.splitlines() if l.strip()]
        if len(txt) < 200 or len(lines) < 6:
            self._rich_reason = (f"ردّ قصير ({len(txt)} حرف/{len(lines)} سطر)"
                                 if txt else "ردّ فارغ")
            return None
        self._rich_reason = "نجح"
        return txt

    @staticmethod
    def _length_directive(card=None, n_sections=1, lang="ar"):
        """What to put in the writer prompt's "Required length" slot.

        That slot read card["page_count"] — a key NOTHING in the pipeline ever
        sets — so the writer was handed an EMPTY length on every section and had
        no idea how long the document should be; the length was only chased
        afterwards by the expansion loop. The real target lives in
        target_words / target_pages / max_words; this turns it into a per-section
        budget the writer can act on. Returns "" when no length was requested,
        leaving the previous behaviour untouched."""
        card = card or {}
        total = card.get("target_words")
        pages = card.get("target_pages")
        mx = card.get("max_words")
        if not total and not pages and not mx:
            return ""
        n = max(1, int(n_sections or 1))
        base = total or mx or 0
        share = int(base / n) if base else 0
        if lang == "en":
            bits = []
            if pages:
                bits.append(f"{pages} pages")
            if total:
                bits.append(f"~{total} words in total")
            if share:
                bits.append(f"about {share} words for THIS section")
            if mx:
                bits.append(f"never exceeding {mx} words overall")
            return " — ".join(bits)
        bits = []
        if pages:
            bits.append(f"{pages} صفحة")
        if total:
            bits.append(f"نحو {total} كلمة للمستند كله")
        if share:
            bits.append(f"أي نحو {share} كلمة لهذا القسم")
        if mx:
            bits.append(f"وألّا يتجاوز المستند {mx} كلمة")
        return " — ".join(bits)

    @staticmethod
    def _bridge_policy(card=None, request=""):
        """How to treat the short bridge a مبحث carries above its مطالب.

        Returns {"mode": "auto"|"none"|"custom", "max_words": int}. The user's
        own instruction wins — including "بلا تمهيد", which removes it entirely
        (and saves the model call). Otherwise it is capped automatically: a
        parent that runs long is a parent that has started writing its
        subsections, which is how مبحث 3 ended up 371 words against مبحث 2's 180
        and printed every مطلب twice.
        """
        import os as _os
        try:
            cap = int(_os.environ.get("WEAVER_BRIDGE_MAXWORDS", "120") or 120)
        except Exception:
            cap = 120
        blob = " ".join([
            str(request or ""),
            " ".join(str(r.get("text", "")) for r in ((card or {}).get(
                "requirements") or []) if isinstance(r, dict)),
        ]).lower()
        if not blob.strip():
            return {"mode": "auto", "max_words": cap}
        # explicit removal
        _drop = ("بلا تمهيد", "بدون تمهيد", "دون تمهيد", "احذف التمهيد",
                 "لا تمهيد", "بلا مقدمة للمبحث", "دون مقدمة للمبحث",
                 "no bridge", "no lead-in", "without an introduction to each")
        if any(k in blob for k in _drop):
            return {"mode": "none", "max_words": 0}
        # an explicit length for the bridge itself
        import re
        m = re.search(r'(?:تمهيد|مقدمة\s+(?:كل\s+)?مبحث|bridge|lead-?in)'
                      r'[^.\n]{0,40}?(\d{2,4})\s*(?:كلمة|كلمات|words?)', blob)
        if not m:
            m = re.search(r'(\d{2,4})\s*(?:كلمة|كلمات|words?)[^.\n]{0,30}?'
                          r'(?:تمهيد|لكل مبحث|bridge)', blob)
        if m:
            try:
                n = int(m.group(1))
                if 20 <= n <= 1000:
                    return {"mode": "custom", "max_words": n}
            except Exception:
                pass
        return {"mode": "auto", "max_words": cap}

    @staticmethod
    def _cap_bridge(body, max_words):
        """Hard-enforce the bridge length, cutting at a sentence boundary so the
        text never ends mid-thought. Deterministic on purpose: the writing
        prompt already asks for 2-4 sentences and a model still overran it."""
        if not body or not max_words:
            return body
        words = body.split()
        if len(words) <= max_words:
            return body
        clipped = " ".join(words[:max_words])
        # back off to the last complete sentence
        cut = max(clipped.rfind(c) for c in (".", "؟", "!", "؛"))
        if cut > len(clipped) * 0.4:
            return clipped[:cut + 1].strip()
        return clipped.rstrip(" ,،") + "."

    @staticmethod
    def _trim_parent_bridge(body):
        """A PARENT section (a مبحث followed by its مطالب) must be a short
        bridge. Told that, a model still sometimes writes the whole chapter —
        emitting its own "المطلب 3.1: …" sub-headings and their content inside
        the bridge. The real مطالب are then written again as proper sections
        with DIFFERENT (descriptive) titles, so every مطلب appeared twice under
        two conflicting names.

        Cut the body at the first line that reads as one of those invented
        child headings. A genuine bridge never opens a line with
        "المطلب 3.1:", so this cannot damage legitimate prose. Returns the body
        unchanged when no such line exists."""
        import re
        if not body:
            return body
        lines = body.split("\n")
        _kw = r'(?:المبحث|المطلب|الفصل|المحور|المبحثُ|Section|Subsection|Chapter)'
        _ord = (r'(?:[\d\u0660-\u0669]+(?:[.\-‑][\d\u0660-\u0669]+)*|'
                r'ال(?:أول|ثاني|ثالث|رابع|خامس|سادس|سابع|ثامن|تاسع|عاشر)\w*)')
        _enum = (r'(?:أولا|أولاً|ثانيا|ثانياً|ثالثا|ثالثاً|رابعا|رابعاً|'
                 r'خامسا|خامساً|سادسا|سادساً)')
        # a heading line, in any of the shapes a model actually produces:
        #   "المطلب 3.1: …" · "المطلب الأول: …" · "أولاً: …" · "3.1 …"
        #   optionally wrapped in markdown (#, **, __)
        _pre = r'^\s*(?:#{1,6}\s*)?(?:\*\*|__)?\s*'
        pat_colon = re.compile(
            _pre + r'(?:' + _kw + r'\s*' + _ord + r'|' + _enum + r')'
            r'\s*(?:\*\*|__)?\s*[:：\-–]')
        # the same without a colon is a heading only when the line is SHORT —
        # otherwise "المطلب الأول يقتضي من الباحث …" is ordinary prose
        pat_bare = re.compile(
            _pre + r'(?:' + _kw + r'\s*' + _ord +
            r'|[\d\u0660-\u0669]+[.\-‑][\d\u0660-\u0669]+)'
            r'\s*(?:\*\*|__)?\s*$|'
            + _pre + r'(?:' + _kw + r'\s*' + _ord +
            r'|[\d\u0660-\u0669]+[.\-‑][\d\u0660-\u0669]+)\s+\S')

        def _is_heading(ln):
            t = ln.strip()
            if not t:
                return False
            if pat_colon.match(t):
                return True
            return bool(pat_bare.match(t)) and len(t.split()) <= 10

        for i, ln in enumerate(lines):
            if _is_heading(ln):
                kept = "\n".join(lines[:i]).strip()
                # keep the trimmed bridge only if something real remains
                return kept if kept else body
        return body

    @staticmethod
    def _promote_heading_from_body(title, body):
        """When an abstract structural heading ("المطلب 1.1") is followed by a
        body whose first line spells out the REAL title ("المطلب 1.1: مفهوم
        الذكاء الاصطناعي ومكانته…"), promote that line to be the heading and
        drop it from the body. This turns a bare numeric outline into a
        descriptive one AND removes the duplicated line the reader used to see
        under every heading. Returns (title, body) unchanged when it does not
        clearly apply."""
        t = (title or "").strip()
        b = (body or "").lstrip()
        if not t or not b:
            return title, body
        # only for the abstract counted labels
        if not t.startswith(("المبحث", "المطلب", "Section", "Subsection")):
            return title, body
        first = b.split("\n", 1)[0].strip().lstrip("#").strip()
        if not first.startswith(t):
            return title, body
        rest = first[len(t):].lstrip()
        if rest[:1] not in (":", "："):
            return title, body
        desc = rest[1:].strip()
        # a real sub-title: a few words, not a whole paragraph
        if not (2 <= len(desc.split()) <= 20):
            return title, body
        new_title = f"{t}: {desc}"
        new_body = b.split("\n", 1)[1] if "\n" in b else ""
        return new_title, new_body.strip()

    @staticmethod
    def _strip_meta_preamble(text):
        """Drop a leading sentence that talks ABOUT the writing task instead of
        being content — the "إليك التوسعة المطلوبة… أضفتُ نحو 300 كلمة" /
        "أهلاً بك. سأقوم بتوسيع الفقرة" leak that the length-expansion loop
        used to paste straight into the document. Conservative: only a SHORT
        leading line carrying a real meta marker is removed, so genuine prose
        is never touched. Safe on empty input."""
        if not text:
            return text
        meta = ("إليك", "أضفت", "أضفتُ", "سأقوم", "قمت بتوسيع", "قمتُ بتوسيع",
                "التوسعة", "التوسيع المطلوب", "كما طلبت", "بناءً على طلبك",
                "مع الحفاظ على", "here is", "here's", "i have expanded",
                "i've expanded", "as requested", "sure,", "certainly,")
        lines = text.split("\n")
        out, dropped = [], 0
        for i, ln in enumerate(lines):
            t = ln.strip()
            if dropped >= 2 or not t:
                out.append(ln)
                continue
            if i <= 2 and len(t.split()) <= 45 and any(
                    m in t.lower() for m in meta):
                dropped += 1
                continue          # a meta line about the task → drop it
            out.append(ln)
        return "\n".join(out).strip()

    @staticmethod
    def _clean_section_body(body, title):
        """Tidy a written section body: drop a leading duplicate of its own
        heading (the "المطلب 1.3: …" leak), and strip leaked markdown heading
        markers (## …) that the docx builder would otherwise show literally.
        Prose content is preserved. Safe on empty input."""
        import re
        if not body:
            return body
        b = body.lstrip()
        t = (title or "").strip()
        # Strip leaked markdown heading markers FIRST. They used to be removed
        # at the END, so a body opening with "## المطلب 2.2: …" never matched the
        # duplicate-heading test below (it starts with "#", not with the title),
        # and the heading survived — printing twice under its own heading.
        b = re.sub(r'(?m)^[ \t]*#{1,6}[ \t]*', '', b).lstrip()
        # strip a leading duplicate of the heading ONLY when it reads as a
        # heading (title then ":"/"："/line-break/end) — never when the title
        # naturally opens the first sentence (e.g. "التركيب … هو الوحدة …").
        if t and b.startswith(t):
            _rest = b[len(t):]
            _after = _rest.lstrip()
            if _rest[:1] == "\n" or _after[:1] in (":", "：") or _after == "":
                b = _rest.lstrip(" :：،.-\n")
        # a leading abstract label glued to the start ("المطلب 1.3: ")
        b = re.sub(r'^\s*(?:المبحث|المطلب|Section|Subsection)\s*[\d.]*\s*'
                   r'[:：]?\s*', '', b)
        # markdown heading markers at line starts → keep text, drop the hashes
        b = re.sub(r'(?m)^[ \t]*#{1,6}[ \t]*', '', b)
        return b.strip()

    def _model_structure(self, topic, request, card, lang="ar"):
        """THE MODEL designs the document structure to FIT the request — instead
        of forcing ONE academic template (intro/body/conclusion/references) onto
        every task. A simple ask (a comparison/table, a definition, a short
        piece) gets a small structure with no forced مقدمة/خاتمة/مراجع; a real
        بحث/تقرير gets its proper academic structure; the model decides which.
        Returns a sections plan [{"title","level"}] and records
        card["needs_references"], or None on any miss (caller keeps the template
        builder as fallback). Additive and fully guarded."""
        if not self.llm_fn:
            return None
        try:
            import os
            from core.llm import extract_json
            _ctx = self._conversation_context(request) or ""
            prompt = (
                "أنت مصمّم بنية مستندات خبير. صمّم البنية المناسبة تماماً لهذا "
                "الطلب — دون فرض قالبٍ جاهز. أعِد JSON فقط:\n"
                '{"sections":[{"title":"عنوان القسم الموضوعي","level":1أو2}],'
                '"needs_references":true|false}\n'
                "قواعد حاسمة:\n"
                "- لاءم البنية مع الطلب فعلاً: طلبٌ بسيط (جدول مقارنة، تعريف، "
                "شرح، فقرة، إجابة قصيرة) = بنية صغيرة (قسم أو أقسام قليلة قصيرة) "
                "بلا مقدمة/خاتمة/توصيات/مراجع إن لم تلزم. بحث أو تقرير أكاديمي = "
                "بنية كاملة مناسبة (مقدمة، مباحث بعناوين موضوعية محدّدة، خاتمة، "
                "ومراجع فقط إن كان يستشهد بمصادر).\n"
                "- العناوين موضوعية محدّدة تخصّ الموضوع، لا تسميات فارغة مثل "
                "«المبحث 1» أو «العرض».\n"
                "- needs_references=true فقط إذا كان العمل يستشهد فعلاً بمصادر "
                "خارجية؛ خلا ذلك false.\n"
                + (f"\nسياق المحادثة:\n{_ctx[:1500]}\n" if _ctx else "")
                + f"\nالطلب:\n{(request or '')[:1200]}\nالموضوع: {topic}")
            try:
                _to = int(os.environ.get("WEAVER_STRUCT_TIMEOUT", "60") or 60)
            except Exception:
                _to = 60
            raw = self.llm_fn(prompt, system=self.system_main,
                              temperature=0.3, max_tokens=1200, timeout=_to) or ""
            data = extract_json(raw)
            secs = data.get("sections") if isinstance(data, dict) else None
            if not isinstance(secs, list) or not secs:
                return None
            plan = []
            for s in secs:
                if not isinstance(s, dict):
                    continue
                t = str(s.get("title", "")).strip()
                if not t:
                    continue
                try:
                    lvl = int(s.get("level", 1))
                except (TypeError, ValueError):
                    lvl = 1
                plan.append({"title": t[:200], "level": 1 if lvl < 2 else 2})
            if not plan:
                return None
            card["needs_references"] = bool(data.get("needs_references"))
            return plan
        except Exception:
            return None

    async def _layer_6(self, task: Task, mem: TaskMemory):
        """٦: الصياغة — بناء البنية ثم المنهجية ثم كتابة كل قسم.
        كل خطوة تستخدم مهارة/قالباً موجوداً؛ عند غياب النموذج تبقى مسودة فارغة."""
        task.status = TaskStatus.LAYER_6
        mem.set_status(6, "صياغة البحث")
        card = task.task_card
        lang = card.get("language", "ar")
        # adapt every writer to the running model's ceiling (small/medium/large)
        # so it works reliably at its own peak. Set once; read by this layer and
        # by weak_model_support below. Additive — default stays "medium".
        try:
            card.setdefault("model_strength", self._model_strength())
        except Exception:
            pass
        # detect Islamic content once so the writer is guided to use the correct
        # Quran/Hadith marks (enforced again after writing by _apply_islamic_marks)
        try:
            card.setdefault("islamic", self._is_islamic_content(
                f"{card.get('topic','')} "
                f"{self._strip_injected_memory(task.description)}"))
        except Exception:
            pass

        # ── YouTube path: produce the summary / transcript directly, with NO
        #    research structure or methodology, then return early.
        yt = card.get("youtube")
        if yt:
            transcript = (yt.get("transcript") or "").strip()
            mode = yt.get("mode", "summary")
            # Fetch failed upstream (no captions / throttled / lib missing):
            # emit a clear, honest, actionable message — never an empty reply
            # and never a fake research report.
            if not transcript and yt.get("error"):
                why = yt.get("error")
                body_txt = (
                    f"تعذّر جلب نص هذا الفيديو من يوتيوب ({why}).\n\n"
                    "**الأسباب المحتملة:**\n\n"
                    "- الفيديو لا يحتوي ترجمة/نصاً تلقائياً (captions مُعطّلة).\n"
                    "- يوتيوب حجب الطلب مؤقتاً بسبب طلبات متتالية — انتظر قليلاً "
                    "ثم أعد المحاولة، ويُفضّل عدم فتح عدة محادثات في آنٍ واحد.\n"
                    "- مكتبة youtube-transcript-api غير مثبّتة على الجهاز "
                    "(pip install youtube-transcript-api)."
                )
                task.sections = [{"heading": "تعذّر التفريغ", "body": body_txt}]
                # web/terminal reply as real Markdown (heading + body)
                task.draft = "## تعذّر التفريغ\n\n" + body_txt
                mem.set_status(6, "يوتيوب: تعذّر جلب النص")
                return
            # Clean (no-timestamp) text drives the summary, so the summary is real
            # prose — never a copy of the timestamped transcript.
            plain = (yt.get("transcript_plain") or "").strip() or transcript
            # Resolve the SUMMARY output language per the rule: explicit name >
            # source/original language of the video > the language the request
            # itself is written in.
            _lk = yt.get("out_lang_kind")
            _ln = yt.get("out_lang_name")
            _en = (yt.get("req_lang") or "ar") == "en"
            if _lk == "source":
                _lang_instr = "بنفس لغة النص أدناه (لغته الأصلية)"
            elif _lk == "name":
                _lang_instr = "باللغة " + (_ln or "العربية")
            else:
                _lang_instr = "بالإنجليزية" if _en else "بالعربية"
            _h_sum = "Summary" if (_lk == "name" and _ln == "الإنجليزية") \
                or (_lk is None and _en) else "الخلاصة"
            _h_tr = "Video transcript" if _h_sum == "Summary" \
                else "التفريغ النصي للفيديو"
            sections = []
            # 1) TRANSCRIPT FIRST (when requested) — always verbatim, its own lang
            if mode in ("transcript", "both"):
                sections.append({"heading": _h_tr,
                                 "body": transcript, "kind": "transcript"})
            # 2) SUMMARY AFTER the transcript (only when requested)
            if mode in ("summary", "both"):
                summ = ""
                if self.llm_fn and plain:
                    try:
                        summ = self.llm_fn(
                            "لخّص النص التالي " + _lang_instr + " في نقاط واضحة "
                            "ومرتّبة، دون مقدمة بحثية أو مباحث أو مراجع. اجعل كل "
                            "نقطة سطراً يبدأ بـ \"- \":\n\n" + plain[:12000],
                            system=self.system_main, temperature=0.4) or ""
                    except Exception as e:
                        mem.set_status(6, f"يوتيوب (تخطّي التلخيص: {e})")
                summ = summ.strip()
                if summ:
                    sections.append({"heading": _h_sum, "body": summ,
                                     "kind": "summary"})
                elif mode == "summary":
                    # summary-only and generation failed → give the clean text
                    # (not the timestamped dump) with an honest note.
                    note = (plain[:4000] + ("…" if len(plain) > 4000 else ""))
                    sections.append({
                        "heading": _h_tr,
                        "body": "تعذّر توليد ملخّص تلقائي الآن؛ في ما يلي نصّ "
                                "الفيديو:\n\n" + note, "kind": "summary"})
                else:
                    # "both": transcript is already shown → just note the miss.
                    sections.append({"heading": _h_sum,
                                     "body": "تعذّر توليد الملخّص تلقائياً الآن.",
                                     "kind": "summary"})
            task.sections = [{"heading": s["heading"], "body": s["body"]}
                             for s in sections]
            # Web/terminal reply (task.draft) as real Markdown so the chat UI
            # renders it like the exported file: "##" headings, each verbatim
            # "[MM:SS]" transcript line on its own line, and a faint "---" divider
            # before the summary that follows the transcript. task.sections keeps
            # its own (already-correct) formatting for the exported file.
            parts = []
            for i, s in enumerate(sections):
                body = s["body"]
                if s.get("kind") == "transcript":
                    body = "\n\n".join(ln.strip() for ln in body.split("\n")
                                       if ln.strip())
                block = f"## {s['heading']}\n\n{body}"
                if i > 0 and sections[i - 1].get("kind") == "transcript":
                    block = "---\n\n" + block
                parts.append(block)
            task.draft = "\n\n".join(parts).strip()
            mem.set_status(6, f"يوتيوب: أُنتج ({mode}، {len(sections)} قسم)")
            return

        # ── scope limits (references-only / part-only handled here; outline-only
        #    after the structure is built below) ──
        scope = card.get("scope")
        scopes = set(card.get("scopes") or ([scope] if scope else []))

        # composite (no-write): references + outline together → one document with
        # the outline block AND the references block. Placed before the single
        # scopes so the combined ask isn't collapsed to references-only.
        if {"references", "outline"} <= scopes and "part" not in scopes:
            out_head = "هيكل العمل" if lang == "ar" else "Outline"
            ref_head = "المراجع والدراسات" if lang == "ar" else "References"
            _topic = card.get("topic") or self._current_request(task.description)
            _ctx = self._conversation_context(task.description)
            _ob = None
            try:
                _ob = self._rich_outline(_topic, card, lang, context=_ctx)
            except Exception:
                _ob = None
            if not _ob:
                _sp = card.get("sections")
                if not _sp:
                    try:
                        _pl = self._skill_call("research_structure", "structures",
                                               "build_structure", card, lang)
                        _sp = (_pl or {}).get("sections") or []
                    except Exception:
                        _sp = []
                try:
                    _sp = self._descriptive_titles(_topic, _sp, lang)
                except Exception:
                    pass
                _ol = []
                for sec in _sp:
                    _lvl = int(sec.get("level", 1) or 1)
                    _ti = sec.get("title") or sec.get("heading") or ""
                    if _ti:
                        _ol.append(("  " * max(0, _lvl - 1)) + "- " + _ti)
                _ob = "\n".join(_ol)
            _rb = self._format_references_only(card, lang)
            task.sections = [{"heading": out_head, "body": _ob},
                             {"heading": ref_head, "body": _rb}]
            task.draft = f"## {out_head}\n\n{_ob}\n\n## {ref_head}\n\n{_rb}"
            mem.set_status(6, "إخراج: هيكل + مراجع")
            return

        if scope == "references":
            head = "المراجع والدراسات" if lang == "ar" else "References"
            body = self._format_references_only(card, lang)
            task.sections = [{"heading": head, "body": body}]
            task.draft = f"## {head}\n\n{body}"
            mem.set_status(6, "إخراج: مراجع/دراسات فقط")
            return

        # techniques for the model strength — shown in the tool-call/thinking UI,
        # never written into the output document. We already write per-section.
        try:
            card["reliability"] = self._skill_call(
                "weak_model_support", "weak_model_support", "reliability_plan",
                card.get("model_strength", "medium"))
        except Exception:
            pass

        # 1) البنية — يقرّرها النموذج لتلائم الطلب (لا قالب مفروض على الكل). طلبٌ
        #    بسيط (جدول/تعريف) يأخذ بنية صغيرة بلا مقدمة/خاتمة/مراجع؛ بحثٌ يأخذ
        #    بنيته الأكاديمية. القالب الجاهز (build_structure) يبقى ارتداداً فقط
        #    حين يتعذّر النموذج. الأقسام الصريحة (عدد مباحث/مطالب) تتجاوزه لاحقاً.
        sections_plan = card.get("sections")
        if not sections_plan and scope not in ("outline", "references", "part") \
                and not (scope == "plan" or "plan" in scopes):
            try:
                _ms = self._model_structure(
                    card.get("topic", "") or task.description,
                    self._current_request(task.description), card, lang)
            except Exception:
                _ms = None
            if _ms:
                sections_plan = _ms
                card["sections"] = sections_plan
                card["structure_source"] = "model"
                mem.set_status(6, f"بنية يقرّرها النموذج ({len(_ms)} قسماً)")
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

        # research proposal (خطة بحثية/مقترح): use the standard proposal sections
        # (problem, questions, objectives, significance, hypotheses, methodology,
        # scope, terms, prior studies, proposed structure) and write them — a
        # proposal is a real document, distinct from a bare outline.
        if scope == "plan" or "plan" in scopes:
            sections_plan = self._proposal_sections(lang)
            card["sections"] = sections_plan

        # explicit counts ("3 مباحث كل منها 3 مطالب", understood by the intent
        # router) → build the structure to EXACTLY that shape before naming it.
        _mc = card.get("mabhath_count")
        if _mc and not (scope == "plan" or "plan" in scopes):
            sections_plan = self._counted_structure(
                lang, self._as_int(_mc, 1) or 1, self._as_int(card.get("matlab_count"), 0) or 0)
            card["sections"] = sections_plan
            # the counted plan REPLACED whatever the model had designed, so its
            # titles are the abstract "المبحث 1"/"المطلب 1.1" slots again. Clear
            # the "model" provenance, otherwise the descriptive-naming step
            # below skips them and every مبحث ships without a real title.
            card["structure_source"] = "counted"
            mem.set_status(6, f"بنية بالطلب: {_mc} مبحث × "
                           f"{card.get('matlab_count') or 0} مطلب")

        # give the abstract "المبحث/المطلب" slots DESCRIPTIVE, topic-specific
        # titles so each section chunk has a real sub-topic to write about (the
        # writer can't produce content for a meaningless "المطلب 1.1"). Additive
        # and guarded: on any miss the original structural labels are kept.
        try:
            # outline builds its own rich structure below (skip slot-naming here
            # so it stays a single model call in the common case). Also skip when
            # the MODEL designed the structure — its titles are already
            # topic-specific, so re-naming would waste a call and could dilute them.
            if scope != "outline" and card.get("structure_source") != "model":
                sections_plan = self._descriptive_titles(
                    card.get("topic", "") or task.description, sections_plan, lang)
                card["sections"] = sections_plan
        except Exception as e:
            mem.set_status(6, f"عناوين وصفية (تخطّي: {e})")

        # outline-only → a COMPLETE, richly-detailed outline authored by the model
        # itself (title, structured intro, annotated sub-points, suggested refs) —
        # not just a flat heading list. Falls back to the descriptive one-line
        # list when the model is unavailable or the reply is too thin.
        if scope == "outline":
            head = "هيكل العمل" if lang == "ar" else "Outline"
            _topic = card.get("topic") or self._current_request(task.description)
            _ctx = self._conversation_context(task.description)
            rich = None
            try:
                rich = self._rich_outline(_topic, card, lang, context=_ctx)
            except Exception as e:
                self._rich_reason = f"استثناء: {type(e).__name__}"
                mem.set_status(6, f"هيكل مفصّل (تخطّي: {e})")
            # make the outcome visible on-screen so a fallback is never a silent
            # mystery (نجح / تعذّر النداء / ردّ قصير / لا نموذج …).
            self._emit("detail", "", "الهيكل المفصّل: "
                       + (getattr(self, "_rich_reason", "") or "?"))
            if rich:
                body = rich
                mem.set_status(6, "إخراج: هيكل مفصّل")
            else:
                try:
                    sections_plan = self._descriptive_titles(
                        _topic, sections_plan, lang)
                except Exception:
                    pass
                lines = []
                for sec in sections_plan:
                    lvl = int(sec.get("level", 1) or 1)
                    title = sec.get("title") or sec.get("heading") or ""
                    if title:
                        lines.append(("  " * max(0, lvl - 1)) + "- " + title)
                body = "\n".join(lines)
                mem.set_status(6, "إخراج: هيكل فقط")
            task.sections = [{"heading": head, "body": body}]
            task.draft = f"## {head}\n\n{body}"
            return

        # part-only → write just the one part the user asked for (single section)
        if scope == "part":
            sections_plan = [{"title": self._current_request(task.description),
                              "level": 1}]

        # INTEGRITY — لا مراجع مُختلقة: قسم المراجع يُكتب فقط إذا وُجدت مصادر
        # حقيقية مُجمَّعة. بلا مصادر → نحذف أي قسم مراجع من الخطة كي لا يخترع
        # الكاتب قائمة مراجع (والملاحظة الصادقة «تعذّر الوصول إلى مصادر» تغطّي
        # ذلك). مهام «المراجع فقط» تُعالَج في مسارها أعلاه فلا تُمسّ هنا.
        try:
            _real_refs = bool(
                card.get("sources")
                or (card.get("paperqa_result") or {}).get("references"))
            if (not _real_refs and scope != "references"
                    and "references" not in scopes):
                sections_plan = [
                    s for s in sections_plan
                    if not self._is_ref_heading(
                        s.get("title") or s.get("heading") or "")]
                card["sections"] = sections_plan
        except Exception:
            pass

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
        # fallback: the semantic memory search can miss even when sources WERE
        # gathered (they live in card["sources"]). Build the context straight
        # from them so the section writers actually receive the evidence — this
        # is what lets the cited path (and the specialized writers) run instead
        # of silently degrading to the no-sources path.
        if (not rag_ctx.strip()) and card.get("sources"):
            _lines = []
            for s in (card.get("sources") or [])[:20]:
                if isinstance(s, dict):
                    _t = s.get("title") or ""
                    _c = (s.get("content") or "")[:200]
                    _u = s.get("url") or ""
                    # Label each source with an APA-style (author، year) key.
                    # It used to fall back to the TITLE, so the model cited
                    # whole titles mid-sentence — "(تأثير منصات وأدوات الذكاء
                    # الاصطناعي على التعليم المعماري، ص. )" — with an empty page.
                    _k = self._apa_key(s)
                    _line = f"[{_k}] {_t} — {_c} ({_u})".strip()
                    if _line.strip("[] —()"):
                        _lines.append(_line)
                elif str(s).strip():
                    _lines.append(str(s))
            if _lines:
                rag_ctx = "\n".join(_lines)
        # ── ALLOWED CITATION KEYS ──
        # The APA keys were only ever attached in the no-RAG fallback above, so
        # on the normal path the writer saw raw retrieved text with no key to
        # cite by — and improvised: some citations came out as «(المطيري، 2022)»
        # and others as a bare TITLE, which is the inconsistency the verifier
        # flagged. This appends the exact, closed list of keys built from the
        # gathered sources, so there is a right answer to copy instead of one to
        # invent. Additive: rag_ctx itself (layer 2's output) is untouched.
        try:
            _keys, _seen = [], set()
            for s in (card.get("sources") or [])[:24]:
                if not isinstance(s, dict):
                    continue
                _k = (self._apa_key(s) or "").strip()
                if not _k or _k in _seen:
                    continue
                _seen.add(_k)
                _ti = " ".join(str(s.get("title") or "").split())[:70]
                _keys.append(f"({_k})" + (f" — {_ti}" if _ti else ""))
            if _keys and rag_ctx.strip():
                card["citation_keys"] = [k.split(" — ")[0] for k in _keys]
                rag_ctx = (
                    rag_ctx + "\n\n"
                    + ("مفاتيح الاستشهاد المسموحة (استشهد بهذه الصيغة حرفياً "
                       "داخل المتن، ولا تستشهد بعنوان مرجعٍ ولا بمفتاحٍ غير "
                       "مذكور هنا):\n" if lang == "ar" else
                       "Allowed citation keys (cite in EXACTLY this form; never "
                       "cite a reference by its title, and never invent a key "
                       "that is not listed here):\n")
                    + "\n".join("- " + k for k in _keys))
        except Exception:
            pass
        no_ctx = (not rag_ctx) or rag_ctx.strip() in ("", "(none)")
        mode = card.get("sourcing_mode", "cited")
        # In "cited" mode with NO retrieved context, don't refuse — write from
        # the model's knowledge and flag it so a clear note is added later.
        if mode == "cited" and no_ctx:
            card["sources_unavailable"] = True
        prof = self._strength_profile(card.get("model_strength", "medium"))
        # how the bridge above each مبحث should behave: removed if the user
        # said so, their length if they gave one, otherwise capped automatically
        try:
            _bridge = self._bridge_policy(
                card, self._current_request(task.description))
        except Exception:
            _bridge = {"mode": "auto", "max_words": 120}
        parts, out_sections = [], []
        for _si, sec in enumerate(sections_plan):
            title = sec.get("title") or sec.get("heading") or ""
            body = ""
            # a PARENT section (a المبحث/level-1 immediately followed by its
            # مطالب/level-2 children) must NOT restate what its subsections will
            # cover — that is the direct cause of a المبحث and its المطلب 1.1
            # opening almost identically. Flag it so the writer produces only a
            # brief bridge (handled in the generic writer below).
            _is_parent = False
            try:
                _lvl = int(sec.get("level", 1) or 1)
                _nxt = sections_plan[_si + 1] if _si + 1 < len(sections_plan) \
                    else None
                if _lvl <= 1 and _nxt and int(_nxt.get("level", 1) or 1) >= 2:
                    _is_parent = True
            except Exception:
                _is_parent = False
            # the user asked for no bridge → write nothing for the parent at
            # all (and skip its model call entirely)
            if _is_parent and _bridge.get("mode") == "none":
                out_sections.append({"heading": title, "body": "",
                                     "level": max(1, min(int(
                                         sec.get("level", 1) or 1), 4))})
                parts.append(f"## {title}" if title else "")
                continue
            # ── bound specialized section writers (skills already present, wired
            #    here) — additive: on any miss the generic writer below runs
            #    unchanged, keeping full backward compatibility ──
            if self.llm_fn:
                try:
                    _spec = self._write_section_specialized(
                        title, card, lang, mode, no_ctx, out_sections, prof)
                except Exception as e:
                    _spec = None
                    mem.set_status(6, f"مهارة قسم (تخطّي: {e})")
                if _spec:
                    body = _spec
            if self.llm_fn and not body:
                from pipeline import prompts as _p
                _topic = card.get("topic", "") or task.description
                # prior-sections context so each section knows what was already
                # written and does NOT repeat the general definition (the direct
                # cause of sibling sections all restating the same opening). Helps
                # a strong model cohere and a weak one avoid loops alike.
                _prior = ""
                _pi = [f"- {o.get('heading', '')}: "
                       f"{' '.join((o.get('body', '') or '').split())[:110]}"
                       for o in out_sections[-6:] if (o.get('body') or '').strip()]
                if _pi:
                    _prior = ((
                        "أقسامٌ كُتبت قبل هذا القسم — لا تُعِد تعريف الموضوع العام "
                        "ولا محتواها، وركّز حصراً على الزاوية الخاصة بهذا القسم:\n"
                        if lang == "ar" else
                        "Sections already written — do NOT repeat the general "
                        "definition or their content; focus only on THIS "
                        "section's angle:\n") + "\n".join(_pi) + "\n")
                # MODEL-AGNOSTIC safety net: if the title is still an abstract
                # structural label (a weak model may not have produced a
                # descriptive one), frame it with the topic so the writer knows
                # what this section is about — otherwise it writes nothing.
                if title.strip().startswith(
                        ("المبحث", "المطلب", "Section", "Subsection")):
                    section_name = (
                        f"«{title}» ضمن بحث عن: {_topic} — اكتب المحتوى العلمي "
                        f"المناسب لموضع هذا القسم (خلفية/تفصيل/تحليل بحسب موقعه)، "
                        f"متماسكاً ومرتبطاً بالموضوع مباشرة"
                        if lang == "ar" else
                        f"\"{title}\" within research on: {_topic} — write the "
                        f"scientific content appropriate to this section's role")
                else:
                    section_name = title
                try:
                    _len_dir = self._length_directive(
                        card, len(sections_plan), lang)
                except Exception:
                    _len_dir = ""
                if mode == "uncited":
                    prompt = _p.PROMPT_LAYER_6_WRITE_UNCITED.format(
                        section_name=section_name, topic=card.get("topic", ""),
                        length=_len_dir,
                        rag_contexts=rag_ctx or "(none)", prior_content=_prior)
                    system = _p.SYSTEM_PROMPT_WRITE_NO_SOURCES
                elif mode == "none" or no_ctx:
                    # explicit no-sources request, OR sources were required but
                    # none could be retrieved — write from knowledge, no refusal
                    prompt = _p.PROMPT_LAYER_6_WRITE_NO_SOURCES.format(
                        section_name=section_name, topic=card.get("topic", ""),
                        length=_len_dir, prior_content=_prior)
                    system = _p.SYSTEM_PROMPT_WRITE_NO_SOURCES
                else:
                    prompt = _p.PROMPT_LAYER_6_WRITE.format(
                        section_name=section_name, topic=card.get("topic", ""),
                        citation_style=(card.get("citation_style")
                                        or "APA (author, year)"),
                        length=_len_dir,
                        rag_contexts=rag_ctx or "(none)", prior_content=_prior)
                    # dedicated WRITING system prompt: forbids clarifying
                    # questions/greetings that a chatty model would emit
                    system = _p.SYSTEM_PROMPT_WRITE
                # style director: a SHORT, model-DECIDED style directive
                # (narrative/bullet mixing by info nature, human academic voice,
                # employed questions, non-standard closing) appended like the
                # depth/Islamic directives below. Guarded + toggleable: any miss
                # → no block, writing unchanged. It describes WHEN, never forces.
                if os.environ.get("WEAVER_STYLE_DIRECTOR", "1").strip().lower() \
                        not in ("0", "false", "off", "no"):
                    try:
                        _sb = self._skill_call(
                            "style_director", "style_directives",
                            "build_style_block", card, section_name, lang)
                        if _sb:
                            prompt = prompt + "\n\n" + _sb
                    except Exception:
                        pass
                # STAGE (ب): write each section with the requirements checklist in
                # view — a short, model-decided directive (style / content / a
                # where-it-fits table hint), appended like the style block. Its
                # source is the plan the model itself extracted, so writing now
                # FOLLOWS the plan section by section. Guarded + toggleable
                # (WEAVER_PLAN_WRITER); any miss → writing unchanged.
                if os.environ.get("WEAVER_PLAN_WRITER", "1").strip().lower() \
                        not in ("0", "false", "off", "no"):
                    try:
                        _rb = self._requirements_directive(card, section_name,
                                                           lang)
                        if _rb:
                            prompt = prompt + "\n\n" + _rb
                    except Exception:
                        pass
                # PARENT section → brief bridge only (no overlap with its
                # subsections). This removes the المبحث/المطلب 1.1 duplication.
                if _is_parent:
                    _bw = int(_bridge.get("max_words") or 120)
                    prompt = prompt + "\n\n" + (
                        f"هذا القسم يليه مطالب فرعية تتناول تفاصيله. اكتب تمهيداً "
                        f"موجزاً جداً (٢-٤ جُمَل، بحدٍّ أقصى {_bw} كلمة) يوطّئ "
                        f"للمطالب ويبيّن خطّتها فقط، دون تعريف الموضوع من جديد، "
                        f"ودون كتابة عناوين المطالب أو محتواها هنا — فهي تُكتب "
                        f"في أقسامها. تجنّب التكرار."
                        if lang == "ar" else
                        "This section is followed by subsections that cover its "
                        "detail. Write only a very brief bridge (2-4 sentences) "
                        "that sets up the subsections, without re-defining the "
                        "topic or covering detail the subsections will handle — "
                        "to avoid repetition.")
                # adapt depth/length + temperature to the model's ceiling
                _depth = prof.get("depth") if lang == "ar" else prof.get("depth_en")
                # The depth directive carries a HARD-CODED per-section word band
                # ("استهدف نحو 500–800 كلمة لهذا القسم"). When the user asked for
                # a length of their own, that band contradicts it directly — a
                # 12-page request over 14 sections is ~230 words each, not
                # 500-800 — so drop the band and keep the depth guidance.
                if _depth and _len_dir:
                    import re as _re
                    _depth = _re.sub(
                        r'\s*[\(（][^)）]*?(?:استهدف|aim)[^)）]*[\)）]', '',
                        _depth).strip()
                if _depth:
                    prompt = prompt + "\n\n" + _depth
                # A requested MAXIMUM must reach the writer. Only the expansion
                # loop knew about it, and it can only grow text — so a document
                # written long from the start stayed long (4514 words against a
                # 3600 ceiling). Give each section its share of the budget.
                try:
                    _mx = card.get("max_words")
                    _nsec = max(1, len(sections_plan))
                    if _mx:
                        _share = max(120, int(_mx / _nsec))
                        prompt = prompt + "\n\n" + (
                            f"حدّ أقصى صارم: لا تتجاوز نحو {_share} كلمة في هذا "
                            f"القسم. المستند كلّه يجب ألّا يتجاوز {_mx} كلمة، "
                            f"فأوجز دون إخلال بالمضمون."
                            if lang != "en" else
                            f"HARD LIMIT: keep this section to about {_share} "
                            f"words. The whole document must not exceed {_mx} "
                            f"words — be concise without losing substance.")
                except Exception:
                    pass
                # guide Quran/Hadith marks for Islamic content
                if card.get("islamic"):
                    prompt = prompt + "\n\n" + (self._ISLAMIC_DIRECTIVE_AR
                                               if lang == "ar"
                                               else self._ISLAMIC_DIRECTIVE_EN)
                try:
                    body = self.llm_fn(prompt, system=system,
                                       temperature=prof.get("temp", 0.5))
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
                # MODEL-AGNOSTIC safety net: a weak model may return an EMPTY
                # (non-conversational) body. One last blunt, direct attempt so no
                # section ships as a bare heading.
                if not (body or "").strip():
                    try:
                        _db = self.llm_fn(
                            (f"اكتب محتوى قسم «{title}» من بحث علمي عن: {_topic}. "
                             "اكتب فقرات علمية مباشرة (نحو 150–300 كلمة) دون "
                             "عنوان ودون أي سؤال أو تحية."
                             if lang == "ar" else
                             f"Write the content of section \"{title}\" of "
                             f"research on: {_topic}. Direct scientific "
                             "paragraphs (~150–300 words), no heading, no "
                             "questions, no greeting."),
                            system=_p.SYSTEM_PROMPT_WRITE,
                            temperature=0.4) or ""
                        if _db.strip() and not self._looks_conversational(_db):
                            body = _db.strip()
                    except Exception:
                        pass
            # tidy leaked heading duplicates / markdown markers before shipping
            # an abstract "المطلب 1.1" whose body opens with the real title
            # → promote it, so headings are descriptive and the line is not
            # repeated under the heading.
            try:
                title, body = self._promote_heading_from_body(title, body)
            except Exception:
                pass
            # a PARENT (مبحث with مطالب under it) that wrote its own subsections
            # inline → keep only the bridge, or every مطلب ships twice
            if _is_parent:
                try:
                    body = self._trim_parent_bridge(body)
                    body = self._cap_bridge(body, _bridge.get("max_words"))
                except Exception:
                    pass
            body = self._clean_section_body(body, title)
            parts.append((f"{title}\n{body}").strip())
            # keep the plan's LEVEL (1=مبحث, 2=مطلب) so the exporter can
            # render a real hierarchy instead of flattening everything to H1.
            try:
                _lv = int(sec.get("level", 1) or 1)
            except Exception:
                _lv = 1
            out_sections.append({"heading": title, "body": body,
                                 "level": max(1, min(_lv, 4))})
        task.draft = "\n\n".join(p for p in parts if p)
        task.sections = out_sections
        mem.set_status(6, f"صياغة: {len(out_sections)} قسم ({mode})")

        # run matched enrichment skills (task.skills) that have a write-stage
        # handler — turns skill routing into real execution. Additive/guarded.
        self._dispatch_skills(task, card, lang, mem)
        # when a data file (csv/xlsx) is attached, run REAL statistics on it and
        # inject the computed results (never invented). Additive/guarded.
        self._inject_statistics(task, card, lang, mem)
        # enforce correct Quran/Hadith marks for Islamic content (text-level,
        # all formats). Additive/guarded; no-op for non-Islamic text.
        self._apply_islamic_marks(task, card, lang, mem)
        # optional enrichments the user explicitly asked for (additive/guarded)
        self._enrich_table_chart(task, card, lang, mem)

        # ── the one document-wide duplicate pass (the last net) ──
        # The per-seam guards above have already run; this catches repetition
        # between ANY two paragraphs of the finished document, at any level.
        # Placed BEFORE the length/coverage check so the word count that stage
        # sees is the post-trim one and it can expand if the document is short.
        # Disable with WEAVER_DEDUPE=0.
        try:
            import os as _os
            if _os.environ.get("WEAVER_DEDUPE", "1") != "0" and task.sections:
                _new, _rep = self._dedupe_sections(task.sections, lang)
                if _rep.get("skipped"):
                    mem.set_status(6, f"كشف التكرار: {_rep['skipped']}")
                    card["dedupe_note"] = _rep["skipped"]
                    self._emit("detail", "", "كشف التكرار: " + _rep["skipped"])
                elif _rep.get("dropped"):
                    task.sections = _new
                    task.draft = self._draft_from_sections(task)
                    _where = "، ".join(
                        f"«{a}» كرّر «{b}»" for a, b in _rep["pairs"][:3])
                    mem.set_status(
                        6, f"كشف التكرار: حُذفت {_rep['dropped']} فقرة "
                           f"({_rep['words']} كلمة)")
                    self._emit("detail", "",
                               f"كشف التكرار: {_rep['dropped']} فقرة مكرّرة "
                               f"حُذفت — {_where}")
                    card["dedupe_report"] = _rep
        except Exception as e:
            mem.set_status(6, f"كشف التكرار (تخطّي: {e})")

    def _enrich_table_chart(self, task, card, lang, mem):
        """When the request asked for a table and/or a chart, derive them from
        the written content and attach them. A table becomes its own section; a
        chart spec is stored on the card so _maybe_chart renders it at export.
        Never fabricates numbers (the model is told to return empty otherwise).
        Additive and fully guarded — a miss changes nothing."""
        if not self.llm_fn:
            return
        content = task.draft or "\n".join(
            (s.get("body", "") or "") for s in (task.sections or []))
        if not content.strip():
            return
        if card.get("want_table"):
            try:
                tbl = _content_to_table(self.llm_fn, content, lang)
                # pass the document so a "table" whose cells are copied out of
                # it is recognised as a copy, not just by its row wording
                if tbl and self._is_outline_dump(tbl, content):
                    tbl = None          # a summary of the paper, not a table
                    mem.set_status(6, "رُفض جدول: نسخةٌ من المتن لا بيانات")
                if tbl and tbl.get("headers") and tbl.get("rows"):
                    md = self._skill_call("table_builder", "make_table",
                                          "make_table", tbl["headers"],
                                          tbl["rows"], lang=lang)
                    head = "جدول توضيحي" if lang == "ar" else "Table"
                    if md:
                        # place it BEFORE the conclusion/references rather than
                        # tacking it on at the very end, where it read as an
                        # unrelated block bolted onto the document.
                        _secs = task.sections or []
                        _at = len(_secs)
                        for _i, _s in enumerate(_secs):
                            _h = (_s.get("heading") or "")
                            if self._is_ref_heading(_h) or any(
                                    w in _h for w in ("الخاتمة", "خاتمة",
                                                      "Conclusion")):
                                _at = _i
                                break
                        _secs.insert(_at, {"heading": head, "body": md,
                                           "level": 1})
                        task.sections = _secs
                        task.draft = (task.draft or "") + f"\n\n## {head}\n\n{md}"
                        mem.set_status(6, "أُدرج جدول من المحتوى")
            except Exception as e:
                mem.set_status(6, f"جدول (تخطّي: {e})")
        if card.get("want_chart") and not card.get("chart"):
            try:
                spec = _content_to_chart(self.llm_fn, content, lang)
                if spec:
                    card["chart"] = spec        # _maybe_chart renders at export
                    mem.set_status(6, "أُعدّ رسم بياني من المحتوى")
            except Exception as e:
                mem.set_status(6, f"رسم بياني (تخطّي: {e})")

    async def _layer_6_6(self, task, mem):
        """٦.٦: تحقق الطول والتغطية — بين الكتابة (6) والأنسنة (6.5).

        يمنح النظام ما يفعله المحرّر يدوياً: يتأكّد أن كل قسم مطلوب كُتب فعلاً
        (فيكتب الناقص)، وأن طول النص قريب من الهدف المطلوب (فيوسّع القصير).
        حلقة تصحيح واحدة، آمنة (تعود مبكّراً بلا تعديل عند غياب طول/أقسام/نموذج).

        صدق القياس: عدّ الكلمات حتمي ودقيق (len(split))، لا تقدير. أمّا الصفحات
        فتقديرية (~500 كلمة/صفحة) ما لم يُفتح الملف بعد التصدير — والتحقق الفعلي
        من الصفحات بعد التصدير مهمّة منفصلة لاحقة، لا تُنفَّذ هنا."""
        try:
            card = task.task_card or {}
            # تخطَّ أوضاع يوتيوب/التفريغ ومهام بلا كتابة
            yt = card.get("youtube")
            if yt and yt.get("mode") in ("transcript", "both"):
                return
            if not task.sections:
                return
            # نطاق مُقيِّد (هيكلة/مراجع/خطة/جزء) → المخرَج مكتمل كما أنتجته الطبقة 6.
            # حلقة التغطية هنا تعتبر كل عنوان في الخطة «ناقصاً» (لأن المخرَج سطرٌ
            # واحد «هيكل العمل») فتكتب جسماً كاملاً لكل عنوان عبر النموذج — وهذا
            # يحوّل الهيكلة إلى بحث كامل بطيء. تحقّق الطول/التغطية للمستند الكامل
            # فقط (scope=None و scopes فارغة).
            _scope = card.get("scope")
            _scopes = set(card.get("scopes") or ([_scope] if _scope else []))
            if _scope in ("outline", "references", "plan", "part") or _scopes:
                return

            # ── (أ) تحقق تغطية الأقسام ──
            plan = card.get("sections") or []
            required = [(s.get("title") or s.get("heading") or "") for s in plan]
            required = [r for r in required if r]
            if required:
                missing = self.verify_sections_coverage(required, task.sections)
                if missing and self.llm_fn:
                    for title in missing:
                        try:
                            body = self.llm_fn(
                                f"اكتب قسم «{title}» لهذا الموضوع: "
                                f"{card.get('topic', task.description)}. "
                                f"اكتب المحتوى مباشرة دون عنوان.",
                                system=getattr(self, "system_write", None)
                                or getattr(self, "system_main", None),
                                temperature=0.5) or ""
                        except Exception:
                            body = ""
                        _b = self._clean_section_body(
                            self._strip_meta_preamble(body.strip()), title)
                        if _b and not self._looks_conversational(_b):
                            task.sections.append({"heading": title,
                                                  "body": _b})
                    mem.set_status(66, f"تغطية: أُضيف {len(missing)} قسم ناقص")

            # ── (ب) تحقق الطول (كلمات) ──
            target = self.extract_length_target(task.description)
            tw = target.get("words")
            if tw:
                actual = self.count_words(task.draft or "")
                lo, hi = int(tw * 0.9), int(tw * 1.15)
                # An explicit ceiling ("لا يزيد عن 12 صفحة") must stop the
                # expansion loop: it only ever grew the text, so a document
                # already past the ceiling kept growing (20.5 pages vs 12).
                _max_w = target.get("max_words")
                if _max_w and actual >= int(_max_w * 0.95):
                    lo = 0
                if actual < lo and self.llm_fn:
                    # النص أقصر من المطلوب → وسّع أضعف الأقسام (الأقصر)
                    deficit = tw - actual
                    secs = sorted(task.sections,
                                  key=lambda s: self.count_words(s.get("body", "")))
                    for s in secs[: max(1, len(secs) // 2)]:
                        if deficit <= 0:
                            break
                        try:
                            more = self.llm_fn(
                                f"وسّع الفقرة التالية بعمق أكبر وتفصيل دقيق "
                                f"(أضِف نحو {min(deficit, 300)} كلمة) دون تكرار "
                                f"ودون حشو. أعِد النصّ الموسَّع وحده فقط: بلا "
                                f"تحية، بلا مقدمة، بلا تعليق على المهمة، وبلا "
                                f"ذكر عدد الكلمات، ولا تُعِد عنوان القسم."
                                f"\n\n{s.get('body', '')}",
                                system=getattr(self, "system_write", None)
                                or getattr(self, "system_main", None),
                                temperature=0.5) or ""
                        except Exception:
                            more = ""
                        if more.strip():
                            # GUARD: the expansion reply may be a chat turn
                            # ("أهلاً بك. سأقوم بتوسيع…"), carry a meta preamble
                            # ("إليك التوسعة المطلوبة… 300 كلمة"), or re-insert
                            # the "المطلب 1.1:" label — all of which used to be
                            # pasted verbatim into the document because this
                            # loop overwrote the ALREADY-CLEANED body. Clean it,
                            # and reject it outright unless it is genuinely
                            # longer real content.
                            _m = self._strip_meta_preamble(more.strip())
                            _m = self._clean_section_body(
                                _m, s.get("heading", ""))
                            _old_w = self.count_words(s.get("body", ""))
                            if (_m and not self._looks_conversational(_m)
                                    and self.count_words(_m) >= _old_w):
                                added = self.count_words(_m) - _old_w
                                s["body"] = _m
                                deficit -= max(0, added)
                    mem.set_status(66, f"طول: وُسّع النص نحو الهدف {tw}")

                # أعد بناء draft بعد أي تعديل
                task.draft = "\n\n".join(
                    (f"{s.get('heading', '')}\n{s.get('body', '')}").strip()
                    for s in task.sections if (s.get("heading") or s.get("body")))

                final = self.count_words(task.draft)
                card["word_count_actual"] = final
                card["word_count_target"] = tw
                mem.set_status(66, f"طول نهائي: {final} كلمة (هدف {tw})")
        except Exception as e:
            mem.set_status(66, f"تحقق الطول/التغطية (تخطّي: {e})")

    async def _layer_6_5(self, task: Task, mem: TaskMemory):
        """٦.٥: إعادة الصياغة والتنظيف — أنسنة النص وإزالة البصمة الآلية.

        تُطبّق صامتةً: تحمي الاستشهادات، تستبدل كلمات AI بمرادفات بشرية،
        وتزيل البصمات البصرية (الشرطات الطويلة، الرموز الزخرفية، الخلط اللغوي)
        حسب نوع الملف — مع إبقاء الرموز في عروض PowerPoint.
        """
        task.status = TaskStatus.LAYER_6_5
        mem.set_status(65, "إعادة الصياغة والتنظيف")

        # verbatim YouTube transcript must stay word-for-word → skip humanizing
        # (transcript-only, and "both" whose transcript half must not change).
        yt = task.task_card.get("youtube")
        if yt and yt.get("mode") in ("transcript", "both"):
            mem.set_status(65, "تفريغ حرفي — تخطّي الأنسنة")
            return

        # structural / reference outputs (an outline, a references list) are not
        # prose to humanize — the AI-fingerprint rewriter would swap words in the
        # headings and corrupt their meaning (e.g. "قبل" → "أخرج"). Leave them
        # exactly as authored.
        _card = task.task_card or {}
        _scope = _card.get("scope")
        _scopes = set(_card.get("scopes") or ([_scope] if _scope else []))
        if _scope in ("outline", "references") or ({"outline", "references"}
                                                   & _scopes):
            mem.set_status(65, "مخرَج بنيوي — تخطّي الأنسنة")
            return

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
                # Humanize PROSE only, keeping Markdown tables and fenced code
                # blocks verbatim — the AI-fingerprint cleaner would otherwise
                # reflow a table's '|'/'---' rows and flatten it. Citations are
                # still masked/restored inside (per prose segment).
                task.draft = self._humanize_draft(
                    draft, mod.humanize_text, file_type)
                task.task_card["humanized"] = True
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

    def _humanize_draft(self, draft, humanize_fn, file_type):
        """Humanize PROSE only — keep Markdown tables and fenced code blocks
        VERBATIM. The AI-fingerprint cleaner treats a table's '|' and '---' as
        decoration and reflows its rows, which FLATTENS the table into stacked
        lines (exactly the broken table users saw). So we split the draft into
        protected blocks (a GFM table = a pipe line whose NEXT line is a
        separator, run until a non-pipe/blank line; or a ```fence``` run) and
        prose, humanize only the prose (citations masked, as before), and
        reassemble. Additive and safe: no table/code → identical to humanizing
        the whole draft."""
        import re
        lines = (draft or "").split("\n")
        n = len(lines)

        def _is_sep(s):
            return bool(re.match(
                r"^\s*\|?\s*:?-{1,}:?\s*(\|\s*:?-{1,}:?\s*)*\|?\s*$", s)) \
                and "-" in s

        out, prose = [], []

        def _flush_prose():
            if not prose:
                return
            text = "\n".join(prose)
            prose.clear()
            if not text.strip():
                out.append(text)
                return
            masked, cites = self._mask_citations(text)
            res = humanize_fn(masked, file_type=file_type)
            out.append(self._unmask_citations(res.get("text", text), cites))

        i = 0
        while i < n:
            line = lines[i]
            if re.match(r"^\s*```", line):                 # fenced code block
                _flush_prose()
                blk = [line]
                i += 1
                while i < n and not re.match(r"^\s*```", lines[i]):
                    blk.append(lines[i])
                    i += 1
                if i < n:
                    blk.append(lines[i])
                    i += 1
                out.append("\n".join(blk))
                continue
            if "|" in line and i + 1 < n and _is_sep(lines[i + 1]):  # GFM table
                _flush_prose()
                blk = [line, lines[i + 1]]
                i += 2
                while i < n and "|" in lines[i] and lines[i].strip() != "":
                    blk.append(lines[i])
                    i += 1
                out.append("\n".join(blk))
                continue
            prose.append(line)
            i += 1
        _flush_prose()
        return "\n".join(out)

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

    def _export_fallback(self, out_dir: str, safe: str, task: Task,
                         fmt: str = None, error=None) -> str:
        """Always writes a REAL file to disk (Markdown) even when a format's
        library is missing — so an output always exists. When a BINARY format
        (pptx/xlsx/pdf/docx) was requested but its builder failed, prepend an
        HONEST note explaining WHY (which library to install) instead of a
        silent .md that looks like the wrong output — and surface it in the
        chat reply too."""
        import os
        out = os.path.join(out_dir, safe + ".md")
        body = task.draft or ""
        if not body and task.sections:
            body = "\n\n".join(f"# {s.get('heading','')}\n{s.get('body','')}"
                               for s in task.sections)
        _libs = {"pptx": "python-pptx", "xlsx": "openpyxl",
                 "pdf": "reportlab", "docx": "python-docx"}
        note = ""
        _f = str(fmt or "").lower()
        if _f in _libs:
            note = (f"⚠️ تعذّر بناء ملف {_f.upper()} على الجهاز، فحُفظ المحتوى "
                    f"كملف Markdown بدلاً منه. الأرجح أن مكتبة «{_libs[_f]}» "
                    f"غير مثبّتة — ثبّتها ثم أعد المحاولة:\n"
                    f"    pip install {_libs[_f]}\n\n")
            # surface the reason in the chat reply (task.draft feeds the reply)
            if task.draft and not task.draft.startswith("⚠️"):
                task.draft = note + task.draft
        with open(out, "w", encoding="utf-8") as f:
            f.write((note + body) if body
                    else (note or "(لا يوجد محتوى بعد — لم يُضبط مفتاح النموذج)"))
        return out

    @staticmethod
    def _theme_catalog():
        """Read the REAL theme registry (shared by Word and slides) so the
        choice is never a hardcoded list: adding a theme to themes.json makes it
        immediately selectable. Returns [{id,label,mood}, ...] or []."""
        import json as _json, os as _os
        fp = _os.path.abspath(_os.path.join(
            _os.path.dirname(__file__), "..", "capabilities", "skills",
            "pptx_builder", "themes", "themes.json"))
        try:
            with open(fp, encoding="utf-8") as f:
                themes = (_json.load(f) or {}).get("themes") or {}
        except Exception:
            return []
        out = []
        for tid, t in themes.items():
            if not isinstance(t, dict):
                continue
            out.append({"id": tid,
                        "label": t.get("label_ar") or t.get("label_en") or tid,
                        "mood": t.get("mood", "")})
        return out

    def _resolve_theme(self, card, lang="ar"):
        """THE MODEL picks the document's visual theme by UNDERSTANDING the
        request — the design counterpart of letting it decide the structure.
        21 themes shipped in themes.json but nothing ever selected one, so every
        document came out in the default navy. Order: an explicit WEAVER_THEME
        override > a theme already on the card > the model's choice > None (the
        builder's own default, i.e. unchanged behaviour). The reply is validated
        against the REAL catalog, so an invented id can never reach the builder.
        Toggle with WEAVER_THEME_DIRECTOR=0. Never raises."""
        import os as _os
        cat = self._theme_catalog()
        ids = {t["id"] for t in cat}
        env = (_os.environ.get("WEAVER_THEME") or "").strip()
        if env and env in ids:
            return env
        cur = str(card.get("theme") or "").strip()
        if cur in ids:
            return cur                       # decided once, reused
        if _os.environ.get("WEAVER_THEME_DIRECTOR", "1").strip().lower() in (
                "0", "false", "off", "no"):
            return None
        if not cat or not self.llm_fn:
            return None
        listing = "\n".join(f"- {t['id']}: {t['label']}"
                             + (f" — {t['mood']}" if t['mood'] else "")
                             for t in cat)
        topic = card.get("topic", "") or ""
        req = ""
        try:
            req = self._current_request(getattr(self, "_last_desc", "")) or ""
        except Exception:
            req = ""
        kind = card.get("task_type", "")
        if lang == "en":
            prompt = ("Pick the ONE visual theme that best fits this document. "
                      "Reply with the theme id ONLY — no explanation.\n\n"
                      f"Available themes:\n{listing}\n\n"
                      f"Document type: {kind}\nTopic: {topic}\n"
                      f"User request: {req[:600]}\n\n"
                      "Prefer a sober academic theme for research/theses; a "
                      "formal one for reports; an expressive one only when the "
                      "subject or the user clearly calls for it.")
        else:
            prompt = ("اختر ثيماً بصرياً واحداً يناسب هذا المستند. أجب بمعرّف "
                      "الثيم فقط، بلا أي شرح.\n\n"
                      f"الثيمات المتاحة:\n{listing}\n\n"
                      f"نوع المستند: {kind}\nالموضوع: {topic}\n"
                      f"طلب المستخدم: {req[:600]}\n\n"
                      "فضّل ثيماً أكاديمياً رصيناً للبحوث والرسائل، ورسمياً "
                      "للتقارير، ولا تختر ثيماً تعبيرياً إلا إذا كان الموضوع أو "
                      "طلب المستخدم يستدعيه صراحةً.")
        try:
            raw = self.llm_fn(prompt, system=self.system_main, temperature=0.0,
                              max_tokens=30, timeout=25) or ""
        except TypeError:
            try:
                raw = self.llm_fn(prompt, system=self.system_main,
                                  temperature=0.0) or ""
            except Exception:
                return None
        except Exception:
            return None
        pick = (raw or "").strip().strip('"\'`.,\n').split()[:1]
        pick = pick[0] if pick else ""
        if pick not in ids:                  # tolerate "id — label" replies
            for tid in ids:
                if tid in (raw or ""):
                    pick = tid
                    break
        if pick in ids:
            card["theme"] = pick
            return pick
        return None

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
                # THE MODEL decides the visual theme (falls back to the
                # builder's own default when unavailable/disabled).
                _kw = {}
                try:
                    _th = self._resolve_theme(card, lang)
                    if _th:
                        _kw["theme_id"] = _th
                except Exception:
                    _kw = {}
                self._skill_call(
                    "docx_builder", "docx_advanced", "build_rich_docx",
                    title=title, sections=sections, output_path=out, lang=lang,
                    font=font, references=references, toc=bool(card.get("toc")),
                    cover=cover, toc_position=toc_pos, **_kw)
                # rich Word styling for Quran/Hadith (bold verse/matn via the
                # quran_hadith_citation skill's own _set_run). Guarded/no-op.
                self._style_islamic_docx(out, card)
                return out
            if fmt == "pdf":
                out = os.path.join(out_dir, safe + ".pdf")
                # A PDF is actually RENDERED, so the cover, the table of
                # contents and the page numbers are REAL here — not Word fields
                # a viewer may refuse to compute. The builder also returns the
                # TRUE page count, which we record so a "10-12 pages"
                # requirement can be checked exactly instead of estimated.
                _cov = (card.get("cover") if self._skill_call(
                    "docx_builder", "docx_frontmatter", "should_add_cover", card)
                    else None)
                _res = self._skill_call(
                    "pdf_builder", "build_pdf", "build_pdf",
                    sections=sections, output_path=out, title=title, lang=lang,
                    references=references, toc=bool(card.get("toc")),
                    cover=_cov)
                try:
                    if isinstance(_res, dict) and _res.get("pages"):
                        card["actual_pages"] = int(_res["pages"])
                except Exception:
                    pass
                return out
            if fmt == "pptx":
                out = os.path.join(out_dir, safe + ".pptx")
                # turn each section body into clean slide points (strip markdown
                # so the deck reads cleanly — build_deck renders text directly)
                def _slide_points(body):
                    pts = []
                    for ln in (body or "").split("\n"):
                        ln = ln.strip()
                        if not ln:
                            continue
                        ln = re.sub(r'^[-*•]\s*', '', ln)     # bullet markers
                        ln = re.sub(r'^#{1,6}\s*', '', ln)    # md headings
                        ln = re.sub(r'[*_`]+', '', ln).strip()  # inline md
                        if ln:
                            pts.append(ln)
                    return pts
                plan_sections = [{"title": s.get("heading", ""),
                                  "points": _slide_points(s.get("body", ""))}
                                 for s in sections]
                # ── creative path first ("the Claude way"): llm_deck_generator
                #    authors free HTML/CSS per slide, then the (now multi-slide)
                #    bridge converts to native PPTX. Needs llm_fn + the Node
                #    engine; on ANY miss we fall through to the template builder
                #    below — unchanged — so nothing breaks without them.
                if self.llm_fn:
                    try:
                        gen = self._skill_call(
                            "pptx_builder", "llm_deck_generator",
                            "generate_and_convert", title, plan_sections, out,
                            lang=lang, llm_fn=self.llm_fn)
                        if (gen and gen.get("ok") and os.path.exists(out)
                                and os.path.getsize(out) > 0):
                            return out
                    except Exception:
                        pass
                slides = None
                # slide_designer: build the slide PLAN (title/points/visual,
                # ≤5 points per slide, academic skeleton when empty). Its
                # "points" key is exactly what build_deck consumes. Additive —
                # on any miss we fall back to a direct mapping below.
                try:
                    plan = self._skill_call(
                        "slide_designer", "design_slides", "design_slides",
                        title, plan_sections, card.get("slide_count"),
                        lang, self.llm_fn)
                    if plan and plan.get("slides"):
                        slides = plan["slides"]
                except Exception:
                    slides = None
                if not slides:
                    # fallback with the CORRECT "points" key build_deck reads
                    # (the previous "bullets" key was silently ignored)
                    slides = [{"title": s["title"], "points": s["points"]}
                              for s in plan_sections]
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
            if fmt in ("csv",):
                out = os.path.join(out_dir, safe + ".csv")
                import csv as _csv
                data = card.get("data") or [[s.get("heading", ""),
                                             re.sub(r'\s+', ' ',
                                                    (s.get("body", "") or ""))]
                                            for s in sections]
                headers = card.get("headers") or (
                    ["القسم", "المحتوى"] if lang == "ar"
                    else ["Section", "Content"])
                # utf-8-sig so Excel opens Arabic correctly
                with open(out, "w", encoding="utf-8-sig", newline="") as f:
                    w = _csv.writer(f)
                    if headers:
                        w.writerow(headers)
                    for row in data:
                        w.writerow(row if isinstance(row, (list, tuple))
                                   else [row])
                return out
            if fmt in ("txt", "text"):
                out = os.path.join(out_dir, safe + ".txt")
                body = "\n\n".join(
                    ((s.get("heading", "") + "\n") if s.get("heading") else "")
                    + (s.get("body", "") or "") for s in sections).strip()
                body = re.sub(r'^[ \t]*#{1,6}[ \t]*', '', body, flags=re.M)
                body = re.sub(r'[*_`]+', '', body)
                with open(out, "w", encoding="utf-8") as f:
                    f.write(body)
                return out
            if fmt in ("html", "htm"):
                out = os.path.join(out_dir, safe + ".html")
                with open(out, "w", encoding="utf-8") as f:
                    f.write(self._sections_to_html(title, sections, lang))
                return out
        except Exception as _e:
            return self._export_fallback(out_dir, safe, task, fmt=fmt, error=_e)
        return self._export_fallback(out_dir, safe, task, fmt=fmt)

    @staticmethod
    def _sections_to_html(title, sections, lang="ar"):
        """A clean standalone HTML document from [{heading, body}] sections."""
        import html as _h
        import re as _r
        rtl = "rtl" if lang == "ar" else "ltr"
        parts = ["<!doctype html><html lang=\"" + ("ar" if lang == "ar" else "en")
                 + "\" dir=\"" + rtl + "\"><head><meta charset=\"utf-8\">"
                 "<meta name=\"viewport\" content=\"width=device-width,"
                 "initial-scale=1\"><title>" + _h.escape(title or "") + "</title>"
                 "<style>body{font-family:system-ui,'Segoe UI',Arial,sans-serif;"
                 "line-height:1.8;max-width:820px;margin:24px auto;padding:0 16px;"
                 "color:#1a1a1a}h1,h2,h3{line-height:1.3}a{color:#1a56db}"
                 "@media(prefers-color-scheme:dark){body{background:#111;color:#eee}"
                 "a{color:#7aa2ff}}</style></head><body>"]
        if title:
            parts.append("<h1>" + _h.escape(title) + "</h1>")
        for s in sections:
            hd = (s.get("heading") or "").strip()
            if hd:
                parts.append("<h2>" + _h.escape(hd) + "</h2>")
            for para in _r.split(r"\n\s*\n", (s.get("body") or "").strip()):
                para = para.strip()
                if not para:
                    continue
                lines = [ln.strip() for ln in para.split("\n") if ln.strip()]
                if lines and all(_r.match(r'^[-*•]\s+', ln) for ln in lines):
                    parts.append("<ul>" + "".join(
                        "<li>" + _h.escape(_r.sub(r'^[-*•]\s+', '', ln)) + "</li>"
                        for ln in lines) + "</ul>")
                else:
                    parts.append("<p>" + "<br>".join(_h.escape(ln)
                                                     for ln in lines) + "</p>")
        parts.append("</body></html>")
        return "".join(parts)

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
        # a link was pasted but couldn't be read (e.g. missing library / no
        # captions) — say so honestly instead of silently topic-searching.
        if card.get("pasted_present") and not card.get("pasted_reads"):
            extra = ("تعذّرت قراءة الرابط المُدرَج (قد يلزم تثبيت "
                     "youtube-transcript-api أو أنّ المحتوى غير متاح)، فاعتمد "
                     "المحتوى على بحث عام حول الموضوع."
                     if lang == "ar" else
                     "The pasted link could not be read (a library may be "
                     "missing or the content is unavailable), so this is based "
                     "on a general search of the topic.")
            note = (note + " " + extra) if note else extra
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

    # ── ONE document-wide duplicate pass ────────────────────────────────────
    # Before this, every anti-repetition guard defended ONE seam: the bridge
    # above a مبحث, a heading echoed inside its own body, two conclusion
    # sub-sections. Eight guards in total — and repetition kept reappearing at
    # the next seam, because the number of section PAIRS that can repeat grows
    # with the square of the section count (15 sections = 105 pairs).
    #
    # This is the last net: after all sections are assembled, every paragraph is
    # compared with every paragraph BEFORE it, anywhere in the document and at
    # any level (مبحث / مطلب / تقسيم / فصل / مقدمة / خاتمة). Similarity is
    # difflib on the paragraph opening — arithmetic, not a keyword list and not
    # a model call, so it behaves identically with any model.
    @staticmethod
    def _dedupe_sections(sections, lang="ar", threshold=0.80,
                         max_removed_ratio=0.40, min_words=12):
        """Drop paragraphs that repeat an earlier paragraph of the SAME document.

        Returns (new_sections, report) where report is
        {"dropped": n, "words": n, "pairs": [(later_heading, earlier_heading)],
         "skipped": reason_or_None}. `sections` is never mutated.

        WHICH COPY SURVIVES: the first occurrence in reading order — EXCEPT when
        the pair is a parent section and one of its own children (a مبحث and its
        مطالب). There the child keeps the text and the parent's copy is dropped,
        because a parent must not pre-empt what its subsections will say.

        PROTECTED (never touched): a references/bibliography section (repeating
        author names is correct there), any table row, and short paragraphs — a
        one-line transition is not a repeat.

        SAFETY: if the pass would remove more than `max_removed_ratio` of the
        document's words it is ABANDONED whole and reported instead, so a
        mis-measure can never gut a real research paper. Never raises."""
        import difflib

        def _norm(s):
            t = " ".join(str(s or "").split())
            for ch in "ًٌٍَُِّْـ":
                t = t.replace(ch, "")
            return (t.replace("أ", "ا").replace("إ", "ا").replace("آ", "ا")
                     .replace("ى", "ي").replace("ة", "ه").lower())

        try:
            secs = [s for s in (sections or []) if isinstance(s, dict)]
            if len(secs) < 2:
                return sections, {"dropped": 0, "words": 0, "pairs": [],
                                  "skipped": None}
            lv = []
            for s in secs:
                try:
                    lv.append(int(s.get("level", 1) or 1))
                except Exception:
                    lv.append(1)
            # children of i = the following sections with a deeper level, until
            # a level back at or above i's own
            kids = []
            for i in range(len(secs)):
                acc = set()
                for j in range(i + 1, len(secs)):
                    if lv[j] <= lv[i]:
                        break
                    acc.add(j)
                kids.append(acc)

            protected = [WeaverOrchestrator._is_ref_heading(
                s.get("heading", "")) for s in secs]
            # flatten to (section_index, paragraph_index, text)
            blocks = []
            for i, s in enumerate(secs):
                for k, para in enumerate((s.get("body") or "").split("\n\n")):
                    blocks.append((i, k, para))

            total_words = sum(len((p or "").split()) for _i, _k, p in blocks)
            drop = set()          # (section_index, paragraph_index)
            pairs = []

            def _eligible(i, para):
                p = (para or "").strip()
                if protected[i] or len(p.split()) < min_words:
                    return False
                return "|" not in p          # leave tables alone

            for a in range(len(blocks)):
                ia, ka, pa = blocks[a]
                if not _eligible(ia, pa) or (ia, ka) in drop:
                    continue
                ha = _norm(pa)[:180]
                for b in range(a + 1, len(blocks)):
                    ib, kb, pb = blocks[b]
                    if ia == ib or not _eligible(ib, pb) or (ib, kb) in drop:
                        continue
                    if difflib.SequenceMatcher(
                            None, ha, _norm(pb)[:180]).ratio() < threshold:
                        continue
                    # parent/child pair → the CHILD keeps it, the parent loses
                    if ib in kids[ia]:
                        drop.add((ia, ka))
                        pairs.append((secs[ia].get("heading", ""),
                                      secs[ib].get("heading", "")))
                        break
                    drop.add((ib, kb))
                    pairs.append((secs[ib].get("heading", ""),
                                  secs[ia].get("heading", "")))

            if not drop:
                return sections, {"dropped": 0, "words": 0, "pairs": [],
                                  "skipped": None}
            removed_words = sum(len((p or "").split())
                                for i, k, p in blocks if (i, k) in drop)
            if total_words and removed_words > total_words * max_removed_ratio:
                return sections, {
                    "dropped": len(drop), "words": removed_words, "pairs": pairs,
                    "skipped": f"القصّ كان سيحذف {removed_words} كلمة من "
                               f"{total_words} (فوق الحدّ) فلم يُطبَّق"}
            out, emptied = [], []
            for i, s in enumerate(secs):
                paras = (s.get("body") or "").split("\n\n")
                keep = [p for k, p in enumerate(paras) if (i, k) not in drop]
                # A section whose EVERY paragraph was a copy (a conclusion that
                # re-printed the body wholesale) would become a bare heading.
                # Keep its first paragraph and name it in the report, so the
                # reader is told rather than handed an empty section.
                if not [x for x in keep if x.strip()] and paras:
                    keep = [next((p for k, p in enumerate(paras)
                                  if (i, k) in drop), paras[0])]
                    emptied.append(s.get("heading", ""))
                new = dict(s)
                new["body"] = "\n\n".join(x for x in keep if x.strip()).strip()
                out.append(new)
            return out, {"dropped": len(drop), "words": removed_words,
                         "pairs": pairs, "skipped": None, "emptied": emptied}
        except Exception as e:
            return sections, {"dropped": 0, "words": 0, "pairs": [],
                              "skipped": f"{type(e).__name__}: {e}"}

    # canonical source TYPES. Arabic scholarship separates these three, and the
    # pipeline used to merge them all into one flat "قائمة المراجع":
    #   primary   المصادر الأوّلية — original material the research works ON
    #             (documents, manuscripts, sacred texts, laws, raw official data)
    #   secondary المراجع — books/articles that ANALYSE the topic
    #   study     الدراسات السابقة — prior academic studies on the same question
    #   web       المواقع الإلكترونية — general web pages
    _REF_TYPES = ("primary", "secondary", "study", "web")
    _REF_GROUP_AR = {"primary": "المصادر", "secondary": "المراجع",
                     "study": "الدراسات السابقة",
                     "web": "المواقع الإلكترونية"}
    # ordinals are applied to the groups ACTUALLY present, so a list with only
    # two of the four reads "أولاً/ثانياً" instead of skipping to "ثانياً/رابعاً"
    _REF_ORDINALS_AR = ("أولاً", "ثانياً", "ثالثاً", "رابعاً")
    _REF_GROUP_EN = {"primary": "Primary Sources", "secondary": "References",
                     "study": "Previous Studies", "web": "Websites"}

    # scholarly databases the pipeline queries — a hit here is a real academic
    # work, not a web page. Used as a MODEL-FREE fallback so the type grouping
    # still engages when the model can't classify.
    _ACAD_PROVENANCE = ("openalex", "crossref", "arxiv", "semanticscholar",
                        "doaj", "europepmc", "paperqa", "pubmed")

    @classmethod
    def _fallback_ref_type(cls, s):
        """A deterministic, model-free type for one source, from its provenance
        and fields. Deliberately conservative: it only separates scholarly works
        («المراجع») from plain web pages («المواقع الإلكترونية»), because telling
        a prior STUDY from an analytical reference needs real judgement. Returns
        a type from _REF_TYPES."""
        if not isinstance(s, dict):
            return "web"
        prov = str(s.get("source") or "").lower()
        if any(k in prov for k in cls._ACAD_PROVENANCE):
            return "secondary"
        if s.get("doi") or s.get("venue") or s.get("journal"):
            return "secondary"
        a = s.get("authors") or s.get("author")
        if a and s.get("year"):
            return "secondary"
        if s.get("url"):
            return "web"
        return "secondary"

    def _classify_sources(self, sources, topic="", lang="ar"):
        """THE MODEL labels each gathered source as a primary source, a
        secondary reference, a prior study, or a web page — the distinction the
        system could not make (everything landed in one «قائمة المراجع»).
        Writes `ref_type` onto each source in place and returns True when at
        least one label was applied. Never raises; no model → False → the flat
        list is kept, so behaviour is unchanged."""
        items = [s for s in (sources or []) if isinstance(s, dict)]
        if not items or not self.llm_fn:
            return False
        items = items[:40]
        listing = []
        for i, s in enumerate(items, 1):
            bits = [str(s.get("title") or s.get("key") or "")[:120]]
            if s.get("year"):
                bits.append(str(s.get("year")))
            if s.get("source"):
                bits.append(str(s.get("source")))
            if s.get("url"):
                bits.append(str(s.get("url"))[:60])
            listing.append(f"{i}. " + " | ".join(b for b in bits if b))
        listing = "\n".join(listing)
        if lang == "en":
            prompt = ("Classify each item by its scholarly TYPE. Return JSON "
                      'only: {"1":"primary|secondary|study|web", ...}\n'
                      "primary = original material the research works on "
                      "(documents, manuscripts, sacred texts, laws, raw official "
                      "statistics); secondary = a book/article analysing the "
                      "topic; study = a prior academic study (empirical paper, "
                      "thesis) on the same question; web = a general web page or "
                      "news site.\n\n"
                      f"Topic: {topic}\n\n{listing}")
        else:
            prompt = ("صنّف كل عنصرٍ بحسب نوعه العلميّ. أعِد JSON فقط: "
                      '{"1":"primary|secondary|study|web", ...}\n'
                      "primary = مصدر أوّليّ يشتغل عليه البحث نفسه (وثائق، "
                      "مخطوطات، نصوص مقدّسة، قوانين، إحصاءات رسمية خام)؛ "
                      "secondary = مرجع (كتاب/مقال) يحلّل الموضوع؛ "
                      "study = دراسة سابقة أكاديمية (بحث ميدانيّ، رسالة علمية) "
                      "على السؤال نفسه؛ web = موقع إلكترونيّ عامّ أو خبريّ.\n\n"
                      f"الموضوع: {topic}\n\n{listing}")
        try:
            from core.llm import extract_json
            try:
                raw = self.llm_fn(prompt, system=self.system_main,
                                  temperature=0.0, max_tokens=600,
                                  timeout=45) or ""
            except TypeError:
                raw = self.llm_fn(prompt, system=self.system_main,
                                  temperature=0.0) or ""
            data = extract_json(raw)
        except Exception:
            return False
        if not isinstance(data, dict):
            return False
        applied = 0
        for i, s in enumerate(items, 1):
            v = data.get(str(i)) or data.get(i)
            v = str(v or "").strip().lower()
            if v in self._REF_TYPES:
                s["ref_type"] = v
                applied += 1
        return applied > 0

    def _grouped_refs_body(self, sources, lang, skill, module, pq_refs, card):
        """Build ONE bibliography body with the types separated by internal
        sub-headings (the «قائمة المصادر والمراجع» layout of Arabic theses).
        Kept as a single section on purpose: separate sections would collide
        with a «الدراسات السابقة» chapter in the body and with the ref-heading
        cleanup. Returns (heading, body) or None to fall back to the flat list."""
        items = [s for s in (sources or []) if isinstance(s, dict)]
        if not items:
            return None
        _how = "model"
        if not any(s.get("ref_type") for s in items):
            if not self._classify_sources(items, card.get("topic", ""), lang):
                _how = "fallback"
        # Fill in anything the model left unlabelled (or everything, when it
        # could not classify at all) using the provenance-based fallback. This
        # is what stops the type-aware list from silently collapsing back to one
        # flat «قائمة المراجع» whenever the classification call fails.
        for s in items:
            if not s.get("ref_type"):
                s["ref_type"] = self._fallback_ref_type(s)
        groups = {t: [] for t in self._REF_TYPES}
        for s in items:
            groups.get(s.get("ref_type") or "secondary",
                       groups["secondary"]).append(s)
        present = [t for t in self._REF_TYPES if groups[t]]
        try:
            card["refs_grouping"] = {
                "how": _how, "types": present,
                "grouped": len(present) > 1,
                "reason": ("" if len(present) > 1
                           else "كل المصادر من نوعٍ واحد")}
        except Exception:
            pass
        if len(present) <= 1:
            return None                  # only one kind → the flat list is right
        names = self._REF_GROUP_EN if lang == "en" else self._REF_GROUP_AR
        parts = []
        for _n, t in enumerate(present):
            try:
                txt = self._skill_call(skill, module, "build_bibliography",
                                       groups[t], lang, None)
            except Exception:
                txt = "\n".join(
                    f"{i}. {(x.get('title') or '')} {(x.get('url') or '')}".strip()
                    for i, x in enumerate(groups[t], 1))
            if (txt or "").strip():
                _label = names[t]
                if lang != "en" and _n < len(self._REF_ORDINALS_AR):
                    _label = f"{self._REF_ORDINALS_AR[_n]}: {_label}"
                parts.append(f"{_label}\n{txt.strip()}")
        if not parts:
            return None
        if pq_refs:
            parts.append(str(pq_refs).strip())
        head = ("قائمة المصادر والمراجع" if lang != "en"
                else "Sources and References")
        return head, "\n\n".join(parts)

    @classmethod
    def _cited_sources(cls, draft, sources):
        """Keep only the sources the text ACTUALLY cites — the rule APA itself
        states (a reference list lists what was cited, nothing more). The list
        used to be built from every gathered source while the citations came
        from whatever the writer used, so the two never matched.

        A source counts as cited when its author surname, its DOI, its URL, or a
        distinctive fragment of its title appears in the draft. SAFETY: if that
        finds (almost) nothing — a writer that cited nothing, or an unreadable
        style — the full list is returned unchanged, so a real bibliography is
        never silently emptied."""
        items = [s for s in (sources or []) if isinstance(s, dict)]
        text = (draft or "")
        if not items or not text.strip():
            return sources
        low = text.lower()

        def _hit(s):
            for key in ("doi", "url"):
                v = str(s.get(key) or "").strip().lower()
                if v and v in low:
                    return True
            a = s.get("authors") or s.get("author")
            if isinstance(a, (list, tuple)):
                a = a[0] if a else ""
            a = str(a or "").strip()
            if a:
                # surname alone is enough: "الشلغصي، وليد" → "الشلغصي"
                sur = a.replace("،", ",").split(",")[0].strip()
                if len(sur) >= 3 and sur.lower() in low:
                    return True
            t = " ".join(str(s.get("title") or "").split())
            if len(t) >= 12:
                frag = " ".join(t.split()[:4]).lower()
                if len(frag) >= 10 and frag in low:
                    return True
            return False

        cited = [s for s in items if _hit(s)]
        # never ship an empty (or near-empty) bibliography on a weak match
        if len(cited) < max(1, len(items) // 4):
            return sources
        return cited

    @staticmethod
    def _draft_from_sections(task):
        """Rebuild the chat draft from task.sections — the single source of
        truth the exported file is built from. Used after the reference list is
        rewritten, so the web view and the document can never show different
        (or duplicated) reference lists."""
        parts = []
        for s in (task.sections or []):
            h = (s.get("heading") or "").strip()
            b = (s.get("body") or "").strip()
            if not (h or b):
                continue
            parts.append((f"## {h}\n\n{b}" if h and b else (h or b)))
        return "\n\n".join(parts).strip() or (task.draft or "")

    def _append_references(self, task: Task):
        """Build the full reference list from the retrieved sources via the
        citation-style skill (apa_formatter / mla_formatter) and put it as the
        LAST section of the report, replacing any placeholder references
        heading. No sources → nothing added."""
        card = task.task_card

        def _strip_fabricated_refs():
            # remove any references section the writer may have produced when we
            # have NO real sources — never leave an invented reference list.
            task.sections = [s for s in (task.sections or [])
                             if not self._is_ref_heading(s.get("heading", ""))]

        # no-citation modes never get a references list
        if card.get("sourcing_mode") in ("none", "uncited"):
            _strip_fabricated_refs()
            return
        sources = card.get("sources") or []
        # APA/MLA list ONLY what the text cites — see _cited_sources (falls back
        # to the full list when citations can't be matched).
        try:
            sources = self._cited_sources(task.draft, sources)
        except Exception:
            pass
        pq_refs = (card.get("paperqa_result") or {}).get("references")
        if not sources and not pq_refs:
            _strip_fabricated_refs()
            return
        lang = card.get("language", "ar")
        style = str(card.get("citation_style", "APA")).upper()
        skill = "mla_formatter" if style == "MLA" else "apa_formatter"
        module = "format_mla" if style == "MLA" else "format_apa"
        # TYPE-AWARE list first: separate المصادر / المراجع / الدراسات السابقة /
        # المواقع instead of merging them into one flat «قائمة المراجع». Falls
        # back to the flat list below whenever the types can't be told apart.
        try:
            _grp = self._grouped_refs_body(sources, lang, skill, module,
                                           pq_refs, card)
        except Exception:
            _grp = None
        if _grp:
            _ghead, _gbody = _grp
            task.sections = [x for x in (task.sections or [])
                             if not self._is_ref_heading(x.get("heading", ""))]
            task.sections.append({"heading": _ghead, "body": _gbody,
                                  "level": 1})
            # Rebuild the chat draft FROM the sections. Appending to the old
            # draft left the writer's own reference block in the web view (and
            # only there), so the page showed TWO differently-formatted lists
            # while the exported file showed one. Now both render the same
            # sections.
            if task.draft:
                task.draft = self._draft_from_sections(task)
            card["references_list"] = _gbody
            return
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
        # rebuild the chat draft from the sections (see note above) so the web
        # view and the exported document never diverge.
        if task.draft:
            task.draft = self._draft_from_sections(task)
        card["references_list"] = refs

    @staticmethod
    def _strip_placeholder_pages(text):
        """Remove UNRESOLVED page-number placeholders the model copies from the
        citation template — "(المصدر، ص. X)" / "(Author, p. N)" where the page is
        a literal letter (X/N/؟), not a real number. Keeps the citation, drops
        only the bogus page part; real numeric pages (ص. 12) are untouched."""
        import re
        if not text:
            return text
        # ", ص. X" / "، p. N" (placeholder letter) inside/at a citation → drop it
        text = re.sub(r"\s*[،,]\s*(?:ص|p)\s*\.?\s*[XxNn؟\?]+(?=[\)\]\s،,\.]|$)",
                      "", text)
        # a lone "(ص. X)" / "(p. N)" with no source → remove the empty citation
        text = re.sub(r"[\(\[]\s*(?:ص|p)\s*\.?\s*[XxNn؟\?]+\s*[\)\]]", "", text)
        return text

    def _expand_draft_to_length(self, draft, target_words, lang="ar"):
        """WIRING 3 helper — ask the model to EXPAND an under-length draft to the
        target word count, adding depth within the EXISTING sections. Returns the
        expanded text only when it genuinely grew AND preserved the structure
        (headings kept, any table kept, language kept); otherwise None so the
        original draft is left untouched. Never truncates, never raises."""
        if not self.llm_fn or not (draft or "").strip() or not target_words:
            return None
        import os
        cur = _vr_words(draft)
        if cur >= target_words * 0.95:
            return None
        try:
            _mt = int(os.environ.get("WEAVER_RICH_MAXTOK", "8000") or 8000)
        except Exception:
            _mt = 8000
        heads_before = len(_vr_headings(draft))
        had_table = _vr_has_table(draft)
        if lang == "en":
            prompt = (
                f"Expand the following document to at least ~{target_words} words "
                "by adding analytical depth, detail and examples WITHIN the "
                "existing sections. Do not delete any existing content, do not "
                "remove or rename headings, and keep every table and the language "
                "intact. Return the full expanded Markdown only:\n\n" + draft)
        else:
            prompt = (
                f"وسّع المستند التالي ليبلغ نحو {target_words} كلمة على الأقل، "
                "بإضافة عمقٍ تحليليّ وتفصيلٍ وأمثلةٍ ضمن الأقسام القائمة. لا تحذف "
                "أيّ محتوى موجود، ولا تحذف العناوين أو تُعِد تسميتها، وحافظ على "
                "الجداول واللغة العربية كما هي. أعِد النصّ الكامل الموسَّع بصيغة "
                "ماركداون فقط:\n\n" + draft)
        try:
            out = self.llm_fn(prompt, system=self.system_main,
                              temperature=0.3, max_tokens=_mt) or ""
        except TypeError:
            out = self.llm_fn(prompt, system=self.system_main,
                              temperature=0.3) or ""
        out = (out or "").strip()
        # strip a wrapping ```markdown fence if present
        if out.startswith("```"):
            out = out.split("\n", 1)[-1] if "\n" in out else ""
            if out.rstrip().endswith("```"):
                out = out.rstrip()[:-3]
        out = out.strip()
        # GUARDS: accept only a real, structure-preserving expansion
        if (_vr_words(out) > cur
                and len(_vr_headings(out)) >= heads_before
                and (not had_table or _vr_has_table(out))
                and (lang == "en" or _vr_arabic_ratio(out) >= 0.6)):
            return out
        return None

    @staticmethod
    def _is_outline_dump(tbl, content=None):
        """True when a generated "table" is really the document re-tabulated
        rather than data. Rejecting it protects the length budget and the
        no-repetition rule at once.

        The original test matched section WORDS in the first cell («المقدمة»,
        «المبحث», «المطلب»). A run then produced a 32-row «النقطة | التفصيل»
        whose first cells read «خلفية الموضوع», «أهمية البحث», «مشكلة البحث» —
        no match, so ~1,400 copied words shipped as a "table". Two MEASURED
        signals now decide it, with the word test kept as a third:

          • CELL SIZE — measured across a real run: genuine term/explanation
            tables had a longest cell of 7–14 words; the dump's longest was 184.
            A cell of 40+ words is prose, and prose in cells is not a table.
          • REPETITION — cells whose opening is already present in the document
            are copies, not data. Needs `content` (optional, so old callers
            behave exactly as before).
        """
        rows = (tbl or {}).get("rows") or []
        if len(rows) < 3:
            return False
        cells = [str(c) for r in rows for c in (r or [])]
        lens = [len(c.split()) for c in cells if c.strip()]
        # (a) prose in cells
        if lens and max(lens) >= 40:
            return True
        # (b) cells copied out of the document
        if content:
            low = " ".join(str(content).split())
            rep = 0
            for c in cells:
                w = c.split()
                if len(w) >= 12 and " ".join(w[:10]) in low:
                    rep += 1
            if rep >= max(2, len([c for c in cells
                                  if len(c.split()) >= 12]) // 4):
                return True
        # (c) the original wording signal
        marks = ("المقدمة", "المبحث", "المطلب", "الخاتمة", "التوصيات",
                 "Introduction", "Section", "Conclusion")
        hits = 0
        for r in rows:
            first = str((r or [""])[0])
            if any(m in first for m in marks):
                hits += 1
        return hits >= max(2, len(rows) // 2)

    def _generate_table(self, task, req, lang="ar"):
        """WIRING 3 helper — produce a REAL Markdown table for an unmet table
        requirement. The writer's soft "use a table where it fits" hint is not
        enough for a MUST requirement: a run produced a «جدول توضيحي» heading
        with 900 words of prose and no table at all. Here we ask for a table and
        nothing else, and accept it ONLY when it really parses as one."""
        if not self.llm_fn:
            return None
        want = (req.get("text") or "").strip()
        topic = (task.task_card or {}).get("topic", "") or task.description
        if lang == "en":
            prompt = (f"Produce ONE Markdown table only — no title, no preamble, "
                      f"no commentary, no prose before or after it.\n"
                      f"Topic: {topic}\nThe table must satisfy: {want}\n"
                      f"Use a header row and a |---|---| separator row, with at "
                      f"least 5 data rows of real, specific content.")
        else:
            prompt = (f"أخرِج جدولاً واحداً بصيغة ماركداون فقط — بلا عنوان، وبلا "
                      f"مقدمة، وبلا تعليق، وبلا أي نصٍّ قبله أو بعده.\n"
                      f"الموضوع: {topic}\nيجب أن يحقّق الجدول: {want}\n"
                      f"استعمل صفَّ رؤوسٍ ثم صفَّ فاصلٍ |---|---| ثم خمسة صفوف "
                      f"بيانات على الأقل بمحتوى حقيقيّ محدّد لا عام.")
        try:
            out = self.llm_fn(prompt, system=self.system_main,
                              temperature=0.2, max_tokens=1500) or ""
        except TypeError:
            out = self.llm_fn(prompt, system=self.system_main,
                              temperature=0.2) or ""
        out = (out or "").strip()
        if out.startswith("```"):
            out = out.split("\n", 1)[-1] if "\n" in out else ""
            if out.rstrip().endswith("```"):
                out = out.rstrip()[:-3]
        out = out.strip()
        # keep ONLY the table lines, and accept only if it truly parses
        lines = [ln for ln in out.splitlines() if ln.strip().count("|") >= 2]
        table = "\n".join(lines).strip()
        return table if table and _vr_has_table(table) else None

    def _repair_requirements(self, task, unmet, reqs):
        """WIRING 3 — attempt SAFE, targeted repairs for unmet MUST requirements.
        Only high-confidence fixes are made; anything riskier is left for the
        honest note. Returns True if it changed anything. Never raises.
          • cover / TOC → set the card flag the export builder reads (the model's
            checklist caught what the keyword detectors missed).
          • length too short → expand the draft (guarded; reverts on any doubt).
        Structure counts, missing tables, and content/style judgements are NOT
        auto-rewritten here — they are reported, not silently patched."""
        card = task.task_card or {}
        lang = card.get("language", "ar") or "ar"
        by_id = {r.get("id"): r for r in (reqs or []) if isinstance(r, dict)}
        fixed = False
        for x in unmet:
            req = by_id.get(x.get("id")) or x
            kind = req.get("kind")
            text = (req.get("text") or "").lower()
            if kind == "insert":
                if (any(k in text for k in ("غلاف", "cover", "عنوان",
                                            "title")) and not card.get("cover")):
                    card["cover"] = True
                    fixed = True
                    continue
                if (any(k in text for k in ("فهرس", "محتويات", "toc",
                                            "contents", "index"))
                        and not card.get("toc")):
                    card["toc"] = True
                    fixed = True
                    continue
                if any(w in text for w in ("جدول", "جداول", "table")) \
                        and not _vr_has_table(task.draft or ""):
                    _tb = None
                    try:
                        _tb = self._generate_table(task, req, lang)
                    except Exception:
                        _tb = None
                    if _tb:
                        _head = ("جدول المصطلحات" if lang != "en"
                                 else "Table")
                        _secs = task.sections or []
                        _new = {"heading": _head, "body": _tb, "level": 1}
                        # place it BEFORE the references list, not after it
                        _at = len(_secs)
                        for _i in range(len(_secs) - 1, -1, -1):
                            if self._is_ref_heading(
                                    _secs[_i].get("heading", "")):
                                _at = _i
                                break
                        _secs.insert(_at, _new)
                        task.sections = _secs
                        task.draft = (task.draft or "").rstrip() \
                            + f"\n\n## {_head}\n\n{_tb}"
                        fixed = True
                        continue
            if kind == "length":
                import os
                pt = _vr_page_target(req)
                if pt:
                    try:
                        wpp = int(os.environ.get("WEAVER_WORDS_PER_PAGE",
                                                 "300") or 300)
                    except Exception:
                        wpp = 300
                    tgt = pt * wpp
                else:
                    tgt = req.get("target") if isinstance(
                        req.get("target"), int) else None
                if tgt:
                    exp = self._expand_draft_to_length(task.draft, tgt, lang)
                    if exp:
                        task.draft = exp
                        fixed = True
        return fixed

    async def _layer_8(self, task: Task, mem: TaskMemory):
        """٨: الإخراج — كتابة الملف النهائي على القرص في outputs/."""
        task.status = TaskStatus.LAYER_8
        mem.set_status(8, "توليد الملف النهائي")
        # drop unresolved "(…، ص. X)" page-number placeholders before export
        try:
            task.draft = self._strip_placeholder_pages(task.draft)
            if task.sections:
                task.sections = [{**s, "body": self._strip_placeholder_pages(
                    s.get("body", ""))} for s in task.sections]
        except Exception:
            pass
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
        # ── STAGE (ج) WIRING 3 — VERIFY → BOUNDED REPAIR → RE-VERIFY ──
        # Verify the finished draft against the requirements checklist; when a
        # MUST requirement isn't confirmed met, attempt SAFE targeted repairs
        # (_repair_requirements) and re-verify, up to WEAVER_REPAIR_ROUNDS passes
        # (default 1). Export is NEVER blocked: after the budget is spent, any
        # still-unmet MUST requirement is reported in ONE honest plain-text note —
        # nothing is silently dropped, and no work is discarded. Fully guarded.
        try:
            _reqs = (task.task_card or {}).get("requirements")
            if _reqs and (task.draft or "").strip():
                import os as _os
                try:
                    _rounds = int(_os.environ.get("WEAVER_REPAIR_ROUNDS",
                                                  "1") or 1)
                except Exception:
                    _rounds = 1
                _rounds = max(0, min(_rounds, 3))
                _lang = task.task_card.get("language", "ar")
                _rep = verify_requirements(
                    _reqs, task.draft, card=task.task_card, lang=_lang,
                    llm_fn=self.llm_fn, system=self.system_main)
                _done = 0
                while (_rep and not _rep.get("all_met") and _done < _rounds):
                    _unmet = [x for x in _rep.get("results", [])
                              if x.get("must") and x.get("status") != "met"]
                    if not _unmet:
                        break
                    try:
                        _changed = self._repair_requirements(
                            task, _unmet, _reqs)
                    except Exception:
                        _changed = False
                    if not _changed:
                        break            # nothing safe left to fix → stop
                    mem.set_status(8, f"إصلاح متطلّبات (جولة {_done + 1})")
                    _rep = verify_requirements(
                        _reqs, task.draft, card=task.task_card, lang=_lang,
                        llm_fn=self.llm_fn, system=self.system_main)
                    _done += 1
                if _rep:
                    task.task_card["verification"] = _rep
                    mem.set_status(8, _rep.get("summary", "تحقّق المتطلّبات"))
                    if not _rep.get("all_met"):
                        _miss = [x for x in _rep.get("results", [])
                                 if x.get("must") and x.get("status") != "met"]
                        if _miss:
                            _en = (_lang == "en")
                            _hdr = ("Verification note (unconfirmed requirements):"
                                    if _en else
                                    "ملاحظة تحقّق (متطلّبات لم تتأكّد):")
                            _lines = [_hdr]
                            for x in _miss:
                                _ev = x.get("evidence", "")
                                _lines.append("• " + str(x.get("text", ""))
                                              + (f" — {_ev}" if _ev else ""))
                            task.draft = (task.draft or "").rstrip() \
                                + "\n\n" + "\n".join(_lines)
        except Exception as e:
            mem.set_status(8, f"تحقّق/إصلاح المتطلّبات (تخطّي: {e})")
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

            # credibility only matters when sources were actually gathered. For a
            # structural ask (outline/plan) or any request with no sources, showing
            # this step made a fast, search-free run look identical to a full
            # research — so gate both the step and the layer on real sources.
            if task.task_card.get("sources"):
                self._emit("step", L("فحص مصداقية المصادر",
                                     "Checking source credibility"))
                await self._layer_5(task, mem)

            self._emit("step", L("كتابة المحتوى", "Writing the content"))
            await self._layer_6(task, mem)
            self._emit("detail", "",
                       L(f"{len(task.sections or [])} قسم",
                         f"{len(task.sections or [])} sections"))

            await self._layer_6_6(task, mem)

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


def _is_conversation_recap(text: str) -> bool:
    """True when the user is asking to recap/summarize THIS conversation (not to
    generate a document). Such a request belongs on the quick path, which sees
    the full recent history (~30 turns) and answers directly — not the pipeline,
    which only receives the last few turns and would also save a stray file.
    Requires BOTH a summary intent AND a reference to the conversation, and no
    pasted link or explicit file-format request (those mean something else)."""
    t = (text or "").lower()
    summary_words = ("لخّص", "لخص", "ملخص", "ملخّص", "لخصلي", "لخّصلي", "اختصر",
                     "خلاصة", "summar", "recap", "tl;dr", "tldr", "استعرض ما")
    convo_words = ("المحادثة", "محادثتنا", "محادثه", "الحوار", "النقاش", "الشات",
                   "الدردشة", "ما قمنا", "ما فعلنا", "ما تحدثنا", "ما دار",
                   "ما جرى", "كلامنا", "حديثنا", "ما اتفقنا", "conversation",
                   "this chat", "our chat", "what we did", "this session",
                   "our discussion", "this thread")
    doc_words = ("ملف", "وورد", "word", "pdf", "docx", "مستند", "وثيقة",
                 "بوربوينت", "pptx", "عرض تقديمي", "اكسل", "excel", "تقرير")
    has_url = ("http://" in t) or ("https://" in t)
    return (any(w in t for w in summary_words)
            and any(w in t for w in convo_words)
            and not any(w in t for w in doc_words)
            and not has_url)


def is_document_task(text: str) -> bool:
    """True when the message asks to produce/analyse a document (→ full
    pipeline); False for a quick conversational question (→ direct answer)."""
    t = (text or "").lower()
    # A recap of THIS conversation is a quick conversational answer, not a
    # document to generate → keep it on the fast path (full recent history, no
    # stray file). This overrides the "summarize" trigger below.
    if _is_conversation_recap(text):
        return False
    if any(trig in t for trig in _TASK_TRIGGERS):
        return True
    # A pasted YouTube link is ALWAYS a pipeline task: it must reach the
    # dedicated youtube path in _layer_3 (summary / transcript / timing).
    # Otherwise a "فرّغ ..." request (whose verbs are not task-triggers) falls
    # to the quick-chat path — which has no transcript tool — and returns wrong
    # output or an empty provider reply. Lazy + guarded; non-YouTube text is
    # completely unaffected.
    try:
        import re as _re
        from capabilities.tools import tool_youtube as _yt
        for _u in _re.findall(r"https?://\S+", text or ""):
            if _yt.is_youtube_url(_u.rstrip('.,)"\'،؛')):
                return True
    except Exception:
        pass
    return False


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


def _md_to_sections(md):
    """Split ready markdown into [{heading, body}] by its '#'/'##' headings."""
    import re
    secs, cur_h, cur_b = [], "", []
    for ln in (md or "").split("\n"):
        m = re.match(r"^\s{0,3}#{1,6}\s+(.*)$", ln)
        if m:
            if cur_h or "".join(cur_b).strip():
                secs.append({"heading": cur_h,
                             "body": "\n".join(cur_b).strip()})
            cur_h, cur_b = m.group(1).strip(), []
        else:
            cur_b.append(ln)
    if cur_h or "".join(cur_b).strip():
        secs.append({"heading": cur_h, "body": "\n".join(cur_b).strip()})
    secs = [s for s in secs if s.get("heading") or s.get("body")]
    return secs or [{"heading": "", "body": (md or "").strip()}]


def _derive_title(md, fallback="مستند"):
    """A document title from the content's first heading, else its first line."""
    import re
    for ln in (md or "").split("\n"):
        m = re.match(r"^\s{0,3}#{1,6}\s+(.*)$", ln)
        if m and m.group(1).strip():
            return m.group(1).strip()[:80]
    for ln in (md or "").split("\n"):
        s = ln.strip().lstrip("#").strip()
        if s:
            return s[:80]
    return fallback


def _content_to_slides(llm_fn, content, lang="ar"):
    """Ask the model to reshape ready content into presentation slides. Returns
    [{heading, body}] (one per slide, body = bullet lines) or None."""
    if not llm_fn:
        return None
    try:
        from core.llm import extract_json
        prompt = (
            "حوّل المحتوى التالي إلى شرائح عرض تقديمي واضحة. أعِد JSON فقط: "
            "{\"slides\":[{\"title\":\"عنوان قصير\",\"bullets\":[\"نقطة\",...]}]}"
            " — عناوين موجزة و3 إلى 6 نقاط قصيرة لكل شريحة، دون أي شرح خارج JSON:\n\n"
            if lang == "ar" else
            "Turn the following into clear presentation slides. Return JSON only: "
            "{\"slides\":[{\"title\":\"short\",\"bullets\":[\"point\",...]}]} — "
            "concise titles, 3-6 short bullets each, nothing outside JSON:\n\n"
        ) + (content or "")[:9000]
        # academic_content: inject scholarly slide-structure guidance for an
        # academic deck (problem→methods→results→discussion + slide-type rules).
        # Same knowledge the creative deck path already uses — here it reaches the
        # convert-to-pptx path too. Guarded: any miss → prompt unchanged.
        try:
            import os as _os
            _sp = _os.path.abspath(_os.path.join(
                _os.path.dirname(__file__), "..", "capabilities", "skills",
                "academic_content", "scripts"))
            import sys as _sys
            if _sp not in _sys.path:
                _sys.path.insert(0, _sp)
            import academic_content as _ac
            _g = _ac.build_guidance((content or "")[:400], lang)
            if _g:
                prompt = prompt + "\n" + _g
        except Exception:
            pass
        data = extract_json(llm_fn(prompt, temperature=0.3)) or {}
        slides = data.get("slides") or []
        out = []
        for s in slides:
            if not isinstance(s, dict):
                continue
            bl = [str(b).strip() for b in (s.get("bullets") or []) if str(b).strip()]
            out.append({"heading": str(s.get("title", "")).strip(),
                        "body": "\n".join("- " + b for b in bl)})
        return out or None
    except Exception:
        return None


def _content_to_table(llm_fn, content, lang="ar"):
    """Ask the model to extract a table from content. Returns
    {"headers":[...], "rows":[[...],...]} or None."""
    if not llm_fn:
        return None
    try:
        from core.llm import extract_json
        prompt = (
            "استخرج من المحتوى التالي جدولاً منظّماً. أعِد JSON فقط: "
            "{\"headers\":[\"عمود1\",\"عمود2\",...],\"rows\":[[\"..\",\"..\"],...]}"
            " — إن كان المحتوى نقاطاً، اجعل عمودين: \"النقطة\" و\"التفصيل\". دون "
            "أي نص خارج JSON:\n\n"
            if lang == "ar" else
            "Extract a structured table from the content. Return JSON only: "
            "{\"headers\":[...],\"rows\":[[...],...]} — if it's bullet points use "
            "two columns \"Point\" and \"Detail\". Nothing outside JSON:\n\n"
        ) + (content or "")[:9000]
        data = extract_json(llm_fn(prompt, temperature=0.2)) or {}
        headers = data.get("headers") or []
        rows = data.get("rows") or []
        rows = [[str(c) for c in r] for r in rows if isinstance(r, list) and r]
        if headers and rows:
            return {"headers": [str(h) for h in headers], "rows": rows}
        return None
    except Exception:
        return None


def classify_intent(request, llm_fn=None, system=None):
    """Model-based intent classifier shared by the pipeline (layer 3) AND the web
    layer's routing (export-previous vs new task). Returns a normalized intent
    dict, or None when the model is unavailable or its reply is unusable — so the
    caller's keyword logic remains the fallback. Classification only.

    This is the "understanding first" layer applied to the WHOLE system: the same
    model that writes also decides what the user meant, instead of keyword lists.
    """
    req = (request or "").strip()
    if not req:
        return None
    if llm_fn is None:
        try:
            from core.llm import get_llm_fn
            llm_fn = get_llm_fn()
        except Exception:
            llm_fn = None
    if not llm_fn:
        return None
    try:
        import os
        prompt = (
            "أنت مصنِّف نيّة دقيق. اقرأ طلب المستخدم وأعد JSON فقط (بلا أي نص "
            "آخر) يصف ما يريده، دون تنفيذ الطلب. الحقول:\n"
            '{"action":"research|rewrite|summarize|translate|convert|edit|chat",'
            '"scopes":[من "references","outline","plan","part"],'
            '"format":"docx|pdf|pptx|xlsx|csv|txt|html|inline|null",'
            '"on_previous":true|false,'
            '"mabhath_count":عدد|null,"matlab_count":عدد|null,'
            '"slide_count":عدد|null,"words":عدد|null,"pages":عدد|null,'
            '"language":"ar|en|null","wants_table":true|false,'
            '"wants_chart":true|false,"wants_data":true|false}\n'
            "تعريفات دقيقة:\n"
            "- action: research=إنتاج مستند/بحث/تقرير مكتوب جديد (ملف أو نصّ "
            "طويل مُنظَّم يطلبه المستخدم صراحةً)؛ rewrite=إعادة صياغة نص؛ "
            "summarize=تلخيص؛ translate=ترجمة؛ convert=تحويل/إخراج ناتجٍ سابق إلى "
            "ملف بصيغة (مثل «ضيف/أخرج/حوّل هذا الملخص إلى وورد»)؛ edit=تعديل/إلحاق "
            "على ملف؛ chat=أي سؤال أو استفسار أو طلب معلومة يُجاب مباشرةً بلا "
            "إنتاج ملف — ويشمل: أخبار اليوم وآخر المستجدّات، البحث عن تطبيق أو "
            "منتج أو سعر، تعريف أو شرح أو مقارنة معرفية، أو أي بحث عن شيء.\n"
            "قاعدة حاسمة: احتياج الطلب لبحثٍ في الإنترنت لا يجعله research. سؤال "
            "الأخبار أو البحث عن تطبيق/معلومة = chat يُجاب مباشرةً (ولو تطلّب "
            "بحثاً حيّاً). اجعله research فقط حين يطلب المستخدم صراحةً كتابة/إنتاج "
            "مستندٍ أو بحثٍ أو تقرير.\n"
            "- on_previous: true إن كان الطلب يتعامل مع ناتجٍ/ردٍّ سابق (هذا "
            "الملخص/الرد/ما سبق) لا موضوعاً جديداً.\n"
            "- scopes (فارغة=مستند كامل): references=مصادر فقط؛ outline=هيكل فقط؛ "
            "plan=خطة/مقترح؛ part=جزء محدد.\n"
            "- mabhath_count/matlab_count: عند طلب عددٍ صريح.\n"
            "- language: لغة المخرجات إن طُلبت صراحةً، وإلا null.\n"
            "- بحث كامل عادي: action=research وscopes=[].\n"
            "طلب المستخدم:\n" + req[:1500]
        )
        from core.llm import extract_json
        # classification is a TINY reply; give it a SHORT own timeout and a small
        # token cap so a slow on-device model fails fast to the keyword fallback
        # instead of eating the task's time budget (which caused read timeouts).
        try:
            _to = int(os.environ.get("WEAVER_INTENT_TIMEOUT", "30") or 30)
        except Exception:
            _to = 30
        try:
            raw = llm_fn(prompt, system=system, temperature=0.0,
                         max_tokens=400, timeout=_to) or ""
        except TypeError:
            # a custom llm_fn without the new kwargs
            raw = llm_fn(prompt, system=system, temperature=0.0) or ""
        try:
            data = extract_json(raw)
        except Exception:
            data = None
        if not isinstance(data, dict):
            return None
        return WeaverOrchestrator._normalize_intent(data)
    except Exception:
        return None


def capability_catalog(lang="ar"):
    """A concise MENU of everything Weaver can actually do — task types, scopes,
    formats, in-document inserts, sources, targets, counts, language. It is handed
    to the unified understanding step so the model chooses from REAL capabilities
    instead of us guessing with keyword lists. Pure text; no side effects.

    Step 1 of making the model the brain: this is the vocabulary the brain speaks.
    """
    if lang == "en":
        return (
            "Available system capabilities (choose by understanding the request):\n"
            "- action: research=new writing/research; rewrite=rephrase text; "
            "summarize; translate; convert=render a previous output/content into a "
            "file format; edit=modify/append inside a file; chat=Q&A that produces "
            "no file.\n"
            "- scopes (empty=full document): references=sources only; outline=research "
            "structure only; plan=research proposal; part=one specific part only.\n"
            "- format (YOU direct the right builder — choose by MEANING, not just "
            "an explicit word): pptx=a presentation/slides; xlsx=a data table/"
            "spreadsheet/calculations; csv=comma-separated data; pdf=when PDF is "
            "asked; docx=a written document/report/research (default for written "
            "documents); txt=plain text; html=a web page; inline=a short answer/"
            "info shown in chat, no file.\n"
            "- in-document inserts: wants_table, wants_chart, wants_data (find "
            "numbers/statistics).\n"
            "- source: topic=a textual subject; previous_output=an earlier reply/"
            "output; pasted_link=a page/YouTube link to read/transcribe; "
            "attached_file=a Word/PDF/Excel/image whose content is read; "
            "instructions_in_file=the instructions live inside the attached file.\n"
            "- target: inline=in chat; new_file=a new file; same_file=the attached "
            "file itself; specific_file=a file named explicitly.\n"
            "- counts when asked: mabhath_count, matlab_count, slide_count, words, "
            "pages.\n"
            "- language: the requested output language, or the attached file's own "
            "language, else null.\n"
            "- one request may contain MORE THAN ONE task (multiple tasks).")
    return (
        "قدرات النظام المتاحة (اختر منها بحسب فهمك للطلب):\n"
        "• أنواع المهام (action): research=كتابة/بحث جديد؛ rewrite=إعادة صياغة نص؛ "
        "summarize=تلخيص؛ translate=ترجمة؛ convert=تحويل ناتجٍ/محتوى سابق إلى ملف "
        "بصيغة؛ edit=تعديل/إلحاق داخل ملف؛ chat=حوار/سؤال لا يُنتج ملفاً.\n"
        "• النطاقات (scopes، فارغة=مستند كامل): references=مصادر/مراجع فقط؛ "
        "outline=هيكل بحثي فقط؛ plan=خطة/مقترح بحثي؛ part=جزء محدّد فقط.\n"
        "• الصيغ (format) — أنت من يوجّه الباني المناسب، فاخترها بالمعنى لا "
        "بالكلمة الصريحة فقط: pptx=عرض تقديمي/شرائح؛ xlsx=جدول بيانات/حسابات/"
        "شيت؛ csv=بيانات مفصولة بفواصل؛ pdf=حين يُطلب PDF؛ docx=مستند/بحث/تقرير "
        "مكتوب (الافتراضي للمستندات المكتوبة)؛ txt=نصّ خام؛ html=صفحة ويب؛ "
        "inline=إجابة/معلومة قصيرة تُعرض في المحادثة بلا ملف.\n"
        "• إدراجات داخل المستند: wants_table=جدول، wants_chart=رسم بياني، "
        "wants_data=إيجاد بيانات/أرقام.\n"
        "• المصدر (source): topic=موضوع نصّي؛ previous_output=ناتج/ردّ سابق؛ "
        "pasted_link=رابط مُدرَج (صفحة/يوتيوب) يُقرأ ويُفرَّغ؛ attached_file=ملف "
        "مرفق (وورد/PDF/إكسل/صورة) يُقرأ محتواه؛ instructions_in_file=التعليمات "
        "داخل نفس الملف المرفق.\n"
        "• الهدف (target): inline=في المحادثة؛ new_file=ملف جديد؛ same_file=نفس "
        "الملف المرفق؛ specific_file=ملف باسمٍ محدّد.\n"
        "• الأعداد عند طلبها: mabhath_count, matlab_count, slide_count, words, "
        "pages.\n"
        "• اللغة (language): لغة المخرجات المطلوبة صراحةً أو لغة الملف الأصلية، "
        "وإلا null.\n"
        "• قد يحوي الطلب الواحد أكثر من مهمة (tasks متعدّدة).")


def _normalize_plan(d):
    """Validate the unified understanding JSON into safe types. Reuses
    _normalize_intent for each task's shared fields and adds the plan-only fields
    (topic / source / target / target_file). Returns a plan dict with a non-empty
    `tasks` list, or None when unusable."""
    if not isinstance(d, dict):
        return None
    tasks_in = d.get("tasks")
    # tolerate a single-task shape ({action:..} without a tasks[] wrapper)
    if not tasks_in and isinstance(d.get("action"), str):
        tasks_in = [d]
    if not isinstance(tasks_in, list) or not tasks_in:
        return None
    _src_ok = ("topic", "previous_output", "pasted_link", "attached_file",
               "instructions_in_file")
    _tgt_ok = ("inline", "new_file", "same_file", "specific_file")
    out_tasks = []
    for t in tasks_in:
        if not isinstance(t, dict):
            continue
        base = WeaverOrchestrator._normalize_intent(t)
        src = str(t.get("source", "") or "").lower().strip()
        base["source"] = src if src in _src_ok else None
        tgt = str(t.get("target", "") or "").lower().strip()
        base["target"] = tgt if tgt in _tgt_ok else None
        tf = str(t.get("target_file", "") or "").strip()
        base["target_file"] = tf[:200] or None
        tp = str(t.get("topic", "") or "").strip()
        base["topic"] = tp[:300] or None
        out_tasks.append(base)
    if not out_tasks:
        return None
    lang = str(d.get("language", "") or "").lower().strip()
    return {"language": lang if lang in ("ar", "en") else None,
            "tasks": out_tasks}


def understand_request(conversation, request, attachments=None, llm_fn=None,
                       system=None):
    """UNIFIED UNDERSTANDING — the brain. Give the model the FULL conversation,
    any attachment/link info, and the capability catalog, and let IT produce a
    complete execution PLAN (one or more tasks) instead of hand-coded keyword
    detection. This is what lets any phrasing/dialect/language be understood, and
    what stops the second message from forgetting the first (full context in, not
    a stripped single line).

    Returns a normalized plan dict, or None when the model is unavailable or its
    reply is unusable (callers keep the keyword + classify_intent fallback).
    Classification only — never writes or executes.

    DORMANT for now: built and tested here, wired into the pipeline in the next
    step so behaviour is unchanged until then."""
    req = (request or "").strip()
    convo = (conversation or "").strip()
    if not req and not convo:
        return None
    if llm_fn is None:
        try:
            from core.llm import get_llm_fn
            llm_fn = get_llm_fn()
        except Exception:
            llm_fn = None
    if not llm_fn:
        return None
    try:
        import os
        cat = capability_catalog("ar")
        att = ""
        if attachments:
            att = ("الملفات/الروابط المرفقة:\n"
                   + "\n".join("- " + str(a) for a in attachments) + "\n\n")
        prompt = (
            "أنت عقل التخطيط في نظام كتابة بحثي. اقرأ المحادثة كاملةً والطلب "
            "الحالي، وحدِّد ما يريده المستخدم فعلاً — دون تنفيذ — وأعِد JSON فقط "
            "(بلا أي نص آخر).\n\n" + cat + "\n\n"
            "أعِد الخطة بهذا الشكل بالضبط:\n"
            '{"language":"ar|en|null","tasks":[{'
            '"action":"research|rewrite|summarize|translate|convert|edit|chat",'
            '"scopes":[من "references","outline","plan","part"],'
            '"format":"docx|pdf|pptx|xlsx|csv|txt|html|inline|null",'
            '"language":"ar|en|null",'
            '"topic":"موضوع المهمة","source":"topic|previous_output|pasted_link|'
            'attached_file|instructions_in_file",'
            '"target":"inline|new_file|same_file|specific_file",'
            '"target_file":"اسم|null","on_previous":true|false,'
            '"mabhath_count":عدد|null,"matlab_count":عدد|null,'
            '"slide_count":عدد|null,"words":عدد|null,"pages":عدد|null,'
            '"wants_table":true|false,"wants_chart":true|false,'
            '"wants_data":true|false,"needs_sources":true|false}]}\n\n'
            "قواعد مهمة:\n"
            "- استعمل المحادثة كاملةً لتحديد الموضوع: إن كان الطلب الحالي تعليمةَ "
            "تنسيق (مثل «اجعلها 3 مباحث») دون ذكر الموضوع، فخذ الموضوع من الرسائل "
            "السابقة ولا تسأل عنه.\n"
            "- إن طلب المستخدم أكثر من شيء، اجعل tasks متعدّدة بالترتيب.\n"
            "- بحث كامل عادي: action=research وscopes=[].\n"
            "- needs_sources: اجعلها true فقط إذا كانت الإجابة تحتاج فعلاً مصادر "
            "خارجية أو بحثاً حياً — أي: أحداث/إحصاءات/أسعار حديثة، أو أرقام واقعية "
            "محدّدة، أو مراجع/دراسات مطلوبة، أو معلومة متغيّرة بمرور الوقت. واجعلها "
            "false إذا كان الطلب معرفةً عامّة ثابتة يعرفها النموذج (شرح، تعريف، "
            "مقارنة بين مفهومين معروفين، جدول من معلومات معروفة)، أو كتابةً "
            "إبداعية، أو تعاملاً مع نصّ/ملف مُعطى (تلخيص/ترجمة/إعادة صياغة). عند "
            "الشكّ اجعلها true.\n\n"
            + att + "المحادثة (الأقدم فالأحدث):\n" + convo[:4000] + "\n\n"
            "الطلب الحالي:\n" + req[:1500])
        from core.llm import extract_json
        try:
            _to = int(os.environ.get("WEAVER_UNDERSTAND_TIMEOUT", "45") or 45)
        except Exception:
            _to = 45
        try:
            raw = llm_fn(prompt, system=system, temperature=0.0,
                         max_tokens=700, timeout=_to) or ""
        except TypeError:
            raw = llm_fn(prompt, system=system, temperature=0.0) or ""
        try:
            data = extract_json(raw)
        except Exception:
            data = None
        return _normalize_plan(data)
    except Exception:
        return None


# ── requirement kinds: a SMALL controlled vocabulary that lets a later, generic
#    verifier route "is this satisfied?" checks. The requirement TEXT stays the
#    user's own words (any topic, any count, any language) — nothing here is
#    hardcoded to a subject. Unknown kinds are kept as "other" (never dropped).
_REQ_KINDS = ("deliverable", "structure", "length", "section", "insert",
              "content", "source", "style", "language", "format", "other")
# what the user ultimately wants PRODUCED — decided by MEANING, not keywords.
# This is the field that fixes the proven scope mis-routing: a "بحث بالكامل"
# request resolves to full_document even when it also says "الهيكلة مكوّنة من…".
_DELIVERABLES = ("full_document", "outline", "references", "plan", "part",
                 "answer", "rewrite", "summary", "translation", "conversion",
                 "edit")


def _normalize_requirements(d):
    """Validate the requirements-extraction JSON into safe types. Returns a dict
    with a `requirements` list (possibly empty) plus `deliverable`/`language`/
    `task_kind`/`notes`, or None when the payload is unusable. Never raises."""
    if not isinstance(d, dict):
        return None

    def _clip(v, n):
        return (str(v or "").strip())[:n]

    def _num_or_str(v):
        # keep an explicit number as int, otherwise a short free-form target
        if isinstance(v, bool) or v is None:
            return None
        if isinstance(v, (int, float)):
            try:
                return int(v)
            except (TypeError, ValueError, OverflowError):
                return None
        s = str(v).strip()
        return s[:120] or None

    dv = _clip(d.get("deliverable"), 40).lower()
    deliverable = dv if dv in _DELIVERABLES else None

    reqs_in = d.get("requirements")
    if isinstance(reqs_in, dict):          # tolerate a single-object shape
        reqs_in = [reqs_in]
    out_reqs = []
    if isinstance(reqs_in, list):
        seen_ids = set()
        for i, r in enumerate(reqs_in):
            if not isinstance(r, dict):
                # tolerate a bare string requirement
                if isinstance(r, str) and r.strip():
                    r = {"text": r}
                else:
                    continue
            text = _clip(r.get("text") or r.get("requirement") or r.get("name"),
                         300)
            if not text:
                continue
            kind = _clip(r.get("kind") or r.get("type"), 20).lower()
            if kind not in _REQ_KINDS:
                kind = "other"
            rid = _clip(r.get("id"), 40) or f"{kind}_{i + 1}"
            # keep ids unique so a later verifier can address each one
            if rid in seen_ids:
                rid = f"{rid}_{i + 1}"
            seen_ids.add(rid)
            must = r.get("must")
            must = True if must is None else bool(must)   # default: required
            out_reqs.append({
                "id": rid,
                "text": text,
                "kind": kind,
                "target": _num_or_str(r.get("target")),
                "must": must,
            })

    lang = _clip(d.get("language"), 8).lower()
    return {
        "task_kind": _clip(d.get("task_kind"), 200) or None,
        "deliverable": deliverable,
        "requirements": out_reqs,
        "language": lang if lang in ("ar", "en") else None,
        "notes": _clip(d.get("notes"), 400) or None,
    }


def extract_requirements(conversation, request, attachments=None, llm_fn=None,
                         system=None):
    """STAGE (أ) of Plan+Verify — REQUIREMENTS EXTRACTION (model-agnostic).

    Reads the FULL request and the FULL conversation — NO truncation. (The older
    understand_request/classify_intent capped input at req[:1500]/convo[:4000],
    which silently dropped half of a long, detailed instruction — one proven
    cause of forgotten requirements like a cover page or a 10-page length.) It
    asks the connected model — ANY model, on any platform — to read the request
    and return a DYNAMIC requirements checklist: the concrete, checkable things
    the user actually asked for, in the user's own words. Nothing here is
    hardcoded to a topic, a structure (3×3 or otherwise), or a keyword list —
    the model decides, and the checklist is whatever THIS request contains.

    Two things it fixes at the root:
      • `deliverable` is decided by MEANING, so "أريد بحثاً بالكامل … الهيكلة
        مكوّنة من…" resolves to full_document, not the keyword-guessed "outline".
      • every concrete ask (غلاف، فهرس، عدد صفحات، جداول بمصطلحات، عدد مباحث/
        مطالب…) becomes an explicit, addressable checklist item a later verify
        stage can confirm was actually delivered.

    Returns a normalized dict (see _normalize_requirements) or None when the
    model is unavailable or its reply is unusable — callers keep their existing
    behaviour, so no fallback is ever removed.

    DORMANT for now: built and verified here; wired into the pipeline in the
    next approved step, so behaviour is unchanged until then. Classification
    only — it never writes or executes."""
    req = (request or "").strip()
    convo = (conversation or "").strip()
    if not req and not convo:
        return None
    if llm_fn is None:
        try:
            from core.llm import get_llm_fn
            llm_fn = get_llm_fn()
        except Exception:
            llm_fn = None
    if not llm_fn:
        return None
    try:
        import os
        att = ""
        if attachments:
            att = ("الملفات/الروابط المرفقة:\n"
                   + "\n".join("- " + str(a) for a in attachments) + "\n\n")
        prompt = (
            "أنت محلّل متطلّبات دقيق في نظام كتابةٍ بحثيّ. مهمتك أن تقرأ طلب "
            "المستخدم كاملاً (والمحادثة كلها) وتستخرج «قائمة المتطلّبات»: كل "
            "شيءٍ محدّدٍ طلبه المستخدم فعلاً، بكلماته هو، دون تنفيذ الطلب ودون "
            "إضافة متطلّباتٍ لم يذكرها. أعِد JSON فقط بلا أي نصٍّ آخر.\n\n"
            "الشكل المطلوب بالضبط:\n"
            '{"task_kind":"وصفٌ حرٌّ قصير لما يريده المستخدم",'
            '"deliverable":"full_document|outline|references|plan|part|answer|'
            'rewrite|summary|translation|conversion|edit",'
            '"language":"ar|en|null",'
            '"requirements":[{"id":"معرّف_قصير","text":"المتطلّب بكلمات المستخدم",'
            '"kind":"deliverable|structure|length|section|insert|content|source|'
            'style|language|format|other","target":عدد أو نص أو null,'
            '"must":true|false}],'
            '"notes":"ملاحظاتٌ قصيرة أو null"}\n\n'
            "قواعد حاسمة:\n"
            "- deliverable يُحدَّد بالمعنى لا بمطابقة كلمة: إن طلب المستخدم بحثاً/"
            "مستنداً/تقريراً مكتوباً كاملاً فهو full_document، حتى لو وصف هيكله في "
            "نفس الرسالة (وصف الهيكل ليس طلباً للهيكل وحده). لا تجعله outline إلا "
            "إذا طلب المستخدم الهيكل/العناصر فقط دون كتابة المحتوى.\n"
            "- استخرج كل متطلّبٍ ملموسٍ قابلٍ للتحقّق ذكره المستخدم، منها مثلاً "
            "(إن وُجدت فقط، ولا تختلق شيئاً): نوع المخرَج، عدد المباحث/المطالب "
            "وأيّ تقسيماتٍ أعمق، عدد الصفحات أو الكلمات، صفحة غلاف، فهرس/جدول "
            "محتويات، جداول (وما يجب أن تحتويه كمصطلحاتٍ أو مقارنة)، رسوم بيانية، "
            "مصادر/مراجع/دراسات وتوثيقها، لغة المخرجات، الأسلوب (أكاديمي/بشري/"
            "سردي/نقطي)، أقسامٌ بعينها يجب أن تُذكر. اجعل كل واحدٍ عنصراً مستقلاً.\n"
            "- target: ضع فيه القيمة المحدّدة إن ذُكرت (عدد الصفحات، عدد المباحث، "
            "اسم قسم…) وإلا null. must=true للمتطلّب الإلزاميّ، false للمرغوب.\n"
            "- إن لم يذكر المستخدم متطلّباتٍ تفصيلية، أعِد requirements كقائمةٍ "
            "فارغة [] مع تحديد deliverable وtask_kind فقط. لا تختلق متطلّبات.\n"
            "- language: لغة المخرجات إن طُلبت صراحةً، وإلا null.\n\n"
            + att + "المحادثة (الأقدم فالأحدث):\n" + convo + "\n\n"
            "الطلب الحالي (اقرأه كاملاً):\n" + req)
        from core.llm import extract_json
        try:
            _to = int(os.environ.get("WEAVER_REQUIREMENTS_TIMEOUT", "60") or 60)
        except Exception:
            _to = 60
        try:
            raw = llm_fn(prompt, system=system, temperature=0.0,
                         max_tokens=1200, timeout=_to) or ""
        except TypeError:
            raw = llm_fn(prompt, system=system, temperature=0.0) or ""
        try:
            data = extract_json(raw)
        except Exception:
            data = None
        return _normalize_requirements(data)
    except Exception:
        return None


# ── STAGE (ج): VERIFY ────────────────────────────────────────────────────────
# The verifier takes the requirements checklist from extract_requirements and the
# PRODUCED output, and reports — requirement by requirement — what was actually
# delivered, BEFORE export. Design: measure what can be measured EXACTLY (word/
# page count, a table's presence, cover/TOC flags, output language) with no model
# at all (so it behaves identically with ANY model), and let the model JUDGE only
# what needs judgement (content, style, "the tables carry technical terms"). It
# NEVER claims a requirement failed on a guess: when it cannot tell, it says
# "unknown", so honest reporting is preserved and no genuine work is discarded.

def _vr_words(text):
    """Whitespace word count of the draft (a good proxy for both Arabic and
    English length). Markdown markup counts too — a harmless over-count."""
    import re
    return len(re.findall(r"\S+", text or ""))


def _vr_arabic_ratio(text):
    """Fraction of letters that are Arabic — used to confirm output language."""
    ar = other = 0
    for ch in (text or ""):
        if "؀" <= ch <= "ۿ":
            ar += 1
        elif ch.isalpha():
            other += 1
    tot = ar + other
    return (ar / tot) if tot else 0.0


def _vr_headings(text):
    """Return the list of Markdown heading lines (without the leading #s)."""
    import re
    out = []
    for line in (text or "").splitlines():
        m = re.match(r"\s{0,3}(#{1,6})\s+(.*\S)\s*$", line)
        if m:
            out.append(m.group(2).strip())
    return out


_VR_AR_NUM = {
    "واحد": 1, "واحدة": 1, "اثنان": 2, "اثنين": 2, "اثنتان": 2, "اثنتين": 2,
    "ثلاثة": 3, "ثلاث": 3, "أربعة": 4, "اربعة": 4, "أربع": 4, "اربع": 4,
    "خمسة": 5, "خمس": 5, "ستة": 6, "ست": 6, "سبعة": 7, "سبع": 7,
    "ثمانية": 8, "ثماني": 8, "تسعة": 9, "تسع": 9, "عشرة": 10, "عشر": 10,
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9, "ten": 10,
}


def _vr_numbers(text):
    """Read the counts stated in a requirement, IN ORDER, from digits or from
    number WORDS ("ثلاثة مباحث، كل مبحث فيه أربعة مطالب" → [3, 4]). Needed so a
    two-level structure rule is checked against the numbers the user actually
    said instead of assuming the same number twice. Never raises."""
    import re as _re
    out = []
    try:
        for tok in _re.findall(r"[0-9٠-٩]+|[^\W\d_]+",
                               (text or ""), _re.UNICODE):
            if tok[0].isdigit() or "٠" <= tok[0] <= "٩":
                t = tok.translate(str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789"))
                try:
                    out.append(int(t))
                except ValueError:
                    pass
            else:
                n = _VR_AR_NUM.get(tok.strip("ًٌٍَُِّْ").lower())
                if n:
                    out.append(n)
    except Exception:
        return out
    return out


def _vr_has_table(text):
    """True when the draft contains a Markdown table (a separator row like
    |---|---| is the reliable signal)."""
    import re
    for line in (text or "").splitlines():
        s = line.strip()
        if s.count("|") >= 2 and re.match(r"^\|?\s*:?-{2,}", s.replace(" ", "")):
            return True
    # also accept a header row immediately followed by a separator
    return bool(re.search(r"\n.*\|.*\n\s*\|?\s*:?-{2,}", "\n" + (text or "")))


def _vr_page_target(req):
    """If a length requirement is expressed in PAGES, return that page count,
    else None. Reads the requirement text + target; never guesses a topic.

    A RANGE cannot fit in one integer, so «لا يقل عن 10 صفحات ولا يزيد عن 12»
    came back with target=None and the whole length check degraded to
    "unknown — لا هدف رقمي محدّد" even though both numbers were sitting in the
    requirement's own text. The floor is read from that text as a fallback."""
    t = (req.get("text") or "").lower()
    is_pages = any(k in t for k in ("صفح", "page"))
    if not is_pages:
        return None
    tgt = req.get("target")
    if isinstance(tgt, int) and not isinstance(tgt, bool):
        return tgt
    nums = [n for n in _vr_numbers(req.get("text") or "") if 1 <= n <= 2000]
    return nums[0] if nums else None


def _verify_deterministic(req, draft, card, lang):
    """Try to settle ONE requirement by exact measurement. Returns
    (status, evidence) with status in {"met","unmet","unknown"}, or None when
    this requirement isn't deterministically checkable (→ defer to the model).
    Conservative: returns "unknown" instead of "unmet" whenever unsure, so we
    never wrongly report a delivered requirement as missing."""
    import os
    kind = req.get("kind")
    text = (req.get("text") or "").lower()
    card = card or {}

    # ── COVER / TABLE OF CONTENTS — settled from the CARD, whatever the model
    #    labelled the requirement. These are EXPORT-time features: they never
    #    appear in the draft text, so if this check is skipped the requirement
    #    falls through to the model, which reads only the draft and always
    #    reports them missing — a false failure on a document that HAS them.
    if any(k in text for k in ("غلاف", "cover page", "title page")) or (
            "cover" in text):
        if card.get("cover"):
            return ("met", "الغلاف مطلوبٌ ومضبوط (يُبنى عند التصدير)")
        return (("unmet" if "cover" in card else "unknown"),
                "لا علامة غلاف في البطاقة")
    if any(k in text for k in ("فهرس", "محتويات", "toc",
                               "table of contents", "index page")):
        if card.get("toc"):
            return ("met", "الفهرس مطلوبٌ ومضبوط (يُبنى عند التصدير)")
        return (("unmet" if "toc" in card else "unknown"),
                "لا علامة فهرس في البطاقة")

    # ── length: words or pages ──
    if kind == "length":
        words = _vr_words(draft)
        pages_tgt = _vr_page_target(req)
        if pages_tgt:
            try:
                wpp = int(os.environ.get("WEAVER_WORDS_PER_PAGE", "300") or 300)
            except Exception:
                wpp = 300
            est_pages = words / max(1, wpp)
            # a CEILING in the same requirement ("لا يزيد عن 12 صفحة") is a
            # failure too — the check only ever tested the floor
            _mx = None
            try:
                _mx = (card or {}).get("max_pages")
                if not _mx:
                    # the ceiling may live only in the requirement's own text
                    _ns = [n for n in _vr_numbers(req.get("text") or "")
                           if 1 <= n <= 2000]
                    if len(_ns) >= 2 and _ns[1] > _ns[0]:
                        _mx = _ns[1]
            except Exception:
                _mx = None
            # a PDF export gives a MEASURED page count — prefer it over the
            # words-per-page estimate, which is only ever an approximation
            try:
                _real = (card or {}).get("actual_pages")
                if _real:
                    est_pages = float(_real)
                    wpp = "مقيس"
            except Exception:
                pass
            ev = f"~{est_pages:.1f} صفحة ({words} كلمة، {wpp}/صفحة) مقابل " \
                 f"مطلوب ≥{pages_tgt}" + (f" و≤{_mx}" if _mx else "")
            if _mx and est_pages > _mx * 1.05:
                return ("unmet", ev + " — تجاوز الحدّ الأقصى")
            # "at least" semantics with a small tolerance
            return (("met" if est_pages >= pages_tgt * 0.95 else "unmet"), ev)
        tgt = req.get("target")
        if isinstance(tgt, int):
            ev = f"{words} كلمة مقابل مطلوب ≥{tgt}"
            return (("met" if words >= tgt * 0.95 else "unmet"), ev)
        return ("unknown", f"{words} كلمة (لا هدف رقمي محدّد)")

    # ── language of the output ──
    if kind == "language":
        tgt = str(req.get("target") or "").lower()
        want_ar = ("ar" in tgt or "عرب" in text)
        want_en = ("en" in tgt or "انجل" in text or "إنجل" in text
                   or "english" in text)
        ratio = _vr_arabic_ratio(draft)
        if want_ar:
            return (("met" if ratio >= 0.6 else "unmet"),
                    f"نسبة العربية {ratio:.0%}")
        if want_en:
            return (("met" if ratio <= 0.4 else "unmet"),
                    f"نسبة العربية {ratio:.0%}")
        return None

    # ── inserts: table/references live in the draft (cover/TOC are settled
    #    above, for ANY kind, because they are invisible in the draft) ─
    if kind == "insert":
        if "جدول" in text or "table" in text:
            # presence is deterministic; whether it holds the RIGHT content
            # (e.g. technical terms) is a judgement → defer that part to model
            if not _vr_has_table(draft):
                return ("unmet", "لا جدول في المخرَج")
            # a table exists but the requirement adds a content condition
            if any(k in text for k in ("مصطلح", "تقني", "مقارنة", "term",
                                       "technical", "comparison")):
                return None            # let the model judge the table content
            return ("met", "يوجد جدول في المخرَج")
        if any(k in text for k in ("مراجع", "مصادر", "references",
                                   "bibliography")):
            heads = " ".join(_vr_headings(draft)).lower()
            has = any(k in heads for k in ("مراجع", "مصادر", "references",
                                           "bibliography"))
            return (("met" if has else "unmet"),
                    "قسم المراجع " + ("موجود" if has else "غير موجود"))
        return None

    # ── structure: count matching headings ──
    if kind == "structure":
        tgt = req.get("target")
        if isinstance(tgt, bool):
            tgt = None
        if not isinstance(tgt, int):
            # A compound rule («ثلاثة مباحث، كل مبحث فيه ثلاثة مطالب، وكل مطلب
            # تقسيمات») cannot be expressed as one integer, so the model returns
            # target=None — and the whole check then went to the model, which
            # judged a TRUNCATED draft and twice reported a مبحث missing that was
            # demonstrably present. The counts are in the requirement's own text.
            _ns = [n for n in _vr_numbers(req.get("text") or "")
                   if 1 <= n <= 200]
            tgt = _ns[0] if _ns else None
        if isinstance(tgt, int):
            # map the requirement wording (often a PLURAL like «مباحث») to the
            # singular STEM that appears in the headings («المبحث الأول»).
            groups = (
                (("مبحث", "مباحث"), "مبحث"),
                (("مطلب", "مطالب"), "مطلب"),
                (("فصل", "فصول"), "فصل"),
                (("باب", "أبواب", "ابواب"), "باب"),
                (("section", "sections"), "section"),
                (("chapter", "chapters"), "chapter"),
            )
            # A requirement may name TWO levels at once — «ثلاثة مباحث، كل مبحث
            # فيه ثلاثة مطالب». That whole case used to be handed to the model
            # (`"كل" not in text`), which then judged a TRUNCATED draft and
            # reported a مبحث missing that was demonstrably present. Counting
            # both stems settles it exactly, with no model and no truncation.
            stems = [s for triggers, s in groups
                     if any(k in text for k in triggers)]
            if stems:
                heads = [h.lower() for h in _vr_headings(draft)]
                counts = [(s, sum(1 for h in heads if s in h)) for s in stems]
                if all(c == 0 for _s, c in counts):
                    return None       # wording may differ from headings → model
                # "N X, each X has M Y": the outer count is `target`; the inner
                # one is target×target when the rule repeats the same number,
                # which is the only per-section form a single int can express.
                if len(counts) >= 2 and ("كل" in text or " each " in text):
                    (s1, c1), (s2, c2) = counts[0], counts[1]
                    # the INNER number is read from the requirement text, so
                    # "ثلاثة مباحث، كل مبحث فيه أربعة مطالب" needs 3×4, not 3×3
                    _nums = _vr_numbers(text)
                    _inner = _nums[1] if len(_nums) >= 2 else None
                    if _inner:
                        need2 = tgt * _inner
                        ok = (c1 >= tgt and c2 >= need2)
                        return (("met" if ok else "unmet"),
                                f"«{s1}» = {c1} مقابل {tgt} · "
                                f"«{s2}» = {c2} مقابل {need2}")
                    # inner number unreadable → judge the outer level only and
                    # report the inner count rather than guess at it
                    return (("met" if c1 >= tgt else "unmet"),
                            f"«{s1}» = {c1} مقابل {tgt} · «{s2}» = {c2}")
                s, cnt = counts[0]
                if cnt == 0:
                    return None
                return (("met" if cnt >= tgt else "unmet"),
                        f"عدد العناوين المطابقة لـ«{s}» = {cnt} مقابل {tgt}")
        return None

    return None


def verify_requirements(requirements, draft, card=None, lang="ar", llm_fn=None,
                        system=None):
    """STAGE (ج) — verify the produced output against the requirements checklist.

    `requirements`: the list from extract_requirements()["requirements"].
    `draft`: the assembled document text (Markdown). `card`: the task card (for
    cover/toc flags). Returns:
      {"results":[{"id","text","kind","must","status","evidence","by"}],
       "unmet":[ids of MUST requirements not confirmed met],
       "all_met": bool,          # every MUST requirement is "met"
       "summary": str}
    status ∈ {"met","unmet","partial","unknown"}. Deterministic checks settle
    what they can with NO model; the rest go to the model in ONE call. When the
    model is unavailable those stay "unknown" (never a false "unmet"). Never
    raises — returns None only when there are no requirements to check."""
    reqs = [r for r in (requirements or []) if isinstance(r, dict)
            and (r.get("text") or "").strip()]
    if not reqs:
        return None
    draft = draft or ""
    card = card or {}

    results = []
    to_model = []          # requirements needing the model's judgement
    for r in reqs:
        try:
            det = _verify_deterministic(r, draft, card, lang)
        except Exception:
            det = None
        if det is not None:
            status, ev = det
            results.append({"id": r.get("id"), "text": r.get("text"),
                            "kind": r.get("kind"), "must": bool(r.get("must")),
                            "status": status, "evidence": ev,
                            "by": "deterministic"})
        else:
            to_model.append(r)

    # ── model judgement for the remainder (content / style / conditional) ──
    verdicts = {}
    if to_model:
        if llm_fn is None:
            try:
                from core.llm import get_llm_fn
                llm_fn = get_llm_fn()
            except Exception:
                llm_fn = None
        if llm_fn:
            try:
                import os
                from core.llm import extract_json
                try:
                    _cap = int(os.environ.get("WEAVER_VERIFY_MAXCHARS",
                                              "16000") or 16000)
                except Exception:
                    _cap = 16000
                if len(draft) <= _cap:
                    body = draft
                else:
                    # Send the HEAD **and the TAIL**. Truncating from the front
                    # only made everything at the END of the document invisible
                    # to the judge — the references list, the conclusion — so it
                    # reported them MISSING on documents that clearly had them
                    # ("لا توجد قائمة مراجع في نهاية النص" while the file ended
                    # with a full APA list). Same class of false failure as the
                    # cover/TOC one: never accuse what you cannot see.
                    _head = int(_cap * 0.6)
                    _tail = _cap - _head
                    body = (draft[:_head]
                            + "\n\n[...جزءٌ من المتن حُذف للاختصار...]\n\n"
                            + draft[-_tail:])
                items = "\n".join(
                    f'- id={r.get("id")}: {r.get("text")}' for r in to_model)
                prompt = (
                    "أنت مدقّق متطلّبات. لكل متطلّبٍ في القائمة، احكم هل حقّقه "
                    "النصُّ المُنتَج فعلاً. أعِد JSON فقط: "
                    '{"results":[{"id":"..","status":"met|unmet|partial",'
                    '"reason":"سببٌ قصير من النص"}]}\n'
                    "لا تفترض؛ استند إلى ما هو موجودٌ في النص فعلاً. "
                    "partial حين يتحقّق المتطلّب جزئياً فقط.\n\n"
                    "المتطلّبات:\n" + items + "\n\nالنصُّ المُنتَج:\n" + body)
                try:
                    raw = llm_fn(prompt, system=system, temperature=0.0,
                                 max_tokens=800, timeout=60) or ""
                except TypeError:
                    raw = llm_fn(prompt, system=system, temperature=0.0) or ""
                data = extract_json(raw) or {}
                for it in (data.get("results") or []):
                    if isinstance(it, dict) and it.get("id"):
                        st = str(it.get("status", "")).lower().strip()
                        if st not in ("met", "unmet", "partial"):
                            st = "unknown"
                        verdicts[str(it["id"])] = (
                            st, str(it.get("reason", ""))[:200])
            except Exception:
                verdicts = {}
    for r in to_model:
        st, reason = verdicts.get(str(r.get("id")), ("unknown", "تعذّر الحكم"))
        results.append({"id": r.get("id"), "text": r.get("text"),
                        "kind": r.get("kind"), "must": bool(r.get("must")),
                        "status": st, "evidence": reason, "by": "model"})

    unmet = [x["id"] for x in results
             if x["must"] and x["status"] != "met"]
    all_met = not unmet
    n_met = sum(1 for x in results if x["status"] == "met")
    summary = (f"تحقّق {n_met}/{len(results)} من المتطلّبات؛ "
               f"{'كل الإلزامية مُحقّقة' if all_met else str(len(unmet)) + ' إلزامي غير مؤكّد'}")
    return {"results": results, "unmet": unmet, "all_met": all_met,
            "summary": summary}


def _content_to_chart(llm_fn, content, lang="ar"):
    """Ask the model to pull a small chartable series (labels + numeric values)
    from content. Returns a chart spec {"type","data":{"labels","values"},
    "title"} ready for _maybe_chart, or None when there's nothing numeric."""
    if not llm_fn:
        return None
    try:
        from core.llm import extract_json
        prompt = (
            "استخرج من المحتوى سلسلةً رقمية قابلة للرسم (تسميات وقيَم عددية). "
            "إن لم توجد أرقام حقيقية فأعِد {\"values\":[]} فقط دون اختلاق. أعِد "
            "JSON فقط: {\"type\":\"bar|pie|line\",\"title\":\"..\","
            "\"labels\":[\"..\"],\"values\":[رقم,..]}:\n\n"
            if lang == "ar" else
            "Extract a small chartable numeric series (labels + numeric values) "
            "from the content. If there are no real numbers, return "
            "{\"values\":[]} — never fabricate. Return JSON only: "
            "{\"type\":\"bar|pie|line\",\"title\":\"..\",\"labels\":[..],"
            "\"values\":[num,..]}:\n\n"
        ) + (content or "")[:9000]
        data = extract_json(llm_fn(prompt, temperature=0.1)) or {}
        labels = [str(x) for x in (data.get("labels") or [])]
        vals = []
        for v in (data.get("values") or []):
            try:
                vals.append(float(v))
            except (TypeError, ValueError):
                vals = []
                break
        if labels and vals and len(labels) == len(vals) and len(vals) >= 2:
            ctype = str(data.get("type", "bar")).lower()
            if ctype not in ("bar", "pie", "line"):
                ctype = "bar"
            return {"type": ctype, "title": str(data.get("title", "")),
                    "data": {"labels": labels, "values": vals}}
        return None
    except Exception:
        return None


def export_content_to_file(content, fmt="docx", lang="ar", title=None):
    """Export READY markdown content to a file (docx/pdf/pptx/xlsx) directly, with
    NO research pipeline — for "أخرج/حوّل الناتج السابق إلى وورد/pdf". The filename
    comes from the content's own title, never the command. Returns the output path
    or None. Safe/degrading."""
    import tempfile
    content = (content or "").strip()
    if not content:
        return None
    _PIPELINE_GATE.acquire(0)
    fd, db = tempfile.mkstemp(prefix="weaver_exp_", suffix=".db")
    os.close(fd)
    try:
        orch = WeaverOrchestrator(db_path=db)
        fmtU = str(fmt).upper()
        ttl = title or _derive_title(content)
        task = Task(description=ttl)
        task.draft = content
        task.task_card = {
            "topic": ttl, "language": lang,
            "output_format": [fmtU], "sourcing_mode": "none",
        }
        # smart restructuring so PowerPoint/Excel aren't just a text dump
        if fmtU == "PPTX":
            task.sections = (_content_to_slides(getattr(orch, "llm_fn", None),
                                                content, lang)
                             or _md_to_sections(content))
        elif fmtU in ("XLSX", "CSV"):
            tbl = _content_to_table(getattr(orch, "llm_fn", None), content, lang)
            if tbl:
                task.task_card["headers"] = tbl.get("headers")
                task.task_card["data"] = tbl.get("rows")
            task.sections = _md_to_sections(content)
        else:
            task.sections = _md_to_sections(content)
        try:
            return orch._export(task)
        except Exception:
            return None
    finally:
        try:
            os.remove(db)
        except OSError:
            pass
        _PIPELINE_GATE.release()


def quick_live_context_ex(msg, lang="ar", max_chars=6000):
    """Live context for the QUICK/chat path (used by web + terminal): read any
    URL pasted in the message (a page or a YouTube video) and — for news/recency
    questions — run a quick multi-engine web search. Returns a tuple
    (context_str, sources) where `sources` is an ORDERED list of {"title","url"}
    (newest first) gathered from the SAME search, so the caller can list clickable
    source links under a news answer without searching again. Fully synchronous
    and degrading (returns ("", []) on any failure)."""
    import asyncio
    import re
    parts = []
    sources = []
    try:
        urls = re.findall(r'https?://[^\s)>\]\"\'،]+', msg or "")
    except Exception:
        urls = []
    orch = object.__new__(WeaverOrchestrator)   # bare: only _extract_full used
    try:
        orch._yt_lang = lang
    except Exception:
        pass
    # 1) pasted URLs → read them (page / YouTube transcript)
    for u in (urls or [])[:2]:
        u = u.rstrip('.,)"،')
        try:
            txt = asyncio.run(orch._extract_full(u))
        except Exception:
            txt = None
        if txt and txt.strip():
            parts.append(f"[محتوى الرابط: {u}]\n{txt.strip()[:4000]}")
    # 2) news/recency OR an explicit site/date search (no URL pasted) → search
    _site, _df_dir = WeaverOrchestrator._search_directives(msg)
    _recency = WeaverOrchestrator._is_recency_query(msg)
    if not urls and (_recency or _site or _df_dir):
        try:
            q = (WeaverOrchestrator._augment_query_with_date(msg, lang)
                 if _recency else (msg or "").strip())
            if _site:
                q = q + " site:" + _site
            _df = _df_dir or ("w" if _recency else None)
            results = WeaverOrchestrator._multi_engine_search(
                q, lang, 12, df=_df) or []
            if _recency:
                results = WeaverOrchestrator._sort_results_by_recency(results)
            lines, n = [], 1
            for r in results[:12]:
                title = (r.get("title") or "").strip()
                if not title:
                    continue
                url = (r.get("url") or "").strip()
                snip = (r.get("content") or "").strip()[:220]
                # NUMBER each result so the model can cite [n] → the matching
                # source; sources are collected in the SAME order.
                lines.append(f"[{n}] {title} — {snip} ({url})")
                if url:
                    # Keep the snippet and mine the URL/title for a DOI and a
                    # year. This used to store {title, url} ONLY — throwing away
                    # the snippet it had just read and ignoring the DOI sitting
                    # inside the URL — which left every web source without the
                    # author/year that APA (or any style) needs.
                    sources.append(
                        WeaverOrchestrator._enrich_source({
                            "title": title, "url": url,
                            "content": snip, "source": "web"}))
                n += 1
            if lines:
                _hdr = ("[نتائج بحث حيّة مرقّمة، الأحدث أولاً]" if _recency
                        else ("[نتائج بحث حيّة مرقّمة من موقع " + _site + "]"
                              if _site else "[نتائج بحث حيّة مرقّمة]"))
                _rule = ("\nقاعدة: لا تذكر خبراً/معلومة إلا إن كانت مدعومة "
                         "بأحد المصادر المرقّمة أعلاه، واذكر رقم مصدرها [n] بعدها، "
                         "واكتفِ بمصدر واحد لكل خبر إلا إن ورد فعلاً في أكثر من "
                         "مصدر. لا تنسب خبراً لمصدر لا يحتويه.")
                parts.append(_hdr + "\n" + "\n".join(lines) + _rule)
        except Exception:
            pass
    ctx = "\n\n".join(parts).strip()
    return ctx[:max_chars], sources


def quick_live_context(msg, lang="ar", max_chars=6000):
    """Backward-compatible wrapper: returns only the context string."""
    try:
        return quick_live_context_ex(msg, lang, max_chars)[0]
    except Exception:
        return ""


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
