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

    # بطاقة المهمة (تُملأ في طبقة الفهم)
    task_card: dict = field(default_factory=dict)

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
    ):
        self.memory = MemoryManager(db_path=db_path)
        self.sandbox = SandboxManager(domain=sandbox_domain, api_key=sandbox_key)

        self._queue: list[Task] = []
        self._active: dict[str, Task] = {}      # task_id → Task
        self._completed: list[Task] = []
        self._lock = asyncio.Lock()

    # ── إضافة مهمة ──

    async def submit(self, description: str, input_files: list[str] = None) -> Task:
        """
        يُضيف مهمة جديدة.
        إن كانت الخانات الخمس ممتلئة → طابور انتظار.
        """
        task = Task(
            description=description,
            input_files=input_files or [],
        )

        async with self._lock:
            if len(self._active) < MAX_TASKS:
                await self._start_task(task)
            else:
                self._queue.append(task)
                print(f"📋 مهمة [{task.task_id}] في الطابور ({len(self._queue)} بالانتظار)")

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

    async def _layer_3(self, task: Task, mem: TaskMemory):
        """٣: الفهم — تحليل المهمة وبناء بطاقتها."""
        task.status = TaskStatus.LAYER_3
        mem.set_status(3, "تحليل المهمة")
        from core.thinking import ThinkingEngine
        from pipeline.prompts import SYSTEM_PROMPT_MAIN
        thinking = ThinkingEngine()
        cot = thinking.cot_prompt(task.description)
        # النموذج سيُجيب هنا — task.task_card تُملأ بالنتيجة
        task.task_card = {
            "task_type": "بحث",
            "topic": task.description,
            "language": "ar",
            "citation_style": "APA",
            "output_format": "DOCX",
        }

    async def _layer_4(self, task: Task, mem: TaskMemory):
        """٤: البحث الأكاديمي — PaperQA2 + استشهاد دقيق برقم الصفحة."""
        from pipeline.layers.layer_4_research import run as _layer4_run
        await _layer4_run(task, mem)

    async def _layer_5(self, task: Task, mem: TaskMemory):
        """٥: المصداقية — تصنيف المصادر."""
        task.status = TaskStatus.LAYER_5
        mem.set_status(5, "تقييم مصداقية المصادر")

    async def _layer_6(self, task: Task, mem: TaskMemory):
        """٦: الصياغة — توليد البحث مع استشهادات."""
        task.status = TaskStatus.LAYER_6
        mem.set_status(6, "صياغة البحث")

    async def _layer_6_5(self, task: Task, mem: TaskMemory):
        """٦.٥: إعادة الصياغة والتنظيف — أنسنة النص وإزالة البصمة الآلية.

        تُطبّق صامتةً: تحمي الاستشهادات، تستبدل كلمات AI بمرادفات بشرية،
        وتزيل البصمات البصرية (الشرطات الطويلة، الرموز الزخرفية، الخلط اللغوي)
        حسب نوع الملف — مع إبقاء الرموز في عروض PowerPoint.
        """
        task.status = TaskStatus.LAYER_6_5
        mem.set_status(65, "إعادة الصياغة والتنظيف")

        lang = task.task_card.get("language", "ar")
        fmt = task.task_card.get("output_format", "DOCX").lower()
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
            draft = mem.get_draft() if hasattr(mem, "get_draft") else task.task_card.get("draft", "")
            if draft:
                result = mod.humanize_text(draft, file_type=file_type)
                if hasattr(mem, "set_draft"):
                    mem.set_draft(result["text"])
                task.task_card["humanized"] = True
                task.task_card["cleaning_issues"] = result.get("issues", [])
        except Exception as e:
            mem.set_status(65, f"إعادة الصياغة (تخطّي: {e})")

    async def _layer_7(self, task: Task, mem: TaskMemory):
        """٧: التحقق من التوثيق — PaperQA truth-check."""
        from pipeline.layers.layer_7_verify import run as _layer7_run
        await _layer7_run(task, mem)


    async def _layer_8(self, task: Task, mem: TaskMemory):
        """٨: الإخراج — توليد الملف النهائي."""
        task.status = TaskStatus.LAYER_8
        mem.set_status(8, "توليد الملف النهائي")
        # إضافة تقرير التحقق للوثيقة النهائية
        try:
            from pipeline.layers.layer_7_verify import format_verification_report
            verify_text = format_verification_report(
                task.task_card, lang=task.task_card.get("language", "ar")
            )
            if verify_text:
                mem.add_reference(f"[تقرير التحقق]\n{verify_text}", source="layer_8")
        except Exception:
            pass

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
