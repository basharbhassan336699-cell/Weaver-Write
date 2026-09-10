"""
build_pdf.py — academic PDF builder (working script)
====================================================
Unlike the .docx path, a PDF is actually RENDERED here, so the three things
Word can only promise via fields are REAL in a PDF:
  * page numbers      — we know the page as we draw it
  * a table of contents with true page numbers — resolved by a measuring pass
  * an exact page count — returned to the caller, no words-per-page estimate

How the TOC gets real numbers: pass 1 lays the content out on a throw-away
canvas and records (heading, level, page); pass 2 draws the cover and the TOC
(whose own length is known from the heading count) and then the content, adding
the front-matter offset to every recorded page.

Arabic: text is reshaped AFTER line breaking (reshaping first would corrupt the
wrap), which is why wrapping measures the SHAPED string.

Requires: pip install reportlab  (+ arabic-reshaper python-bidi for Arabic)
"""
from __future__ import annotations
import argparse
import json
import os
import re

NAVY = (0x1B / 255, 0x2A / 255, 0x4A / 255)
GOLD = (0xC8 / 255, 0xA0 / 255, 0x4A / 255)
DARK = (0x22 / 255, 0x2A / 255, 0x38 / 255)
GREY = (0x66 / 255, 0x6C / 255, 0x78 / 255)


def _shape_arabic(text: str):
    """Reshape + reorder Arabic text for correct RTL rendering."""
    try:
        import arabic_reshaper
        from bidi.algorithm import get_display
        return get_display(arabic_reshaper.reshape(text)), True
    except ImportError:
        return text, False


_AR_RE = re.compile(r'[\u0600-\u06FF\u0750-\u077F\uFB50-\uFDFF\uFE70-\uFEFF]')


def _shape_line(text: str):
    """Shape ONE line for RTL drawing, protecting Latin runs (URLs above all).

    Running the whole line through the bidi algorithm splits a URL at its ':'
    and '/' — which are neutral characters — and reorders the pieces, so
    "https://doi.org/10.63496/ejhs" was drawn as "0.63496/ejhs …//:sptth".
    Here the line is cut into Arabic and non-Arabic runs; only the Arabic runs
    are reshaped/reordered, the Latin runs are left exactly as written, and the
    RUN ORDER is reversed because the base direction is right-to-left.
    """
    if not text:
        return text, True
    ok = True
    runs, cur, cur_ar = [], "", None
    for ch in text:
        is_ar = bool(_AR_RE.match(ch))
        if ch.isspace():
            cur += ch
            continue
        if cur_ar is None or is_ar == cur_ar:
            cur_ar = is_ar
            cur += ch
        else:
            runs.append((cur_ar, cur))
            cur, cur_ar = ch, is_ar
    if cur:
        runs.append((bool(cur_ar), cur))
    out = []
    for is_ar, run in runs:
        if is_ar:
            shaped, k = _shape_arabic(run)
            ok = ok and k
            out.append(shaped)
        else:
            out.append(run)          # URLs/numbers stay exactly as written
    return "".join(reversed(out)), ok


def _find_font(lang):
    """Register an Arabic-capable TTF and return (regular, bold) font names."""
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    import glob
    if lang != "ar":
        return "Helvetica", "Helvetica-Bold"
    root = os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.dirname(os.path.abspath(__file__)))))
    base = os.path.join(root, "engines", "fonts-core", "arabic")
    reg = bold = None
    for want, tag in (("Amiri-Regular", "reg"), ("Amiri-Bold", "bold")):
        fp = os.path.join(base, want + ".ttf")
        if os.path.exists(fp):
            try:
                pdfmetrics.registerFont(TTFont("Ar-" + tag, fp))
                if tag == "reg":
                    reg = "Ar-reg"
                else:
                    bold = "Ar-bold"
            except Exception:
                pass
    if not reg:
        for cand in sorted(glob.glob(os.path.join(base, "*.ttf"))) + [
                "/system/fonts/NotoNaskhArabic-Regular.ttf",
                "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"]:
            if os.path.exists(cand):
                try:
                    pdfmetrics.registerFont(TTFont("Ar-reg", cand))
                    reg = "Ar-reg"
                    break
                except Exception:
                    pass
    reg = reg or "Helvetica"
    return reg, (bold or reg)


def _wrap_to_width(text, font, size, max_w, rtl):
    """Break text into lines that FIT, measuring the shaped string (the old
    builder counted characters, which over/under-fills every Arabic line)."""
    from reportlab.pdfbase import pdfmetrics

    def _w(s):
        t = _shape_line(s)[0] if rtl else s
        try:
            return pdfmetrics.stringWidth(t, font, size)
        except Exception:
            return len(t) * size * 0.5

    out, cur = [], ""
    for word in (text or "").split():
        cand = (cur + " " + word).strip()
        if cur and _w(cand) > max_w:
            out.append(cur)
            cur = word
        else:
            cur = cand
    if cur:
        out.append(cur)
    return out or [""]


def _md_table(lines, i):
    """Parse a GFM table starting at lines[i]; → (headers, rows, next_i) or None."""
    def cells(l):
        return [c.strip() for c in l.strip().strip("|").split("|")]
    if i + 1 >= len(lines) or "|" not in lines[i]:
        return None
    sep = lines[i + 1].replace(" ", "")
    if not re.match(r'^\|?:?-{2,}', sep) or "|" not in lines[i + 1]:
        return None
    headers = cells(lines[i])
    rows, j = [], i + 2
    while j < len(lines) and "|" in lines[j] and lines[j].strip():
        rows.append(cells(lines[j]))
        j += 1
    return headers, rows, j


def _render(c, sections, references, font, bold, lang, width, height, margin,
            page_offset, draw, page_numbers=True):
    """Lay the CONTENT out. Called twice: once with draw=False purely to record
    where each heading lands, then again for real. Returns (headings, pages)
    where headings is [{"text","level","page"}] with page_offset already added."""
    rtl = (lang == "ar")
    state = {"y": height - margin, "page": 1}
    heads = []

    def _footer():
        if not page_numbers:
            return
        n = state["page"] + page_offset
        lbl = f"صفحة {n}" if rtl else f"Page {n}"
        if draw:
            c.setFont(font, 9)
            c.setFillColorRGB(*GREY)
            c.drawCentredString(width / 2.0, margin * 0.55,
                                _shape_arabic(lbl)[0] if rtl else lbl)

    def _newpage():
        _footer()
        if draw:
            c.showPage()
        state["page"] += 1
        state["y"] = height - margin

    def _need(h):
        if state["y"] - h < margin:
            _newpage()

    def _text(s, size, color, fnt=None, gap=1.35):
        _need(size * gap)
        if draw:
            c.setFillColorRGB(*color)
            c.setFont(fnt or font, size)
            t = _shape_line(s)[0] if rtl else s
            if rtl:
                c.drawRightString(width - margin, state["y"], t)
            else:
                c.drawString(margin, state["y"], t)
        state["y"] -= size * gap

    def _para(body, size=11):
        for raw in (body or "").split("\n"):
            raw = raw.rstrip()
            if not raw.strip():
                state["y"] -= size * 0.5
                continue
            for ln in _wrap_to_width(raw, font, size,
                                     width - 2 * margin, rtl):
                _text(ln, size, DARK)
            state["y"] -= 2

    def _table(headers, rows, size=9.5):
        ncol = max(1, len(headers))
        colw = (width - 2 * margin) / ncol
        allrows = [headers] + rows
        for ri, row in enumerate(allrows):
            _need(size * 2.2)
            yy = state["y"]
            if draw:
                if ri == 0:
                    c.setFillColorRGB(*NAVY)
                    c.rect(margin, yy - size * 0.45, width - 2 * margin,
                           size * 1.6, stroke=0, fill=1)
                c.setFont(bold if ri == 0 else font, size)
                c.setFillColorRGB(1, 1, 1) if ri == 0 else \
                    c.setFillColorRGB(*DARK)
                for ci in range(ncol):
                    cell = row[ci] if ci < len(row) else ""
                    cell = _shape_line(cell)[0] if rtl else cell
                    x = (width - margin - ci * colw) if rtl else (margin + ci * colw)
                    if rtl:
                        c.drawRightString(x - 4, yy, cell[:38])
                    else:
                        c.drawString(x + 4, yy, cell[:38])
                c.setStrokeColorRGB(*GREY)
                c.setLineWidth(0.3)
                c.line(margin, yy - size * 0.5, width - margin, yy - size * 0.5)
            state["y"] -= size * 1.9
        state["y"] -= 4

    for sec in (sections or []):
        head = (sec.get("heading") or "").strip()
        try:
            lvl = int(sec.get("level", 1) or 1)
        except Exception:
            lvl = 1
        if head:
            _need(40)
            heads.append({"text": head, "level": max(1, min(lvl, 3)),
                          "page": state["page"] + page_offset})
            _text(head, 15 if lvl <= 1 else 12.5, NAVY, bold, gap=1.7)
        body = sec.get("body") or ""
        lines = body.split("\n")
        i = 0
        while i < len(lines):
            tb = _md_table(lines, i)
            if tb:
                _table(tb[0], tb[1])
                i = tb[2]
                continue
            _para(lines[i])
            i += 1
        state["y"] -= 6

    if references:
        _need(40)
        h = "المراجع" if rtl else "References"
        heads.append({"text": h, "level": 1, "page": state["page"] + page_offset})
        _text(h, 15, NAVY, bold, gap=1.7)
        refs = references if isinstance(references, (list, tuple)) \
            else str(references).split("\n")
        for i, r in enumerate(refs, 1):
            r = str(r).strip()
            if r:
                for ln in _wrap_to_width(f"{i}. {r}", font, 10,
                                         width - 2 * margin, rtl):
                    _text(ln, 10, DARK)
    _footer()
    return heads, state["page"]


def build_pdf(sections, output_path, title="", lang="ar", references=None,
              toc=False, cover=None, page_numbers=True, subtitle=""):
    """Build an academic PDF.

    sections: [{"heading": str, "body": str, "level": int}]
    toc:      insert a table of contents with REAL page numbers
    cover:    truthy → a title page; a dict may carry author/institution/date
    Returns {"output_path", "pages", "toc_entries", "arabic_shaped"} — `pages`
    is the TRUE page count, so a "10-12 pages" requirement can be checked
    exactly instead of estimated from a words-per-page guess.
    """
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import cm
    from reportlab.pdfgen import canvas as _canvas

    rtl = (lang == "ar")
    font, bold = _find_font(lang)
    width, height = A4
    margin = 2 * cm

    def _sh(s):
        return _shape_line(s)[0] if rtl else s

    # ── pass 1: measure where every heading lands (throw-away canvas) ──
    import io as _io
    probe = _canvas.Canvas(_io.BytesIO(), pagesize=A4)
    heads, _ = _render(probe, sections, references, font, bold, lang,
                       width, height, margin, 0, draw=False,
                       page_numbers=page_numbers)

    # front matter length is known once the heading count is known
    cover_pages = 1 if cover else 0
    per_toc_page = int((height - 2 * margin) / 22)
    toc_pages = max(1, -(-len(heads) // max(1, per_toc_page))) if (toc and heads) else 0
    offset = cover_pages + toc_pages

    c = _canvas.Canvas(output_path, pagesize=A4)

    # ── cover ──
    if cover:
        info = cover if isinstance(cover, dict) else {}
        y = height * 0.62
        c.setFillColorRGB(*NAVY)
        c.setFont(bold, 24)
        for ln in _wrap_to_width(title or "", bold, 24, width - 2 * margin, rtl):
            c.drawCentredString(width / 2.0, y, _sh(ln))
            y -= 34
        c.setStrokeColorRGB(*GOLD)
        c.setLineWidth(2)
        c.line(width / 2.0 - 90, y - 6, width / 2.0 + 90, y - 6)
        y -= 46
        c.setFont(font, 13)
        c.setFillColorRGB(*DARK)
        for key in ("subtitle", "institution", "author", "supervisor",
                    "course", "date"):
            v = str(info.get(key) or ("" if key != "subtitle" else subtitle)).strip()
            if v:
                c.drawCentredString(width / 2.0, y, _sh(v))
                y -= 22
        c.showPage()

    # ── table of contents with the measured page numbers ──
    if toc_pages:
        y = height - margin
        c.setFillColorRGB(*NAVY)
        c.setFont(bold, 17)
        t = "المحتويات" if rtl else "Contents"
        if rtl:
            c.drawRightString(width - margin, y, _sh(t))
        else:
            c.drawString(margin, y, t)
        y -= 34
        c.setFont(font, 11.5)
        for h in heads:
            if y < margin + 20:
                c.showPage()
                y = height - margin
                c.setFont(font, 11.5)
            indent = (h["level"] - 1) * 18
            num = str(h["page"] + offset)
            c.setFillColorRGB(*DARK)
            label = _sh(h["text"])
            if rtl:
                c.drawRightString(width - margin - indent, y, label)
                c.drawString(margin, y, num)
            else:
                c.drawString(margin + indent, y, label)
                c.drawRightString(width - margin, y, num)
            c.setStrokeColorRGB(*GREY)
            c.setLineWidth(0.25)
            c.setDash(1, 3)
            c.line(margin + 24, y + 3, width - margin - 24, y + 3)
            c.setDash()
            y -= 22
        c.showPage()

    # ── pass 2: the real content, numbered from after the front matter ──
    _, pages = _render(c, sections, references, font, bold, lang,
                       width, height, margin, offset, draw=True,
                       page_numbers=page_numbers)
    c.save()
    return {"output_path": output_path, "pages": pages + offset,
            "toc_entries": len(heads),
            "arabic_shaped": _shape_arabic("ا")[1] if rtl else None}


def _wrap(text, width):
    """Kept for backward compatibility (character-count wrap)."""
    words = text.split()
    lines, cur = [], ""
    for w in words:
        if len(cur) + len(w) + 1 <= width:
            cur = (cur + " " + w).strip()
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines or [""]


def _main():
    p = argparse.ArgumentParser(description="Build an academic PDF")
    p.add_argument("--sections", required=True, help="JSON list of sections")
    p.add_argument("--out", required=True)
    p.add_argument("--title", default="")
    p.add_argument("--lang", default="ar")
    p.add_argument("--toc", action="store_true")
    p.add_argument("--cover", action="store_true")
    a = p.parse_args()
    print(json.dumps(build_pdf(json.loads(a.sections), a.out, a.title, a.lang,
                               toc=a.toc, cover=a.cover), ensure_ascii=False))


if __name__ == "__main__":
    _main()
