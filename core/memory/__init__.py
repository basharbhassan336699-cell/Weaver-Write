"""
core/memory/__init__.py
=======================
UniMemory مدمجة كذاكرة داخلية للنظام.

كل مهمة من الخمس لها ذاكرة معزولة تماماً.
UniMemory تحفظ:
  - حالة المهمة (في أي طبقة)
  - المراجع المكتشفة
  - المسودة الجارية
  - قرارات التحقق
  - الدروس المستخلصة
"""

from __future__ import annotations
import sys
import os

# إضافة مسار UniMemory للنظام
UNIMEMORY_PATH = os.path.join(os.path.dirname(__file__), "../../engines/unimemory-core")
if UNIMEMORY_PATH not in sys.path:
    sys.path.insert(0, UNIMEMORY_PATH)

from unimemory import UniMemory, Memory, Sector
from unimemory.memory_types import classify_sector


class TaskMemory:
    """
    ذاكرة مهمة واحدة — غلاف فوق UniMemory.
    
    كل مهمة تحصل على user_id معزول = task_id
    لا تسرب بيانات بين المهام الخمس.
    """

    def __init__(self, task_id: str, db_path: str = "./weaver_memory.db"):
        self.task_id = task_id
        self.mem = UniMemory(
            db_path=db_path,
            user_id=task_id,
            enable_truth_check=True,
            enable_graph=True,
        )

    # ── حالة المهمة ──

    def set_status(self, layer: int, status: str):
        """يحفظ حالة المهمة الحالية."""
        self.mem.add(
            f"حالة المهمة: الطبقة {layer} — {status}",
            node="observe",
            sector="procedural",
            tags=["status", f"layer_{layer}"],
        )

    def get_status(self) -> list:
        """يسترجع آخر حالة للمهمة."""
        return self.mem.search("حالة المهمة", limit=1, sector="procedural")

    # ── المراجع الأكاديمية ──

    def add_reference(self, ref: str, page: int = None, source_key: str = None):
        """يضيف مرجعاً مع رقم صفحته."""
        content = ref
        if page:
            content += f" | ص. {page}"
        if source_key:
            content += f" | مفتاح: {source_key}"
        self.mem.add(content, node="observe", sector="semantic", tags=["reference"])

    def get_references(self, query: str, limit: int = 10) -> list:
        """يبحث في المراجع المخزنة."""
        return self.mem.search(query, limit=limit, sector="semantic")

    # ── المسودة ──

    def save_draft(self, section: str, content: str):
        """يحفظ قسماً من المسودة."""
        self.mem.add(
            f"مسودة — {section}: {content[:500]}",
            node="plan",
            sector="semantic",
            tags=["draft", section],
        )

    # ── قرارات التحقق ──

    def mark_verified(self, citation_key: str, page: int, verified: bool):
        """يسجل نتيجة التحقق من استشهاد."""
        status = "مؤكد" if verified else "مرفوض"
        self.mem.add(
            f"تحقق {status}: {citation_key} ص. {page}",
            node="act",
            sector="procedural",
            tags=["verification", citation_key],
        )

    # ── الدروس المستخلصة ──

    def distill_task_lessons(self, messages: list):
        """يستخلص دروساً عند انتهاء المهمة."""
        return self.mem.distill_session(messages, store=True)

    # ── تصدير ──

    def export(self) -> str:
        """يصدّر ذاكرة المهمة كـ JSON."""
        return self.mem.export_json()

    def stats(self) -> dict:
        """إحصاءات ذاكرة المهمة."""
        return self.mem.stats()

    def close(self):
        self.mem.close()


class MemoryManager:
    """
    مدير الذاكرة لكل المهام الخمس.
    نقطة الدخول الوحيدة للذاكرة في النظام.
    """

    def __init__(self, db_path: str = "./weaver_memory.db"):
        self.db_path = db_path
        self._tasks: dict[str, TaskMemory] = {}

    def create_task(self, task_id: str) -> TaskMemory:
        """ينشئ ذاكرة معزولة لمهمة جديدة."""
        if task_id not in self._tasks:
            self._tasks[task_id] = TaskMemory(task_id, self.db_path)
        return self._tasks[task_id]

    def get_task(self, task_id: str) -> TaskMemory:
        """يسترجع ذاكرة مهمة موجودة."""
        if task_id not in self._tasks:
            self._tasks[task_id] = TaskMemory(task_id, self.db_path)
        return self._tasks[task_id]

    def close_task(self, task_id: str):
        """يُغلق ذاكرة مهمة منتهية."""
        if task_id in self._tasks:
            self._tasks[task_id].close()
            del self._tasks[task_id]

    def active_tasks(self) -> list[str]:
        """قائمة المهام النشطة حالياً."""
        return list(self._tasks.keys())

    def close_all(self):
        for task_id in list(self._tasks.keys()):
            self.close_task(task_id)
