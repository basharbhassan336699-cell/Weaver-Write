"""
build_intro.py — build a research introduction (working script)
===============================================================
Assembles a structured introduction. It builds the scaffold deterministically
(the five ordered sections with their references injected), then calls an LLM
to write natural prose for each section. The LLM call is provided by the
caller as `llm_fn(prompt) -> str`, so this script stays provider-agnostic.

Without an llm_fn, it returns the structured scaffold (headings + the
references to weave in), which is still directly usable.

Usage (as a module):
    from build_intro import build_intro
    intro = build_intro(topic, references, lang="ar", llm_fn=my_llm)
"""
from __future__ import annotations
import argparse
import json

SECTIONS = {
    "ar": [
        ("خلفية الموضوع", "قدّم تمهيداً عاماً يضع القارئ في سياق الموضوع"),
        ("أهمية البحث", "وضّح لماذا هذا الموضوع جدير بالدراسة"),
        ("مشكلة البحث", "اذكر الفجوة المعرفية أو السؤال المحوري"),
        ("أهداف البحث", "اذكر ما يسعى البحث لتحقيقه في نقاط محددة"),
        ("منهجية مختصرة", "أشر بإيجاز للمنهج المتبع"),
    ],
    "en": [
        ("Background", "Provide a general lead-in placing the reader in context"),
        ("Significance", "Explain why this topic is worth studying"),
        ("Research Problem", "State the knowledge gap or central question"),
        ("Objectives", "State what the research aims to achieve as specific points"),
        ("Brief Methodology", "Briefly point to the approach used"),
    ],
}


def build_intro(topic, references=None, length=400, lang="ar", llm_fn=None):
    """
    Build an introduction.

    references: list of {"key","text","page"} to weave in with citations.
    llm_fn: optional callable(prompt:str)->str. If None, returns scaffold.
    Returns: {"text": str, "structured": bool}
    """
    references = references or []
    sections = SECTIONS.get(lang, SECTIONS["en"])
    per_section = max(50, length // len(sections))

    ref_block = "\n".join(
        f"- ({r.get('key','?')}، ص. {r.get('page','?')}): {r.get('text','')[:120]}"
        if lang == "ar" else
        f"- ({r.get('key','?')}, p. {r.get('page','?')}): {r.get('text','')[:120]}"
        for r in references
    ) or ("لا مراجع متاحة" if lang == "ar" else "no references available")

    if llm_fn is None:
        # scaffold only
        lines = []
        for heading, guide in sections:
            lines.append(f"## {heading}\n[{guide}]\n")
        lines.append(("### المراجع المتاحة للدمج:\n" if lang == "ar"
                      else "### References to weave in:\n") + ref_block)
        return {"text": "\n".join(lines), "structured": True}

    # LLM mode: write each section
    rules = (
        "اكتب بالعربية الأكاديمية الفصيحة. كل معلومة تحتاج استشهاداً توثّق بصيغة "
        "(المؤلف، ص. X). لا تستخدم معلومات من خارج المراجع المعطاة."
        if lang == "ar" else
        "Write in formal academic English. Every factual claim needs a citation "
        "(Author, p. X). Do not use information outside the given references."
    )
    parts = []
    for heading, guide in sections:
        prompt = (
            f"{rules}\n\nالموضوع: {topic}\nالقسم: {heading}\nالتوجيه: {guide}\n"
            f"عدد الكلمات المستهدف: {per_section}\n\nالمراجع:\n{ref_block}"
            if lang == "ar" else
            f"{rules}\n\nTopic: {topic}\nSection: {heading}\nGuidance: {guide}\n"
            f"Target words: {per_section}\n\nReferences:\n{ref_block}"
        )
        parts.append(f"## {heading}\n{llm_fn(prompt).strip()}")
    return {"text": "\n\n".join(parts), "structured": False}


def _main():
    p = argparse.ArgumentParser(description="Build a research introduction (scaffold)")
    p.add_argument("--topic", required=True)
    p.add_argument("--lang", default="ar", choices=["ar", "en"])
    p.add_argument("--length", type=int, default=400)
    args = p.parse_args()
    r = build_intro(args.topic, lang=args.lang, length=args.length)
    print(r["text"])


if __name__ == "__main__":
    _main()
