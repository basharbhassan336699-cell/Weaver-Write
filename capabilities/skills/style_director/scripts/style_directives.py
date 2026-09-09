"""
style_directives.py — the style director (working script)
=========================================================
Pure-logic skill: produces a SHORT style directive block that Layer 6 appends
to the section-writing prompt. It does NOT call the model and never raises for
normal input — it just returns text.

Why it exists: the writing prompt only said "academic, human-toned, varied
rhythm". This skill adds the missing, model-DECIDED guidance:
  * narrative vs. bullet-point mixing BY THE NATURE OF THE INFORMATION
    (the governing principle of the dormant narrative_bullet_mixing skill),
  * a human academic voice (varied rhythm, a measured stance),
  * employed rhetorical questions where they serve the analysis,
  * a non-standard closing for conclusion-like sections.

Crucially it DESCRIBES WHEN to use each device — it never forces it — so the
model stays the author, choosing per the content. Returns "" for sections that
must stay plain (references), so nothing is imposed there.

Usage:
    from style_directives import build_style_block
    block = build_style_block(card, section_name, lang)   # str (may be "")
"""
from __future__ import annotations


def _norm(s):
    return (s or "").strip().lower()


def _is_references(section_name):
    n = _norm(section_name)
    return any(k in n for k in ("مراجع", "مصادر", "references", "bibliography",
                                "works cited"))


def _is_conclusion(section_name):
    n = _norm(section_name)
    return any(k in n for k in ("خاتمة", "خلاصة", "استنتاج", "conclusion",
                                "summary"))


def conclusion_directive(lang: str = "ar") -> str:
    """The non-standard-closing directive alone — reused by build_style_block and
    passed to the specialized conclusion writer so a conclusion doesn't end with a
    formulaic close."""
    if lang == "en":
        return ("Close with a non-standard touch — an open question, a paradox, "
                "or a brief reflection — instead of a formulaic "
                "\"In conclusion\".")
    return ("اختم بلمسةٍ غير نمطية — سؤالٌ مفتوح، أو مفارقة، أو تأمّلٌ موجز — "
            "بدل عبارة «في الختام» أو «وفي الخاتمة» المكرّرة.")


def build_style_block(card=None, section_name: str = "", lang: str = "ar") -> str:
    """Return a concise style directive to append to the writing prompt, or ""
    when the section should stay plain (a references list). The directive is
    guidance the model APPLIES BY ITS OWN JUDGEMENT — it is never a mandate."""
    # references / bibliography sections: never style them
    if _is_references(section_name):
        return ""

    if lang == "en":
        lines = [
            "Style guidance (apply by YOUR judgement of the content — never "
            "forced):",
            "- Form follows the nature of the information: use bullet points "
            "ONLY when the items are countable, homogeneous, independent, and "
            "carry no causal link; write flowing narrative for a single, "
            "connected idea. Do not add bullets merely to break monotony, and "
            "do not turn connected analysis into a list.",
            "- A human academic voice: vary sentence length and rhythm, take a "
            "measured scholarly stance where warranted, with no filler, no "
            "excess emotion, and no mechanical repetition.",
            "- Employ a question where it serves the analysis: you may open an "
            "idea with a research question that guides the reader, then answer "
            "it.",
        ]
        if _is_conclusion(section_name):
            lines.append("- " + conclusion_directive("en"))
        return "\n".join(lines)

    # Arabic (default)
    lines = [
        "توجيه أسلوبي (طبّقه بحسب تقديرك لطبيعة المحتوى، لا تفرضه على الكل):",
        "- شكل العرض يتبع طبيعة المعلومة: استعمل النقاط فقط حين تكون العناصر "
        "معدودةً متجانسةً مستقلّةً بلا ربطٍ سببيّ؛ واكتب سرداً متّصلاً للفكرة "
        "الواحدة المترابطة. لا تُقحم نقاطاً لمجرّد كسر الرتابة، ولا تحوّل "
        "تحليلاً مترابطاً إلى قائمة.",
        "- نبرة بشرية أكاديمية: نوّع طول الجمل وإيقاعها، وأبدِ رأياً علمياً "
        "محسوباً عند اللزوم، دون حشوٍ ولا عاطفةٍ زائدة ولا تكرارٍ آليّ.",
        "- وظّف التساؤل حين يخدم التحليل: قد تفتح الفكرة بسؤالٍ بحثيّ يوجّه "
        "القارئ ثم تجيب عنه.",
    ]
    if _is_conclusion(section_name):
        lines.append("- " + conclusion_directive("ar"))
    return "\n".join(lines)


if __name__ == "__main__":
    print("=== body (ar) ===")
    print(build_style_block({}, "المبحث الأول: النشأة", "ar"))
    print("\n=== conclusion (ar) ===")
    print(build_style_block({}, "الخاتمة", "ar"))
    print("\n=== references (ar) -> empty ===")
    print(repr(build_style_block({}, "قائمة المراجع", "ar")))
