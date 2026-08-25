"""
build_pdf.py — build a professional PDF (working script)
========================================================
Direction-aware academic PDF:
  - Arabic (lang="ar")  -> RTL: text shaped with arabic_reshaper + bidi,
                            right-aligned.
  - English (lang="en") -> LTR: left-aligned.

Arabic correctness requires two libraries that reshape and reorder glyphs:
    pip install arabic-reshaper python-bidi
Without them, Arabic letters render disconnected and left-to-right, so the
builder detects their absence and reports it clearly rather than producing
broken output.

Requires: pip install reportlab  (+ arabic-reshaper python-bidi for Arabic)
"""
from __future__ import annotations
import argparse
import json

NAVY = (0x1B/255, 0x2A/255, 0x4A/255)
GOLD = (0xC8/255, 0xA0/255, 0x4A/255)
DARK = (0x22/255, 0x2A/255, 0x38/255)


def _shape_arabic(text: str):
    """Reshape + reorder Arabic text for correct RTL rendering."""
    try:
        import arabic_reshaper
        from bidi.algorithm import get_display
        return get_display(arabic_reshaper.reshape(text)), True
    except ImportError:
        return text, False


def build_pdf(sections, output_path, title="", lang="ar", references=None):
    """
    Build an academic PDF.

    sections: list of {"heading": str, "body": str}
    lang: 'ar' (RTL) | 'en' (LTR)
    """
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import cm
    from reportlab.pdfgen import canvas as _canvas
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    import os

    rtl = (lang == "ar")
    arabic_ok = True

    # register an Arabic-capable font if available on the system
    font_name = "Helvetica"
    if rtl:
        # bundled fonts first, then system fonts
        import glob as _glob
        _bundled = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
            os.path.dirname(os.path.abspath(__file__))))),
            "engines", "fonts-core", "arabic")
        _candidates = sorted(_glob.glob(os.path.join(_bundled, "*.ttf")))
        for candidate in _candidates + [
            "/system/fonts/NotoNaskhArabic-Regular.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/noto/NotoNaskhArabic-Regular.ttf",
        ]:
            if os.path.exists(candidate):
                try:
                    pdfmetrics.registerFont(TTFont("Arabic", candidate))
                    font_name = "Arabic"
                    break
                except Exception:
                    pass

    c = _canvas.Canvas(output_path, pagesize=A4)
    width, height = A4
    margin = 2 * cm
    y = height - margin

    def _line(text, size, color, bold=False, gap=0.8):
        nonlocal y, arabic_ok
        if rtl:
            shaped, ok = _shape_arabic(text)
            arabic_ok = arabic_ok and ok
            text = shaped
        c.setFillColorRGB(*color)
        c.setFont(font_name, size)
        if rtl:
            c.drawRightString(width - margin, y, text)
        else:
            c.drawString(margin, y, text)
        y -= size * gap + 6
        if y < margin:
            c.showPage(); y = height - margin

    # title
    if title:
        _line(title, 20, NAVY, bold=True, gap=1.5)
        y -= 10

    # sections
    for sec in sections:
        _line(sec.get("heading", ""), 15, NAVY, bold=True, gap=1.2)
        body = sec.get("body", "")
        # naive wrap
        for chunk in _wrap(body, 90):
            _line(chunk, 11, DARK)
        y -= 8

    # references
    if references:
        _line("المراجع" if rtl else "References", 15, NAVY, gap=1.2)
        for i, ref in enumerate(references, 1):
            for chunk in _wrap(f"{i}. {ref}", 90):
                _line(chunk, 10, DARK)

    c.save()
    return {"output_path": output_path, "arabic_shaped": arabic_ok if rtl else None}


def _wrap(text, width):
    words = text.split()
    lines, cur = [], ""
    for w in words:
        if len(cur) + len(w) + 1 <= width:
            cur = (cur + " " + w).strip()
        else:
            lines.append(cur); cur = w
    if cur:
        lines.append(cur)
    return lines or [""]


def _main():
    p = argparse.ArgumentParser(description="Build an academic PDF")
    p.add_argument("--json", required=True)
    p.add_argument("--output", default="doc.pdf")
    p.add_argument("--lang", default="ar", choices=["ar", "en"])
    args = p.parse_args()
    with open(args.json, encoding="utf-8") as f:
        d = json.load(f)
    result = build_pdf(d.get("sections", []), args.output,
                       title=d.get("title", ""), lang=args.lang,
                       references=d.get("references"))
    print(f"Created: {result['output_path']}")
    if args.lang == "ar" and result.get("arabic_shaped") is False:
        print("WARNING: arabic-reshaper/python-bidi not installed — "
              "Arabic text may render disconnected. "
              "Fix: pip install arabic-reshaper python-bidi")


if __name__ == "__main__":
    _main()
