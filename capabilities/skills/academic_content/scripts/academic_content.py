"""
academic_content.py — callable entry point for the academic-content skill
=========================================================================
This skill was previously reference-only (SKILL.md + references/, no script),
so it could only be consumed by code that read its files directly (the creative
llm_deck_generator already does). This script gives it a single callable entry
point so any slide-generation path can load its scholarly-structure guidance.

It governs WHAT goes on each slide and in WHAT order (problem → methods →
results → discussion) plus the 5 canonical slide types — presentation CONTENT
only, never file design or statistical validity.

Usage:
    from academic_content import build_guidance, academic_skeleton
    block = build_guidance(request, lang, max_chars=1600)  # str (may be "")
"""
from __future__ import annotations
import os

_REF = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    "references")

# reference files, most-useful first
_FILES = ("slide-types.md", "slide_patterns.md", "content_guidelines.md")

_ACAD_TERMS = ("بحث", "أكاديمي", "علمي", "دراسة", "رسالة", "ماجستير", "دكتوراه",
               "مناقشة", "أطروحة", "academic", "research", "thesis",
               "conference", "paper", "study", "dissertation")


def is_academic(text: str) -> bool:
    t = (text or "").lower()
    return any(term in t for term in _ACAD_TERMS)


def _load_patterns(max_chars: int = 1600) -> str:
    out, budget = [], max_chars
    for fname in _FILES:
        if budget <= 0:
            break
        fp = os.path.join(_REF, fname)
        if os.path.exists(fp):
            try:
                with open(fp, encoding="utf-8") as f:
                    chunk = f.read()[:budget]
                out.append(chunk)
                budget -= len(chunk)
            except Exception:
                pass
    return "\n\n".join(out)


def academic_skeleton(lang: str = "ar"):
    """The canonical scholarly section order for an academic deck."""
    if lang == "en":
        return ["Introduction", "Problem & Questions", "Framework",
                "Methodology", "Results", "Discussion", "Conclusion"]
    return ["المقدمة", "المشكلة والأسئلة", "الإطار النظري", "المنهجية",
            "النتائج", "المناقشة", "الخاتمة"]


def build_guidance(request: str = "", lang: str = "ar",
                   max_chars: int = 1600) -> str:
    """Return a concise academic-structure guidance block to inject into a
    slide-generation prompt, or "" when the request isn't academic or no
    references are available. Pure logic, never raises for normal input."""
    if request and not is_academic(request):
        return ""
    patterns = _load_patterns(max_chars)
    if not patterns:
        return ""
    if lang == "en":
        head = ("ACADEMIC STRUCTURE GUIDANCE (follow the scholarly flow — "
                "problem → methods → results → discussion — and "
                "the slide-type rules below; each slide is exactly one type: "
                "Cover, Table of Contents, Section Divider, Content, Closing):\n")
    else:
        head = ("إرشاد البنية الأكاديمية (اتّبع التدفّق العلمي: مشكلة ← "
                "منهجية ← نتائج ← مناقشة، وقواعد أنواع الشرائح أدناه؛ "
                "كل شريحة نوعٌ واحد: غلاف، محتويات، فاصل قسم، محتوى، ختامية):\n")
    return head + patterns


if __name__ == "__main__":
    print("academic skeleton (ar):", academic_skeleton("ar"))
    g = build_guidance("اعمل عرض بحثي عن الذكاء الاصطناعي", "ar")
    print("guidance chars:", len(g))
    print("non-academic -> empty:",
          repr(build_guidance("اعمل عرض عن رحلتي", "ar")[:0]))
