"""
html_deck_generator.py — generate a themed HTML deck (working script)
=====================================================================
Emits a designed HTML slide deck that html2pptx converts to native,
editable PPTX — the same "design in HTML/CSS, convert to PPTX" approach
Claude uses.

Key capabilities:
  - Multiple themes (see themes/themes.json): navy, green, gray, blue,
    purple, maroon — each a full color palette + fonts.
  - Theme selection from a free-text design request (Arabic or English):
    "عرض رسمي" -> formal_gray, "إبداعي" -> creative_purple, etc.
  - Correct direction: Arabic -> RTL (dir="rtl", right-anchored), English
    -> LTR (dir="ltr", left-anchored).

Pipeline:
    request text ─▶ pick_theme() ─▶ build_html() ─▶ html2pptx ─▶ .pptx
"""
from __future__ import annotations
import argparse
import json
import os
import html as _html

_THEMES_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            "themes", "themes.json")


def load_themes():
    with open(_THEMES_PATH, encoding="utf-8") as f:
        return json.load(f)["themes"]


def pick_theme(request: str, themes=None, default="academic_navy") -> str:
    """
    Choose a theme id from a free-text design request by matching mood words.
    Bilingual. Returns the best-matching theme id (or default).
    """
    themes = themes or load_themes()
    req = (request or "").lower()
    best, best_score = default, 0
    for tid, t in themes.items():
        score = sum(1 for m in t.get("mood", []) if m.lower() in req)
        # explicit theme name match is a strong signal
        if t["label_en"].lower() in req or t["label_ar"] in request:
            score += 5
        if tid.replace("_", " ") in req:
            score += 3
        if score > best_score:
            best, best_score = tid, score
    return best


def resolve_theme(request="", theme_id=None, custom_color=None, themes=None):
    """
    Resolve to a concrete theme dict. Priority:
      1) custom_color (any hex) -> build a harmonious theme around it
      2) explicit theme_id
      3) pick from the free-text request
    Returns (theme_dict, theme_label).
    """
    themes = themes or load_themes()
    # 1) custom color wins
    if custom_color:
        try:
            import os, sys
            here = os.path.dirname(os.path.abspath(__file__))
            if here not in sys.path:
                sys.path.insert(0, here)
            from palette_generator import custom_theme
            t = custom_theme(str(custom_color).lstrip("#"))
            return t, "custom"
        except Exception:
            pass
    # 2) explicit id
    if theme_id and theme_id in themes:
        return themes[theme_id], theme_id
    # 3) from request
    tid = pick_theme(request, themes)
    return themes[tid], tid


def _esc(s):
    return _html.escape(str(s), quote=True)


def build_html(title, slides, theme_id="academic_navy", lang="ar",
               subtitle="", closing=None, themes=None, font=None):
    """
    Build a full HTML deck string. One <div class="slide"> per slide,
    sized 960x540 (16:9). Direction from `lang`.
    `font`: optional font family to use (e.g. "Kufyan Arabic Black", "Arial",
    "Simplified Arabic"); overrides the theme font. A fallback chain of
    bundled open fonts is appended so it still looks right if the requested
    (often commercial) font isn't installed.
    """
    themes = themes or load_themes()
    t = themes.get(theme_id, themes["academic_navy"])
    rtl = (lang == "ar")
    d = "rtl" if rtl else "ltr"
    anchor = "right" if rtl else "left"
    base_font = font or (t["font_ar"] if rtl else t["font_en"])
    # fallback chain: requested -> bundled open fonts -> generic
    if rtl:
        font = f"'{base_font}', 'Cairo', 'Tajawal', 'Amiri', sans-serif"
    else:
        font = f"'{base_font}', 'Georgia', 'DejaVu Serif', serif"

    def _side(px):
        return f"{anchor}: {px}px;"

    css = f"""
    * {{ margin:0; padding:0; box-sizing:border-box; font-family:{font}; }}
    .slide {{ width:960px; height:540px; position:relative; overflow:hidden;
              direction:{d}; text-align:{anchor}; }}
    .bg-title {{ background:#{t['bg_title']}; }}
    .bg-content {{ background:#{t['bg']}; }}
    .bg-section {{ background:#{t['accent']}; }}
    .title-main {{ position:absolute; top:200px; {_side(80)} color:#{t['accent']};
                   font-size:44px; font-weight:bold; width:800px; }}
    .subtitle {{ position:absolute; top:290px; {_side(80)} color:#{t['text_on_dark']};
                 font-size:24px; width:800px; }}
    .accent-bar {{ position:absolute; top:270px; {_side(80)} width:180px; height:8px;
                   background:#{t['accent']}; }}
    .slide-title {{ position:absolute; top:50px; {_side(70)} color:#{t['primary']};
                    font-size:32px; font-weight:bold; width:820px; }}
    .title-bar {{ position:absolute; top:110px; {_side(70)} width:130px; height:6px;
                  background:#{t['accent']}; }}
    .content {{ position:absolute; top:160px; {_side(70)} width:820px;
                color:#{t['text']}; font-size:22px; line-height:1.9; }}
    .bullet {{ margin-bottom:14px; }}
    .section-title {{ position:absolute; top:230px; {_side(80)} color:#{t['primary']};
                      font-size:38px; font-weight:bold; width:800px; }}
    .closing {{ position:absolute; top:230px; left:0; right:0; text-align:center;
                color:#{t['accent']}; font-size:40px; font-weight:bold; }}
    """

    parts = [f"<!DOCTYPE html><html dir='{d}'><head><meta charset='utf-8'><style>{css}</style></head><body>"]

    # title slide
    parts.append(f"<div class='slide bg-title'>")
    parts.append(f"<div class='title-main'>{_esc(title)}</div>")
    parts.append(f"<div class='accent-bar'></div>")
    if subtitle:
        parts.append(f"<div class='subtitle'>{_esc(subtitle)}</div>")
    parts.append("</div>")

    # body slides
    for s in slides:
        if s.get("layout") == "section":
            parts.append("<div class='slide bg-section'>")
            parts.append(f"<div class='section-title'>{_esc(s.get('title',''))}</div>")
            parts.append("</div>")
        else:
            parts.append("<div class='slide bg-content'>")
            parts.append(f"<div class='slide-title'>{_esc(s.get('title',''))}</div>")
            parts.append("<div class='title-bar'></div>")
            marker = "◀" if rtl else "▶"
            body = "<div class='content'>"
            for pt in s.get("points", []):
                body += f"<div class='bullet'>{marker} {_esc(pt)}</div>"
            body += "</div>"
            parts.append(body)
            parts.append("</div>")

    # closing slide
    if closing is None:
        closing = "شكراً لكم" if rtl else "Thank you"
    parts.append(f"<div class='slide bg-title'><div class='closing'>{_esc(closing)}</div></div>")

    parts.append("</body></html>")
    return "\n".join(parts)


def generate_deck_html(title, slides, request="", lang="ar", subtitle="",
                       closing=None, output_html=None, custom_color=None,
                       theme_id=None, font=None):
    """
    High-level: resolve a theme (custom color > explicit id > request), build
    the HTML, optionally write it. Returns (html_string, theme_label).
    """
    themes = load_themes()
    theme, label = resolve_theme(request=request, theme_id=theme_id,
                                 custom_color=custom_color, themes=themes)
    # inject the resolved theme under its label so build_html can find it
    themes = dict(themes)
    themes[label] = theme
    html_str = build_html(title, slides, label, lang, subtitle, closing, themes, font=font)
    if output_html:
        with open(output_html, "w", encoding="utf-8") as f:
            f.write(html_str)
    return html_str, label


def _main():
    p = argparse.ArgumentParser(description="Generate a themed HTML deck")
    p.add_argument("--json", required=True, help="JSON: title/subtitle/slides/request/lang")
    p.add_argument("--output", default="deck.html")
    args = p.parse_args()
    with open(args.json, encoding="utf-8") as f:
        d = json.load(f)
    html_str, theme = generate_deck_html(
        d.get("title", ""), d.get("slides", []),
        request=d.get("request", ""), lang=d.get("lang", "ar"),
        subtitle=d.get("subtitle", ""), closing=d.get("closing"),
        output_html=args.output)
    print(f"Created: {args.output} (theme: {theme})")


if __name__ == "__main__":
    _main()
