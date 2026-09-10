"""
docx_advanced.py — professional Word features (working script)
==============================================================
Rich, theme-aware Word building that matches the quality Claude produces:
formatted tables, inline images, two-column layouts, headers/footers with
page numbers, a table-of-contents field, and colored headings — all with
correct direction (Arabic RTL / English LTR) at the XML level.

These are composable helpers that operate on a python-docx Document, plus a
high-level build_rich_docx() that assembles a full themed document.

Direction:
  - Arabic (lang="ar") -> paragraphs get <w:bidi/>, right alignment, and
    tables get <w:bidiVisual/> so columns read right-to-left.
  - English (lang="en") -> normal LTR.

Themes: reuses the presentation palettes (themes.json) so a Word report and
a deck on the same topic share colors.

Requires: python-docx  (+ a bundled font via fonts-core)
"""
from __future__ import annotations
import os
import json

from docx.oxml.ns import qn
from docx.oxml import OxmlElement


# ── theme palette (shared with slides) ───────────────────────
_THEMES = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "pptx_builder", "themes", "themes.json")


def load_palette(theme_id="academic_navy"):
    try:
        with open(_THEMES, encoding="utf-8") as f:
            t = json.load(f)["themes"].get(theme_id, {})
        return {
            "primary": t.get("primary", "1B2A4A"),
            "accent": t.get("accent", "C8A04A"),
            "text": t.get("text", "222A38"),
        }
    except Exception:
        return {"primary": "1B2A4A", "accent": "C8A04A", "text": "222A38"}


# ── direction helpers ────────────────────────────────────────
def set_paragraph_rtl(paragraph):
    pPr = paragraph._p.get_or_add_pPr()
    if pPr.find(qn("w:bidi")) is None:
        pPr.append(OxmlElement("w:bidi"))


def set_table_rtl(table):
    """Make a table read right-to-left (columns flow RTL)."""
    tblPr = table._tbl.tblPr
    if tblPr.find(qn("w:bidiVisual")) is None:
        tblPr.append(OxmlElement("w:bidiVisual"))


def _shade_cell(cell, hex_color):
    tcPr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:fill"), hex_color)
    tcPr.append(shd)


def _set_run_font(run, font_name, size=None, color=None, bold=None):
    from docx.shared import Pt, RGBColor
    if font_name:
        run.font.name = font_name
        rpr = run._element.get_or_add_rPr()
        rfonts = rpr.find(qn("w:rFonts"))
        if rfonts is None:
            rfonts = OxmlElement("w:rFonts"); rpr.append(rfonts)
        for a in ("w:ascii", "w:hAnsi", "w:cs"):
            rfonts.set(qn(a), font_name)
    if size:
        run.font.size = Pt(size)
    if color:
        run.font.color.rgb = RGBColor.from_string(color)
    if bold is not None:
        run.font.bold = bold


# ── formatted table ──────────────────────────────────────────
def add_table(doc, headers, rows, lang="ar", theme_id="academic_navy",
              font=None, totals_row=None):
    """
    Add a styled table: colored header row, borders, RTL-aware.
    headers: list[str]; rows: list[list]; totals_row: optional list.
    """
    from docx.shared import Pt
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    pal = load_palette(theme_id)
    rtl = (lang == "ar")
    font = font or ("Kufyan Arabic" if rtl else "Times New Roman")

    n_cols = len(headers)
    table = doc.add_table(rows=1, cols=n_cols)
    table.style = "Table Grid"
    if rtl:
        set_table_rtl(table)

    # header
    hdr = table.rows[0].cells
    for i, h in enumerate(headers):
        _shade_cell(hdr[i], pal["primary"])
        p = hdr[i].paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = p.add_run(str(h))
        _set_run_font(run, font, 12, "FFFFFF", bold=True)
        if rtl:
            set_paragraph_rtl(p)

    # body
    for row in rows:
        cells = table.add_row().cells
        for i, val in enumerate(row):
            p = cells[i].paragraphs[0]
            p.alignment = WD_ALIGN_PARAGRAPH.RIGHT if rtl else WD_ALIGN_PARAGRAPH.LEFT
            run = p.add_run(str(val))
            _set_run_font(run, font, 11, pal["text"])
            if rtl:
                set_paragraph_rtl(p)

    # totals
    if totals_row:
        cells = table.add_row().cells
        for i, val in enumerate(totals_row):
            _shade_cell(cells[i], pal["accent"])
            p = cells[i].paragraphs[0]
            p.alignment = WD_ALIGN_PARAGRAPH.RIGHT if rtl else WD_ALIGN_PARAGRAPH.LEFT
            run = p.add_run(str(val))
            _set_run_font(run, font, 11, "1A1A1A", bold=True)
            if rtl:
                set_paragraph_rtl(p)
    return table


# ── inline image ─────────────────────────────────────────────
def add_image(doc, image_path, caption="", width_inches=5.5, lang="ar",
              font=None):
    from docx.shared import Inches, Pt
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    rtl = (lang == "ar")
    if not os.path.exists(image_path):
        return False
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.add_run().add_picture(image_path, width=Inches(width_inches))
    if caption:
        cap = doc.add_paragraph()
        cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = cap.add_run(caption)
        _set_run_font(run, font or ("Kufyan Arabic" if rtl else "Times New Roman"),
                      10, "666666")
        run.font.italic = True
        if rtl:
            set_paragraph_rtl(cap)
    return True


# ── two-column section ───────────────────────────────────────
def set_columns(section, num=2, space_twips=425):
    """Set a section to N newspaper-style columns."""
    sectPr = section._sectPr
    cols = sectPr.find(qn("w:cols"))
    if cols is None:
        cols = OxmlElement("w:cols"); sectPr.append(cols)
    cols.set(qn("w:num"), str(num))
    cols.set(qn("w:space"), str(space_twips))


def add_column_break(doc):
    from docx.enum.text import WD_BREAK
    doc.add_paragraph().add_run().add_break(WD_BREAK.COLUMN)


# ── header / footer with page numbers ────────────────────────
def add_page_numbers(section, lang="ar", text=""):
    """Add a footer with a page-number field (centered)."""
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    footer = section.footer
    p = footer.paragraphs[0] if footer.paragraphs else footer.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    if text:
        p.add_run(text + "   ")
    # PAGE field
    run = p.add_run()
    fldBegin = OxmlElement("w:fldChar"); fldBegin.set(qn("w:fldCharType"), "begin")
    instr = OxmlElement("w:instrText"); instr.set(qn("xml:space"), "preserve")
    instr.text = "PAGE"
    fldEnd = OxmlElement("w:fldChar"); fldEnd.set(qn("w:fldCharType"), "end")
    run._r.append(fldBegin); run._r.append(instr); run._r.append(fldEnd)
    if lang == "ar":
        set_paragraph_rtl(p)


def set_header(section, text, lang="ar", font=None, theme_id="academic_navy"):
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    pal = load_palette(theme_id)
    header = section.header
    p = header.paragraphs[0] if header.paragraphs else header.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.RIGHT if lang == "ar" else WD_ALIGN_PARAGRAPH.LEFT
    run = p.add_run(text)
    _set_run_font(run, font or ("Kufyan Arabic" if lang == "ar" else "Times New Roman"),
                  10, pal["primary"], bold=True)
    if lang == "ar":
        set_paragraph_rtl(p)


# ── table of contents field ──────────────────────────────────
def add_toc(doc, lang="ar", font=None):
    """Insert a TOC field. Word populates it on open (update fields)."""
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    title = "المحتويات" if lang == "ar" else "Table of Contents"
    h = doc.add_paragraph()
    h.alignment = WD_ALIGN_PARAGRAPH.RIGHT if lang == "ar" else WD_ALIGN_PARAGRAPH.LEFT
    run = h.add_run(title)
    _set_run_font(run, font or ("Kufyan Arabic" if lang == "ar" else "Times New Roman"),
                  16, None, bold=True)
    if lang == "ar":
        set_paragraph_rtl(h)

    p = doc.add_paragraph()
    run = p.add_run()
    fldBegin = OxmlElement("w:fldChar"); fldBegin.set(qn("w:fldCharType"), "begin")
    instr = OxmlElement("w:instrText"); instr.set(qn("xml:space"), "preserve")
    instr.text = 'TOC \\o "1-3" \\h \\z \\u'
    fldSep = OxmlElement("w:fldChar"); fldSep.set(qn("w:fldCharType"), "separate")
    placeholder = OxmlElement("w:t")
    placeholder.text = ("اضغط تحديث الحقول لعرض المحتويات" if lang == "ar"
                        else "Right-click > Update Field to build the TOC")
    fldEnd = OxmlElement("w:fldChar"); fldEnd.set(qn("w:fldCharType"), "end")
    run._r.append(fldBegin); run._r.append(instr); run._r.append(fldSep)
    run._r.append(placeholder); run._r.append(fldEnd)
    if lang == "ar":
        set_paragraph_rtl(p)


# ── colored heading ──────────────────────────────────────────
def add_colored_heading(doc, text, level=1, lang="ar", theme_id="academic_navy",
                        font=None):
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    pal = load_palette(theme_id)
    h = doc.add_heading("", level=level)
    h.alignment = WD_ALIGN_PARAGRAPH.RIGHT if lang == "ar" else WD_ALIGN_PARAGRAPH.LEFT
    run = h.add_run(text)
    size = {1: 18, 2: 15, 3: 13}.get(level, 12)
    _set_run_font(run, font or ("Kufyan Arabic" if lang == "ar" else "Times New Roman"),
                  size, pal["primary"], bold=True)
    if lang == "ar":
        set_paragraph_rtl(h)
    return h


if __name__ == "__main__":
    # self-test: build a document exercising every feature
    from docx import Document
    doc = Document()
    sec = doc.sections[0]
    set_header(sec, "تقرير تجريبي", lang="ar")
    add_page_numbers(sec, lang="ar", text="صفحة")
    add_toc(doc, lang="ar")
    add_colored_heading(doc, "المقدمة", 1, lang="ar")
    doc.add_paragraph("نص تجريبي للفقرة.")
    add_table(doc, ["البند", "القيمة"], [["أ", 10], ["ب", 20]],
              lang="ar", totals_row=["الإجمالي", 30])
    doc.save("/tmp/advanced_test.docx")
    print("saved /tmp/advanced_test.docx")


def _md_table_sep(line):
    """True if `line` is a GFM table separator row (| --- | :--- | ...)."""
    import re
    return bool(re.match(
        r"^\s*\|?\s*:?-{1,}:?\s*(\|\s*:?-{1,}:?\s*)*\|?\s*$", line)) \
        and "-" in line


def _md_cells(line):
    s = line.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|"):
        s = s[:-1]
    return [c.strip() for c in s.split("|")]


def _parse_glued_table(line):
    """A Markdown table can arrive glued onto ONE line — rows joined by '||'
    (e.g. '| h1 | h2 || --- | --- || a | b |') when newlines were lost upstream.
    Reconstruct it: the run of separator cells ('---'/':--:') gives the exact
    column count, so we chunk the remaining cells into rows deterministically.
    Returns (headers, rows) or None when the line isn't a glued table."""
    import re
    if line.count("|") < 4 or not re.search(r"\|\s*:?-{2,}:?\s*\|", line):
        return None
    toks = [c.strip() for c in line.split("|")]
    toks = [t for t in toks if t != ""]
    is_sep = [bool(re.match(r"^:?-{1,}:?$", t)) for t in toks]
    if True not in is_sep:
        return None
    first = is_sep.index(True)
    ncol = 0
    j = first
    while j < len(toks) and is_sep[j]:
        ncol += 1
        j += 1
    if ncol == 0 or first == 0:
        return None
    headers = (toks[:first] + [""] * ncol)[:ncol]
    data = toks[j:]
    rows = [data[k:k + ncol] for k in range(0, len(data), ncol)]
    rows = [(r + [""] * ncol)[:ncol] for r in rows if any(x for x in r)]
    return headers, rows


def _strip_inline_md(text):
    """Drop simple inline Markdown markers so Word shows clean text, not '**'."""
    import re
    text = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)
    text = re.sub(r"__([^_]+)__", r"\1", text)
    text = re.sub(r"(?<!\*)\*([^*\n]+)\*(?!\*)", r"\1", text)
    text = re.sub(r"`([^`]+)`", r"\1", text)
    return text


def _add_body_markdown(doc, body, lang, theme_id, font):
    """Render a section body as REAL Word content instead of dumping it as one
    run. The old builder put the whole body (newlines included) into a single
    paragraph/run; Word ignores '\\n' inside a run, so every paragraph glued
    together AND a Markdown table collapsed to raw '| a | b || c | d |' pipes.
    Here we split the body: blank line → new paragraph, a GFM table (header +
    separator + rows) → a native Word table via add_table, '#' heading → a bold
    line, '-/*' bullet → a list item. Wrapped lines of one paragraph are joined
    with a space (Markdown soft-wrap). Safe: plain prose → same paragraphs."""
    import re
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    rtl = (lang == "ar")
    pal = load_palette(theme_id)
    lines = (body or "").split("\n")
    n = len(lines)
    buf = []

    def _para(text, size=14, color=None, bold=False, style=None):
        text = _strip_inline_md(text).strip()
        if not text:
            return
        p = doc.add_paragraph(style=style) if style else doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.RIGHT if rtl else WD_ALIGN_PARAGRAPH.LEFT
        run = p.add_run(text)
        _set_run_font(run, font, size, color or pal["text"], bold=bold)
        if rtl:
            set_paragraph_rtl(p)

    def _flush():
        if buf:
            _para(" ".join(x.strip() for x in buf))
            buf.clear()

    i = 0
    while i < n:
        line = lines[i]
        # GFM table: a pipe line whose NEXT line is a separator row
        if "|" in line and i + 1 < n and _md_table_sep(lines[i + 1]):
            _flush()
            headers = _md_cells(line)
            ncol = len(headers)
            i += 2
            rows = []
            while i < n and "|" in lines[i] and lines[i].strip() != "":
                c = _md_cells(lines[i])
                rows.append([(c[j] if j < len(c) else "") for j in range(ncol)])
                i += 1
            headers = [_strip_inline_md(h) for h in headers]
            rows = [[_strip_inline_md(v) for v in r] for r in rows]
            try:
                add_table(doc, headers, rows, lang, theme_id, font)
            except Exception:
                _para(" | ".join(headers))
                for r in rows:
                    _para(" | ".join(r))
            continue
        if line.strip() == "":
            _flush()
            i += 1
            continue
        m = re.match(r"^\s*(#{1,6})\s+(.*)$", line)
        if m:
            _flush()
            _para(m.group(2), size=15, color=pal["primary"], bold=True)
            i += 1
            continue
        mb = re.match(r"^\s*[-*+]\s+(.*)$", line)
        if mb:
            _flush()
            _para(mb.group(1), style="List Bullet")
            i += 1
            continue
        # NUMBERED list item ("1. …"). Without this, consecutive numbered lines
        # were treated as Markdown soft-wrap and joined into ONE paragraph —
        # which is what glued a whole 9-entry reference list into a single
        # unreadable block.
        mn = re.match(r"^\s*\d{1,3}[.)]\s+(.*)$", line)
        if mn:
            _flush()
            _para(mn.group(1), style="List Number")
            i += 1
            continue
        # a whole table glued onto ONE line (rows joined by '||') → un-glue it
        _gt = _parse_glued_table(line)
        if _gt:
            _flush()
            _h = [_strip_inline_md(x) for x in _gt[0]]
            _r = [[_strip_inline_md(v) for v in row] for row in _gt[1]]
            try:
                add_table(doc, _h, _r, lang, theme_id, font)
            except Exception:
                _para(" | ".join(_h))
                for row in _r:
                    _para(" | ".join(row))
            i += 1
            continue
        buf.append(line)
        i += 1
    _flush()


def build_rich_docx(title, sections, output_path="research.docx", lang="ar",
                    theme_id="academic_navy", font=None, subtitle="",
                    references=None, header_text=None, page_numbers=True,
                    toc=False, two_columns=False, cover=None,
                    toc_position="after_cover"):
    """
    High-level rich document builder (Claude-quality).

    sections: list of dicts, each may contain:
        {"heading": str, "body": str,
         "table": {"headers":[...], "rows":[...], "totals":[...]}?,
         "image": {"path": str, "caption": str}?}
    Options: header_text, page_numbers, toc, two_columns.
    """
    from docx import Document
    from docx.shared import Pt
    from docx.enum.text import WD_ALIGN_PARAGRAPH

    rtl = (lang == "ar")
    font = font or ("Kufyan Arabic" if rtl else "Times New Roman")
    doc = Document()
    sec = doc.sections[0]

    # ── cover page (mandatory unless suppressed) + TOC placement ──
    # Track what the front-matter path adds, so the LEGACY title/TOC blocks
    # below don't add a SECOND cover and a SECOND table of contents (which is
    # what produced a duplicated cover plus blank pages after it).
    _fm_cover = False
    _fm_toc = False
    try:
        import sys, os
        here = os.path.dirname(os.path.abspath(__file__))
        if here not in sys.path:
            sys.path.insert(0, here)
        from docx_frontmatter import (add_cover_page, add_toc_page,
                                      should_add_cover, resolve_toc_position)
        _card = {"no_cover": (not cover) if cover is not None else False}
        if cover and should_add_cover(_card):
            _fm_cover = True
            cinfo = cover if isinstance(cover, dict) else {}
            add_cover_page(doc, title, lang=lang, theme_id=theme_id, font=font,
                           institution=cinfo.get("institution", ""),
                           subtitle=cinfo.get("subtitle", subtitle),
                           author=cinfo.get("author", ""),
                           supervisor=cinfo.get("supervisor", ""),
                           course=cinfo.get("course", ""),
                           date=cinfo.get("date", ""))
        _toc_pos = resolve_toc_position({"toc": toc,
                                         "toc_position": toc_position})
        if _toc_pos == "after_cover":
            add_toc_page(doc, lang=lang, theme_id=theme_id, font=font)
            _fm_toc = True
    except Exception:
        pass

    if header_text:
        set_header(sec, header_text, lang, font, theme_id)
    if page_numbers:
        add_page_numbers(sec, lang, "صفحة " if rtl else "Page ")

    # title — skipped when a cover page already carries it (otherwise the
    # title printed twice and read as a second cover page)
    if _fm_cover:
        tp = None
    else:
        tp = doc.add_paragraph()
        tp.alignment = WD_ALIGN_PARAGRAPH.CENTER
        trun = tp.add_run(title)
        _set_run_font(trun, font, 24, load_palette(theme_id)["primary"],
                      bold=True)
        if rtl:
            set_paragraph_rtl(tp)
    if subtitle and not _fm_cover:
        sp = doc.add_paragraph()
        sp.alignment = WD_ALIGN_PARAGRAPH.CENTER
        srun = sp.add_run(subtitle)
        _set_run_font(srun, font, 14, load_palette(theme_id)["accent"])
        if rtl:
            set_paragraph_rtl(sp)

    if toc and not _fm_toc:
        doc.add_page_break()
        add_toc(doc, lang, font)
        doc.add_page_break()

    # optionally switch body to two columns
    if two_columns:
        set_columns(sec, 2)

    # sections
    for s in sections:
        if s.get("heading"):
            # Honour the section's own LEVEL (1=مبحث, 2=مطلب, 3=تقسيم) so the
            # document shows a real hierarchy. Previously every heading was
            # forced to Heading1, which made a مطلب look identical to the
            # مبحث above it and flattened the whole outline (and the TOC).
            try:
                _lv = int(s.get("level", 1) or 1)
            except Exception:
                _lv = 1
            add_colored_heading(doc, s["heading"], max(1, min(_lv, 4)),
                                lang, theme_id, font)
        if s.get("body"):
            # Render the body as real paragraphs + native tables (not one glued
            # run). This is what makes a Markdown table in the body show as a
            # Word table instead of raw "| a | b || c | d |" pipes on one line.
            _add_body_markdown(doc, s["body"], lang, theme_id, font)
        if s.get("table"):
            t = s["table"]
            add_table(doc, t.get("headers", []), t.get("rows", []),
                      lang, theme_id, font, t.get("totals"))
        if s.get("image"):
            img = s["image"]
            add_image(doc, img.get("path", ""), img.get("caption", ""),
                      lang=lang, font=font)
        if s.get("equation"):
            # native Word equation (OMML)
            try:
                import sys, os
                here = os.path.dirname(os.path.abspath(__file__))
                if here not in sys.path:
                    sys.path.insert(0, here)
                from docx_math import add_equation
                eq = s["equation"]
                if isinstance(eq, str):
                    eq = [eq]
                for e in eq:
                    add_equation(doc, e, inline=False)
            except Exception:
                pass

    # references
    if references:
        add_colored_heading(doc, "المراجع" if rtl else "References", 1,
                            lang, theme_id, font)
        for ref in references:
            rp = doc.add_paragraph(style="List Number")
            rp.alignment = WD_ALIGN_PARAGRAPH.RIGHT if rtl else WD_ALIGN_PARAGRAPH.LEFT
            rrun = rp.add_run(ref)
            _set_run_font(rrun, font, 12, load_palette(theme_id)["text"])
            if rtl:
                set_paragraph_rtl(rp)

    # TOC at end, if requested
    try:
        if toc and toc_position == "end":
            from docx_frontmatter import add_toc_page
            doc.add_page_break()
            add_toc_page(doc, lang=lang, theme_id=theme_id, font=font,
                        page_break_after=False)
    except Exception:
        pass

    # A Word TOC is a FIELD: it renders blank until the fields are refreshed,
    # which is why the contents page looked like an empty page. Ask Word to
    # update fields when the document is opened so it fills itself in.
    if toc:
        try:
            from docx.oxml.ns import qn
            from docx.oxml import OxmlElement
            _st = doc.settings.element
            if _st.find(qn("w:updateFields")) is None:
                _uf = OxmlElement("w:updateFields")
                _uf.set(qn("w:val"), "true")
                _st.append(_uf)
        except Exception:
            pass

    doc.save(output_path)
    return output_path
