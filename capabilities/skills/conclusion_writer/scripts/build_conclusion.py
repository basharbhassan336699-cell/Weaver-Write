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

def _drop_repeats(text, earlier, threshold=0.78):
    """Remove paragraphs that repeat something an EARLIER sub-section already
    said. Similarity is measured on the paragraph's opening (where a restatement
    shows first) with difflib — no keyword list, no model call, so it behaves the
    same with any model. Conservative: short paragraphs are left alone (a one
    line transition is not a repeat). When EVERY substantial paragraph repeats,
    "" is returned and the caller omits the sub-section entirely: an omitted part
    is honest, a verbatim duplicate is not — and the duplicate is what the reader
    actually complained about. Never raises."""
    try:
        import difflib
        prev = [p for blk in (earlier or []) for p in blk.split("\n\n")
                if len(p.split()) >= 12]
        if not prev:
            return text
        keep, dropped = [], 0
        for para in (text or "").split("\n\n"):
            p = para.strip()
            if len(p.split()) < 12:
                keep.append(para)
                continue
            head = p[:160]
            if any(difflib.SequenceMatcher(None, head, q[:160]).ratio()
                   >= threshold for q in prev):
                dropped += 1
                continue
            keep.append(para)
        if dropped and not [k for k in keep if len(k.split()) >= 12]:
            return ""                  # the whole sub-section was a restatement
        return "\n\n".join(k for k in keep if k.strip()).strip()
    except Exception:
        return text


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
    written = []          # what the EARLIER sub-sections already said
    for _i, (heading, guide) in enumerate(sections):
        prompt = (f"{rules}\n\nالموضوع: {topic}\nالقسم: {heading}\nالتوجيه: {guide}\n"
                  f"النتائج:\n{findings_block}" if lang == "ar" else
                  f"{rules}\n\nTopic: {topic}\nSection: {heading}\nGuidance: {guide}\n"
                  f"Findings:\n{findings_block}")
        # Each sub-section used to be written from an IDENTICAL prompt body —
        # same topic, same findings — differing only in two short lines, and
        # BLIND to what the previous sub-sections had written. The model then
        # re-stated the same findings under every heading (measured: 7 paragraphs
        # repeated verbatim between "ملخص النتائج" and "الإجابة على سؤال البحث").
        # Showing it what is already written, and naming what THIS sub-section
        # must add instead, is what makes the parts differ.
        if written:
            _prev = "\n\n".join(written)[-2500:]
            prompt += (
                "\n\nما كُتب فعلاً في الأقسام السابقة من الخاتمة (لا تُعِده "
                "ولا تُعِد صياغته، ولا تبدأ بالجُمل نفسها):\n" + _prev +
                "\n\nاكتب هذا القسم بزاويةٍ مختلفة تُضيف ما لم يُذكر بعد."
                if lang == "ar" else
                "\n\nAlready written in earlier parts of the conclusion (do not "
                "repeat or rephrase it, and do not open with the same "
                "sentences):\n" + _prev +
                "\n\nWrite this part from a different angle that adds what has "
                "not been said yet.")
        # non-standard closing: apply the style hint to the FINAL sub-section
        # only, so the whole conclusion ends with a question/paradox/reflection.
        if style_hint and _i == len(sections) - 1:
            prompt = prompt + "\n\n" + str(style_hint)
        _txt = _strip_echoed_heading(llm_fn(prompt).strip(), heading)
        # Belt and braces: a model that repeats anyway is trimmed here, by
        # measurement rather than instruction.
        _txt = _drop_repeats(_txt, written)
        if _txt:
            written.append(_txt)
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
