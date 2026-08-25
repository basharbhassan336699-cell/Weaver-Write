"""
design_slides.py — propose a slide structure (working script)
=============================================================
Turns a topic + sections into a slide plan ready for build_pptx.py:
each slide gets a title, key points, and a suggested visual type.

Deterministic planning (no LLM needed) with sensible defaults; an optional
llm_fn can refine the point wording.

Usage (as a module):
    from design_slides import design_slides
    plan = design_slides(topic, sections, slide_count=8, lang="ar")
    # plan feeds directly into build_pptx.build_deck(slides=plan["slides"])
"""
from __future__ import annotations
import argparse
import json


def design_slides(topic, sections=None, slide_count=8, lang="ar", llm_fn=None):
    """
    sections: list of {"title": str, "points": [str,...]} or None.
    Returns: {"slides": [...], "title": str} ready for build_pptx.
    """
    rtl = (lang == "ar")
    slides = []

    # opening section marker
    intro_label = "المقدمة" if rtl else "Introduction"
    concl_label = "الخاتمة" if rtl else "Conclusion"

    if sections:
        for sec in sections:
            pts = sec.get("points", [])
            # cap points per slide at 5; split if longer
            for i in range(0, max(1, len(pts)), 5):
                chunk = pts[i:i+5]
                slides.append({
                    "title": sec.get("title", ""),
                    "points": chunk,
                    "visual": _suggest_visual(chunk, lang),
                })
    else:
        # generate a default academic skeleton
        skeleton = ([intro_label, "الإطار النظري", "المنهجية", "النتائج", concl_label]
                    if rtl else
                    [intro_label, "Framework", "Methodology", "Results", concl_label])
        for s in skeleton:
            slides.append({"title": s, "points": [], "visual": "text"})

    # respect slide_count (trim or note)
    if slide_count and len(slides) > slide_count:
        slides = slides[:slide_count]

    return {"title": topic, "slides": slides, "count": len(slides)}


def _suggest_visual(points, lang):
    """Heuristic: suggest a visual type from the point content."""
    joined = " ".join(points).lower()
    num_markers = ["%", "نسبة", "rate", "عدد", "count", "بيانات", "data"]
    if any(m in joined for m in num_markers):
        return "chart"
    if len(points) >= 4:
        return "table"
    return "text"


def _main():
    p = argparse.ArgumentParser()
    p.add_argument("--topic", required=True)
    p.add_argument("--lang", default="ar")
    p.add_argument("--count", type=int, default=8)
    args = p.parse_args()
    plan = design_slides(args.topic, slide_count=args.count, lang=args.lang)
    print(json.dumps(plan, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    _main()
