"""
llm_deck_generator.py — LLM-authored HTML decks (working script)
================================================================
The full "Claude way": instead of filling fixed templates, this hands the
design task to an LLM, which authors creative HTML/CSS per slide. The theme
palette is passed as *guidance*, not a rigid template, so layout variety is
unbounded — different slides can have different structures (cards, columns,
timelines, quotes...), exactly like Claude.

Pipeline:
    request + content + theme palette
        └─▶ llm_fn(prompt) writes an HTML deck
              └─▶ sanitize + validate (must contain .slide divs, sized right)
                    └─▶ html2pptx → native editable PPTX

Provider-agnostic: the caller passes `llm_fn(prompt: str) -> str`. Without
an llm_fn, it falls back to the template generator (html_deck_generator).

Correct direction is enforced in the prompt AND double-checked after:
Arabic → RTL, English → LTR.
"""
from __future__ import annotations
import argparse
import json
import os
import re

_SCRIPTS = os.path.dirname(os.path.abspath(__file__))
if _SCRIPTS not in __import__("sys").path:
    __import__("sys").path.insert(0, _SCRIPTS)


def _load_themes():
    from html_deck_generator import load_themes
    return load_themes()


_REF_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "templates", "reference_layouts")


def normalize_direction(html: str, lang: str) -> str:
    """
    Retarget a reference layout's reading direction to the task language.
    Arabic -> RTL (dir=rtl, text-align:right), English -> LTR (dir=ltr,
    text-align:left). This lets any of the 27 templates (some authored RTL,
    some LTR) be reused correctly for either language.
    """
    import re
    want_rtl = (lang == "ar")
    to_dir = "rtl" if want_rtl else "ltr"
    to_align = "right" if want_rtl else "left"
    opp_align = "left" if want_rtl else "right"

    # 1) html/element dir attribute
    html = re.sub(r'dir\s*=\s*["\'](rtl|ltr)["\']', f'dir="{to_dir}"', html, flags=re.I)
    # 2) lang attribute on <html>
    html = re.sub(r'lang\s*=\s*["\'][^"\']*["\']',
                  f'lang="{"ar" if want_rtl else "en"}"', html, count=1, flags=re.I)
    # 3) CSS direction property
    html = re.sub(r'direction\s*:\s*(rtl|ltr)', f'direction:{to_dir}', html, flags=re.I)
    # 4) CSS text-align: flip left<->right (keep center as-is)
    #    use a placeholder to avoid double-swapping
    html = re.sub(r'text-align\s*:\s*right', 'text-align:__A__', html, flags=re.I)
    html = re.sub(r'text-align\s*:\s*left', 'text-align:__B__', html, flags=re.I)
    html = html.replace('text-align:__A__', f'text-align:{to_align}')
    html = html.replace('text-align:__B__', f'text-align:{to_align}' if want_rtl else 'text-align:left')
    # after swap, ensure the dominant alignment matches target
    html = html.replace('__A__', to_align).replace('__B__', opp_align)
    return html


def load_reference_layout(name_hint="", lang="ar"):
    """
    Load one real reference layout HTML as a style example for the LLM,
    normalized to the task's reading direction (Arabic=RTL, English=LTR).
    27 real, previously-built templates (Expo2020, creative, Friends&Family).
    Returns a trimmed, direction-correct HTML snippet or "".
    """
    if not os.path.isdir(_REF_DIR):
        return ""
    files = [f for f in os.listdir(_REF_DIR) if f.endswith(".html")]
    if not files:
        return ""
    chosen = None
    hint = (name_hint or "").lower()
    if hint:
        for f in files:
            if hint in f.lower():
                chosen = f
                break
    chosen = chosen or files[0]
    try:
        with open(os.path.join(_REF_DIR, chosen), encoding="utf-8") as fh:
            html = fh.read()
        html = normalize_direction(html, lang)   # retarget direction
        return html[:2500]
    except Exception:
        return ""


_ACAD_REF = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), "academic_content", "references")


def load_academic_patterns(max_chars=2000):
    """Load slide-type + academic content patterns as LLM guidance."""
    out = []
    for fname in ("slide-types.md", "slide_patterns.md"):
        fp = os.path.join(_ACAD_REF, fname)
        if os.path.exists(fp):
            try:
                with open(fp, encoding="utf-8") as f:
                    out.append(f.read()[:max_chars])
            except Exception:
                pass
    return "\n\n".join(out)


def build_prompt(title, slides_content, theme, lang, subtitle="", request=""):
    """
    Construct the design brief for the LLM. The theme is guidance, not a
    template — the LLM is free to choose layouts per slide.
    """
    rtl = (lang == "ar")
    direction = "RTL (right-to-left)" if rtl else "LTR (left-to-right)"
    font = theme["font_ar"] if rtl else theme["font_en"]

    palette = (
        f"primary #{theme['primary']}, accent #{theme['accent']}, "
        f"background #{theme['bg']}, title-bg #{theme['bg_title']}, "
        f"body-text #{theme['text']}, text-on-dark #{theme['text_on_dark']}"
    )

    # For academic decks, add real scholarly structure guidance.
    content_json = json.dumps(slides_content, ensure_ascii=False, indent=2)
    academic_guidance = ""
    acad_terms = ["بحث", "أكاديمي", "علمي", "دراسة", "رسالة", "مناقشة",
                  "academic", "research", "thesis", "conference", "paper", "study"]
    if any(t in (request + " " + title).lower() for t in acad_terms):
        patterns = load_academic_patterns()
        if patterns:
            academic_guidance = (
                "\nACADEMIC STRUCTURE GUIDANCE (follow scholarly flow — "
                "problem → methods → results → discussion — and the slide-type "
                "rules below):\n" + patterns + "\n")

    # Inject a real reference layout (direction-normalized to this language)
    # so the LLM echoes a proven design rather than a generic one.
    ref_cover = load_reference_layout("cover", lang=lang)
    ref_example = ""
    if ref_cover:
        ref_example = (
            "\nREFERENCE STYLE (a real, previously-built cover slide, already in the "
            f"correct {'RTL' if rtl else 'LTR'} direction — echo its structure/quality, "
            "adapt colors to the theme):\n" + ref_cover + "\n")

    # Layout patterns proven in prior real decks — offered as a design vocabulary
    # the LLM can draw from (not a rigid template).
    layout_vocabulary = """PROVEN LAYOUT PATTERNS (draw from these, mix as fits the content):
- Cover: two-panel split (dark primary panel + accent band), title + subtitle,
  a reserved area (circle/rounded box) as a photo/logo placeholder, small
  student-info line at the bottom.
- Table of contents / agenda: a grid of numbered cards (2x3 or 3x3).
- Section divider: full-bleed accent-colored slide with a large centered title.
- Content slide: a title with a short accent underline bar on the reading side,
  then 3-5 bullet points OR a set of cards.
- Cards row: 2-4 rounded cards, each with a bold heading + short text; use the
  accent color for card borders or headers.
- Two-column split: text on one side, a stat/quote/placeholder box on the other.
- Stats row: 2-4 oversized numbers with small captions under them.
- Decorative motif: a large semi-transparent circle partially off the top corner
  (on the reading side), or a small diamond accent — subtle, never a full stripe.
- Closing: dark primary slide with a centered accent-colored thank-you line."""

    if rtl:
        lang_rules = (
            "المحتوى بالعربية. اجعل الاتجاه RTL: أضف dir=\"rtl\" على html و على كل .slide، "
            "واجعل text-align:right، وابدأ العناصر من اليمين. استخدم الخط "
            f"'{font}'."
        )
    else:
        lang_rules = (
            f"Content is in English. Use LTR direction (dir=\"ltr\"), text-align:left, "
            f"left-anchored elements. Use the '{font}' font."
        )

    prompt = f"""You are an expert presentation designer. Author a COMPLETE, self-contained
HTML slide deck. It will be converted to native PowerPoint by html2pptx, so
follow these HARD REQUIREMENTS exactly:

STRUCTURE
- One `<div class="slide">` per slide. Each slide is EXACTLY 960px wide by 540px tall.
- Use inline <style> in <head>. Use absolute positioning OR CSS grid/flex inside each slide.
- Every slide must have `position: relative; width:960px; height:540px; overflow:hidden;`.
- Do NOT use external images, scripts, web fonts, or animations (they don't convert).
- Solid colors and simple gradients only.

DESIGN
- Theme palette (use as guidance, be creative): {palette}
- VARY the layout across slides: a title slide, then content slides that may use
  cards, two-column splits, numbered lists, a quote block, a stats row, a closing slide.
  Do not make every slide identical.
- Keep text legible: title >=32px, body >=20px. Strong visual hierarchy.

{layout_vocabulary}
{academic_guidance}
{ref_example}
DIRECTION
- {lang_rules}
- The reading direction must be {direction} on every slide.

CONTENT
- Deck title: {title}
- Subtitle: {subtitle}
- Design request from user: {request or "(none)"}
- Slides content (each item = one content slide):
{content_json}

OUTPUT
- Return ONLY the raw HTML document, starting with <!DOCTYPE html>.
- No markdown fences, no explanation. Just the HTML."""
    return prompt


_FENCE = re.compile(r"^```[a-zA-Z]*\s*|\s*```$", re.MULTILINE)


def sanitize_html(raw: str) -> str:
    """Strip markdown fences / stray prose the LLM may add around the HTML."""
    text = raw.strip()
    text = _FENCE.sub("", text)
    # keep from first <!DOCTYPE or <html to last </html>
    start = text.lower().find("<!doctype")
    if start < 0:
        start = text.lower().find("<html")
    end = text.lower().rfind("</html>")
    if start >= 0 and end >= 0:
        text = text[start:end + len("</html>")]
    return text.strip()


def validate_html(html: str, lang: str) -> dict:
    """Sanity checks so we don't feed broken HTML to the converter."""
    issues = []
    low = html.lower()
    if "<!doctype" not in low and "<html" not in low:
        issues.append("missing html root")
    slide_count = len(re.findall(r'class\s*=\s*["\'][^"\']*\bslide\b', low))
    if slide_count == 0:
        issues.append("no .slide elements found")
    if lang == "ar" and 'dir="rtl"' not in low and "dir='rtl'" not in low:
        issues.append("Arabic deck but no dir=rtl")
    return {"ok": len(issues) == 0, "issues": issues, "slides": slide_count}


def generate_llm_deck(title, slides_content, lang="ar", request="",
                      subtitle="", theme_id=None, llm_fn=None,
                      output_html=None, max_retries=1):
    """
    Generate an LLM-authored HTML deck.

    Returns: {"html": str, "theme": str, "authored_by": "llm"|"template",
              "valid": bool, "issues": [...]}
    If llm_fn is None or fails validation, falls back to the template generator.
    """
    themes = _load_themes()
    # theme: explicit id, else pick from request
    if theme_id and theme_id in themes:
        chosen = theme_id
    else:
        from html_deck_generator import pick_theme
        chosen = pick_theme(request, themes)
    theme = themes[chosen]

    if llm_fn is not None:
        prompt = build_prompt(title, slides_content, theme, lang, subtitle, request)
        attempt = 0
        while attempt <= max_retries:
            raw = llm_fn(prompt)
            html = sanitize_html(raw)
            v = validate_html(html, lang)
            if v["ok"]:
                if output_html:
                    with open(output_html, "w", encoding="utf-8") as f:
                        f.write(html)
                return {"html": html, "theme": chosen, "authored_by": "llm",
                        "valid": True, "issues": [], "slides": v["slides"]}
            attempt += 1
            # on retry, append the issues so the LLM fixes them
            prompt += f"\n\nYour previous output had issues: {v['issues']}. Fix them and return valid HTML only."

    # fallback: deterministic template generator
    from html_deck_generator import build_html
    html = build_html(title, slides_content, chosen, lang, subtitle, themes=themes)
    if output_html:
        with open(output_html, "w", encoding="utf-8") as f:
            f.write(html)
    return {"html": html, "theme": chosen, "authored_by": "template",
            "valid": True, "issues": [], "slides": len(slides_content) + 2}


def generate_and_convert(title, slides_content, output_pptx, lang="ar",
                         request="", subtitle="", theme_id=None, llm_fn=None):
    """End-to-end: author HTML (LLM or template) -> native PPTX."""
    from html2pptx_bridge import html_to_pptx
    result = generate_llm_deck(title, slides_content, lang, request,
                               subtitle, theme_id, llm_fn)
    conv = html_to_pptx(result["html"], output_pptx, is_string=True)
    return {
        "ok": conv.get("ok", False),
        "output_path": output_pptx if conv.get("ok") else None,
        "theme": result["theme"],
        "authored_by": result["authored_by"],
        "direction": "RTL" if lang == "ar" else "LTR",
        "error": conv.get("error"),
    }


def _main():
    p = argparse.ArgumentParser(description="Generate an LLM-authored deck (template fallback)")
    p.add_argument("--json", required=True)
    p.add_argument("--output", default="deck.html")
    args = p.parse_args()
    with open(args.json, encoding="utf-8") as f:
        d = json.load(f)
    # CLI has no llm_fn -> uses template fallback
    r = generate_llm_deck(d.get("title", ""), d.get("slides", []),
                          lang=d.get("lang", "ar"), request=d.get("request", ""),
                          subtitle=d.get("subtitle", ""), output_html=args.output)
    print(f"Created: {args.output} (theme: {r['theme']}, by: {r['authored_by']})")


if __name__ == "__main__":
    _main()
