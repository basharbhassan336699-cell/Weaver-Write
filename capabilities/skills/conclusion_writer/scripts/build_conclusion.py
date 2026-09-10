"""
build_conclusion.py — build a conclusion & recommendations (working script)
===========================================================================
Deterministic scaffold + optional LLM prose, same pattern as build_intro.
Provider-agnostic: pass llm_fn(prompt)->str or get the scaffold.
"""
from __future__ import annotations
import argparse
import re

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



def _strip_echoed_heading(text, heading):
    """Drop a leading echo of the sub-heading from the model's own reply.
    The caller already emits "## {heading}", and models routinely open their
    answer with that same heading — which printed it twice in the document
    ("ملخص النتائج ملخص النتائج"). Removes the echo whether it comes as a
    markdown heading, followed by a colon, or on its own line. Conservative:
    the heading must actually START the reply."""
    t = (text or "").strip()
    h = (heading or "").strip()
    if not t or not h:
        return t
    # a leading "## heading" / "# heading" line
    m = re.match(r'^\s*#{1,6}\s*(.+?)\s*$', t.split("\n", 1)[0])
    if m and m.group(1).strip().rstrip(":：").strip() == h:
        t = t.split("\n", 1)[1] if "\n" in t else ""
        return t.strip()
    if t.startswith(h):
        rest = t[len(h):]
        after = rest.lstrip()
        # only when it reads as a heading: newline, a colon, or nothing after it
        if rest[:1] == "\n" or after[:1] in (":", "：") or after == "":
            return rest.lstrip(" :：\n\t-،.").strip()
    return t

def build_conclusion(topic, main_findings=None, lang="ar", llm_fn=None,
                     style_hint=None, include=None):
    """Build a conclusion. main_findings: list[str]. llm_fn optional.
    style_hint (optional str): a closing-style directive applied to the FINAL
    sub-section only, so the conclusion ends with a non-standard touch instead
    of a formulaic close. None → behaviour unchanged (backward compatible)."""
    main_findings = main_findings or []
    sections = SECTIONS.get(lang, SECTIONS["en"])
    # `include` (optional) selects WHICH sub-sections to write. The four were
    # always imposed, so every document ended with recommendations and future
    # research even when the user never asked for them. None → unchanged.
    if include is not None:
        _keep = {str(k).strip() for k in include}
        _sel = [(h, g) for h, g in sections if h in _keep]
        if _sel:
            sections = _sel
    findings_block = "\n".join(f"- {f}" for f in main_findings) or (
        "لا نتائج مُدخلة" if lang == "ar" else "no findings provided")

    if llm_fn is None:
        lines = []
        for heading, guide in sections:
            lines.append(f"## {heading}\n[{guide}]\n")
        lines.append(("### النتائج الرئيسية:\n" if lang == "ar"
                      else "### Key findings:\n") + findings_block)
        return {"text": "\n".join(lines), "structured": True}

    # NB: the caller already prints "## {heading}", so the model must NOT open
    # its answer with that heading — doing so printed it twice in the document
    # ("ملخص النتائج ملخص النتائج").
    rules = ("اكتب بالعربية الأكاديمية. لا تُدخل معلومات جديدة. التوصيات قابلة "
             "للتطبيق. ابدأ بالمحتوى مباشرةً ولا تُعِد كتابة عنوان القسم."
             if lang == "ar" else
             "Write in academic English. Do not introduce new information. "
             "Recommendations must be actionable. Begin with the content "
             "directly; do not repeat the section heading.")
    parts = []
    for _i, (heading, guide) in enumerate(sections):
        prompt = (f"{rules}\n\nالموضوع: {topic}\nالقسم: {heading}\nالتوجيه: {guide}\n"
                  f"النتائج:\n{findings_block}" if lang == "ar" else
                  f"{rules}\n\nTopic: {topic}\nSection: {heading}\nGuidance: {guide}\n"
                  f"Findings:\n{findings_block}")
        # non-standard closing: apply the style hint to the FINAL sub-section
        # only, so the whole conclusion ends with a question/paradox/reflection.
        if style_hint and _i == len(sections) - 1:
            prompt = prompt + "\n\n" + str(style_hint)
        _txt = _strip_echoed_heading(llm_fn(prompt).strip(), heading)
        parts.append(f"## {heading}\n{_txt}")
    return {"text": "\n\n".join(parts), "structured": False}


def _main():
    p = argparse.ArgumentParser()
    p.add_argument("--topic", required=True)
    p.add_argument("--lang", default="ar", choices=["ar", "en"])
    args = p.parse_args()
    print(build_conclusion(args.topic, lang=args.lang)["text"])


if __name__ == "__main__":
    _main()
