"""
pipeline/layers/layer_4_research.py
=====================================
طبقة ٤: البحث الأكاديمي (RAG)

تستدعي PaperQATool عندما تحتاج المهمة لمراجع أكاديمية.
المعيار: يُحدد في task_card["needs_academic_search"].
"""

from __future__ import annotations
import os, sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pipeline.orchestrator import Task, TaskMemory

ACADEMIC_TASK_TYPES = {
    "بحث", "مراجعة أدبيات", "literature review",
    "دراسة", "تقرير أكاديمي", "واجب أكاديمي",
}

ACADEMIC_KEYWORDS = [
    "مرجع", "استشهاد", "دراسات سابقة", "references",
    "citation", "ص.", "p.", "أكاديمي", "academic",
    "بحوث", "مجلات علمية", "Semantic Scholar",
]


def needs_academic_search(task_card: dict) -> bool:
    if task_card.get("needs_academic_search"):
        return True
    task_type = task_card.get("task_type", "").lower()
    if any(t in task_type for t in ACADEMIC_TASK_TYPES):
        return True
    topic = task_card.get("topic", "").lower()
    if any(kw.lower() in topic for kw in ACADEMIC_KEYWORDS):
        return True
    if task_card.get("citation_style", "").upper() in {"APA", "MLA", "CHICAGO"}:
        return True
    return False


async def run(task: "Task", mem: "TaskMemory") -> None:
    from pipeline.orchestrator import TaskStatus
    task.status = TaskStatus.LAYER_4
    mem.set_status(4, "البحث الأكاديمي")

    card = task.task_card
    lang_str = "arabic" if card.get("language", "ar") == "ar" else "english"

    if not needs_academic_search(card):
        mem.set_status(4, "لا يلزم بحث أكاديمي — تخطّي PaperQA")
        print(f"    [L4] ⏭️  [{task.task_id}] لا يحتاج RAG أكاديمي")
        return

    print(f"    [L4] 🔍 [{task.task_id}] يحتاج بحثاً أكاديمياً...")

    input_sources = [f for f in task.input_files if f.lower().endswith(".pdf")]
    card_sources  = card.get("academic_sources", [])
    sources = input_sources + card_sources

    try:
        _add_paperqa_path()
        from paperqa_tool import academic_search

        question = _build_research_question(card)
        print(f"    [L4] 📚 {len(sources)} مصدر — {question[:60]}")

        result = await academic_search(
            question=question,
            sources=sources,
            lang=lang_str,
            mode="cloud",
        )

        if result.error:
            mem.set_status(4, f"خطأ PaperQA: {result.error}")
            print(f"    [L4] ⚠️  {result.error}")
            task.task_card["paperqa_error"] = result.error
            return

        _save_to_memory(mem, result)

        task.task_card["paperqa_result"] = {
            "answer":        result.answer,
            "references":    result.references,
            "citations":     result.citations,
            "pages_found":   result.pages_found,
            "sources_count": result.sources_indexed,
        }

        print(f"    [L4] ✅ PaperQA: {result.sources_indexed} مصدر، {len(result.citations)} استشهاد")
        mem.set_status(4, f"اكتمل — {len(result.citations)} استشهاد برقم الصفحة")

    except ImportError:
        msg = "paperqa-core غير مثبت (pip install paper-qa pymupdf4llm)"
        print(f"    [L4] ⚠️  {msg}")
        mem.set_status(4, msg)
        task.task_card["paperqa_error"] = msg


def _add_paperqa_path():
    base = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    for p in [
        os.path.join(base, "engines", "paperqa-core"),
        os.path.join(base, "engines", "paperqa-core", "src"),
    ]:
        if p not in sys.path:
            sys.path.insert(0, p)


def _build_research_question(card: dict) -> str:
    topic     = card.get("topic", "")
    task_type = card.get("task_type", "بحث")
    if task_type in ("مراجعة أدبيات", "literature review"):
        return f"ما الدراسات والأبحاث الرئيسية حول: {topic}؟"
    elif task_type == "منهجية":
        return f"ما المناهج البحثية المستخدمة في: {topic}؟"
    return f"ما النتائج والمعلومات الأكاديمية الرئيسية حول: {topic}؟"


def _save_to_memory(mem, result):
    if result.answer:
        mem.add_reference(f"[PaperQA] {result.answer[:500]}", source="paperqa_academic_search")
    for cit in result.citations:
        mem.add_reference(
            f"[{cit['key']}، ص. {cit['page']}] {cit['context'][:200]}",
            source=cit["key"], page=cit["page"],
        )
    if result.references:
        mem.add_reference(f"[قائمة المراجع]\n{result.references}", source="paperqa_references")
