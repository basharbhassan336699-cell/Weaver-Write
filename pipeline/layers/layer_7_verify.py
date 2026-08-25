"""
pipeline/layers/layer_7_verify.py
===================================
طبقة ٧: التحقق من التوثيق

تتحقق من كل استشهاد في المسودة:
  ١. هل المرجع موجود في قاعدة RAG؟
  ٢. هل رقم الصفحة حقيقي؟
  ٣. هل النص المقتبس قريب من محتوى تلك الصفحة؟
"""

from __future__ import annotations
import os, sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pipeline.orchestrator import Task, TaskMemory

VERIFICATION_THRESHOLD = 70


async def run(task: "Task", mem: "TaskMemory") -> None:
    from pipeline.orchestrator import TaskStatus
    task.status = TaskStatus.LAYER_7
    mem.set_status(7, "التحقق من التوثيق")

    card = task.task_card
    paperqa_result = card.get("paperqa_result")
    if not paperqa_result:
        mem.set_status(7, "لا توجد استشهادات أكاديمية — تخطّي التحقق")
        print(f"    [L7] ⏭️  [{task.task_id}] بلا RAG — لا تحقق مطلوب")
        return

    draft = card.get("draft_text", "") or paperqa_result.get("answer", "")
    if not draft:
        mem.set_status(7, "لا توجد مسودة للتحقق")
        return

    lang_str = "arabic" if card.get("language", "ar") == "ar" else "english"
    print(f"    [L7] 🔍 التحقق من الاستشهادات [{task.task_id}]...")

    try:
        _add_paperqa_path()
        from paperqa_tool import PaperQATool

        tool   = PaperQATool(lang=lang_str)
        result = await tool.verify(text=draft, question=card.get("topic", ""))

        report = result.verification_report
        score  = report.get("score", 0)

        task.task_card["verification_report"] = report
        task.task_card["verification_score"]  = score
        task.task_card["verification_passed"] = score >= VERIFICATION_THRESHOLD

        mem.set_status(7, f"تحقق اكتمل — {score}% ({report.get('summary','')})")
        print(f"    [L7] {'✅' if score >= VERIFICATION_THRESHOLD else '⚠️ '} التحقق: {score}% — {report.get('summary','')}")

        if score < VERIFICATION_THRESHOLD:
            failed_keys = [c.get("key","") for c in report.get("failed",[])[:3]]
            if failed_keys:
                mem.add_reference(
                    f"[تحذير توثيق] الاستشهادات التالية لم تُؤكد: {failed_keys}",
                    source="verification_layer",
                )

    except ImportError:
        msg = "paperqa-core غير مثبت — التحقق غير متاح"
        print(f"    [L7] ⚠️  {msg}")
        mem.set_status(7, msg)
        task.task_card["verification_report"] = {"score": 0, "summary": msg, "verified": [], "failed": [], "partial": []}

    except Exception as e:
        print(f"    [L7] ⚠️  خطأ في التحقق: {e}")
        mem.set_status(7, f"خطأ: {e}")


def format_verification_report(card: dict, lang: str = "ar") -> str:
    """يولّد نص تقرير التحقق لإضافته في الوثيقة النهائية (يُستدعى من L8)."""
    report = card.get("verification_report", {})
    if not report:
        return ""

    score    = report.get("score", 0)
    summary  = report.get("summary", "")
    verified = report.get("verified", [])
    partial  = report.get("partial", [])
    failed   = report.get("failed", [])

    sep = "─" * 40
    if lang == "ar":
        lines = [sep, "📋 تقرير التحقق من التوثيق", f"النتيجة: {score}% — {summary}"]
        if verified: lines.append(f"✅ مؤكد ({len(verified)}): " + "، ".join(c.get("key","") for c in verified[:5]))
        if partial:  lines.append(f"⚠️  جزئي ({len(partial)}): " + "، ".join(c.get("key","") for c in partial[:3]))
        if failed:   lines.append(f"❌ غير مؤكد ({len(failed)}): " + "، ".join(c.get("key","") for c in failed[:3]))
    else:
        lines = [sep, "📋 Verification Report", f"Score: {score}% — {summary}"]
        if verified: lines.append(f"✅ Verified ({len(verified)}): " + ", ".join(c.get("key","") for c in verified[:5]))
        if failed:   lines.append(f"❌ Unverified ({len(failed)}): " + ", ".join(c.get("key","") for c in failed[:3]))
    lines.append(sep)
    return "\n".join(lines)


def _add_paperqa_path():
    base = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    for p in [
        os.path.join(base, "engines", "paperqa-core"),
        os.path.join(base, "engines", "paperqa-core", "src"),
    ]:
        if p not in sys.path:
            sys.path.insert(0, p)
