"""
build_conclusion.py — build a conclusion & recommendations (working script)
===========================================================================
Deterministic scaffold + optional LLM prose, same pattern as build_intro.
Provider-agnostic: pass llm_fn(prompt)->str or get the scaffold.
"""
from __future__ import annotations
import argparse

SECTIONS = {
    "ar": [
        ("ملخص النتائج", "لخّص أهم النتائج بإيجاز"),
        ("الإجابة على سؤال البحث", "أجب صراحةً على السؤال المحوري"),
        ("التوصيات", "قدّم توصيات عملية مبنية على النتائج"),
        ("مقترحات للبحوث المستقبلية", "اقترح اتجاهات لبحوث لاحقة"),
    ],
    "en": [
        ("Summary of Findings", "Briefly summarize the key findings"),
        ("Answer to the Research Question", "Explicitly answer the central question"),
        ("Recommendations", "Give practical recommendations grounded in the findings"),
        ("Future Research", "Suggest directions for later research"),
    ],
}


def build_conclusion(topic, main_findings=None, lang="ar", llm_fn=None):
    """Build a conclusion. main_findings: list[str]. llm_fn optional."""
    main_findings = main_findings or []
    sections = SECTIONS.get(lang, SECTIONS["en"])
    findings_block = "\n".join(f"- {f}" for f in main_findings) or (
        "لا نتائج مُدخلة" if lang == "ar" else "no findings provided")

    if llm_fn is None:
        lines = []
        for heading, guide in sections:
            lines.append(f"## {heading}\n[{guide}]\n")
        lines.append(("### النتائج الرئيسية:\n" if lang == "ar"
                      else "### Key findings:\n") + findings_block)
        return {"text": "\n".join(lines), "structured": True}

    rules = ("اكتب بالعربية الأكاديمية. لا تُدخل معلومات جديدة. التوصيات قابلة للتطبيق."
             if lang == "ar" else
             "Write in academic English. Do not introduce new information. "
             "Recommendations must be actionable.")
    parts = []
    for heading, guide in sections:
        prompt = (f"{rules}\n\nالموضوع: {topic}\nالقسم: {heading}\nالتوجيه: {guide}\n"
                  f"النتائج:\n{findings_block}" if lang == "ar" else
                  f"{rules}\n\nTopic: {topic}\nSection: {heading}\nGuidance: {guide}\n"
                  f"Findings:\n{findings_block}")
        parts.append(f"## {heading}\n{llm_fn(prompt).strip()}")
    return {"text": "\n\n".join(parts), "structured": False}


def _main():
    p = argparse.ArgumentParser()
    p.add_argument("--topic", required=True)
    p.add_argument("--lang", default="ar", choices=["ar", "en"])
    args = p.parse_args()
    print(build_conclusion(args.topic, lang=args.lang)["text"])


if __name__ == "__main__":
    _main()
