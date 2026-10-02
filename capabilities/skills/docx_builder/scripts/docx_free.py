# -*- coding: utf-8 -*-
"""
docx_free.py — التصميمُ الحرّ لمستندات Word (النشرات، التقارير المصمَّمة، الكتيّبات،
السير الذاتية، الشهادات) — أمّا البحوثُ والواجباتُ فبالقالب الرسميّ (docx_advanced).
=================================================================================
صفحاتُ Word تتدفّق ولا تُرسم بإحداثيات (الأشكالُ العائمةُ تتبعثر في عارضات الهاتف)،
فالحرّيّةُ هنا في **كتلٍ** يركّبها النموذجُ بترتيبه وألوانه وأحجامه: شريطُ غلافٍ
ملوّن، عناوينُ بخطٍّ مميّز، فقرات، نقاط، صناديقُ تنبيه، بطاقات، أرقامٌ كبيرة،
اقتباس، أعمدة، صور (أو إطارٌ فارغ)، رسم، جدول، فاصل. كلُّها عناصرُ Word أصليّة
(جداولُ بلا حدودٍ للتخطيط) — تُفتح وتُعدَّل في أيّ برنامج.

الاتّجاه: بعد البناء تمرّ الفقراتُ كلُّها على docx_rtl.finalize_direction (المقيسة:
العربيُّ من اليمين والإنجليزيُّ من اليسار، فقرةً فقرة)، والجداولُ في المستند العربيّ
bidiVisual (البطاقةُ الأولى يميناً). ثمّ المحاذاةُ المطلوبةُ بصريّاً («يمين/يسار/وسط»)
تُكتب منطقيّاً — قِيس: في فقرةٍ من اليمين jc=right يظهر يساراً، وبلا jc يميناً.

ومعاينةٌ: صفحاتٌ مرسومةٌ (Pillow + raqm) لينظر إليها النموذجُ ويصحّح، وفحصٌ للتباين
والخطّ الصغير.
"""
from __future__ import annotations

import os
import re
import sys

from docx import Document
from docx.enum.text import WD_BREAK
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)
import docx_rtl   # noqa: E402

PAGE = {"A4": (8.27, 11.69), "letter": (8.5, 11.0)}
_AR = re.compile(r"[؀-ۿݐ-ݿࢠ-ࣿﭐ-﷿ﹰ-﻿]")
_LAT = re.compile(r"[A-Za-zÀ-ɏ]")
PLACEHOLDER = "أضف صورة"


# ─────────────────────────── أدوات ───────────────────────────
def _f(v, d=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return d


def _hex(c, d=None):
    if c is None or c == "":
        return d
    s = str(c).strip().lstrip("#")
    if len(s) == 3:
        s = "".join(ch * 2 for ch in s)
    return s[:6].upper() if re.fullmatch(r"[0-9A-Fa-f]{6}", s[:6] or "") else d


def _rgb(c):
    c = _hex(c, "000000")
    return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))


def _lum(c):
    def ch(v):
        v = v / 255
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    r, g, b = (ch(v) for v in _rgb(c))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a, b):
    la, lb = _lum(a), _lum(b)
    return (max(la, lb) + 0.05) / (min(la, lb) + 0.05)


def _auto(bg):
    return "FFFFFF" if _lum(bg or "FFFFFF") < 0.33 else "1F2937"


def is_rtl(text, doc_rtl):
    """كقاعدة docx_rtl.fix_paragraph: عربيٌّ ⟵ يمين؛ بلا حروف ⟵ اتّجاهُ المستند."""
    t = str(text or "")
    return bool(_AR.search(t)) or (doc_rtl and not _LAT.search(t))


def _lines_of(v):
    if v is None:
        return []
    items = v if isinstance(v, list) else [v]
    out = []
    for it in items:
        if isinstance(it, dict):
            for part in str(it.get("text") or "").split("\n"):
                d = dict(it)
                d["text"] = part
                out.append(d)
        else:
            out += [{"text": s} for s in str(it).split("\n")]
    return out


class Ctx:
    def __init__(self, doc, lang, font, font_en, width):
        self.doc = doc
        self.lang = lang
        self.rtl = lang == "ar"
        self.font = font
        self.font_en = font_en or font
        self.width = width                  # عرضُ النصّ (بوصة)
        self.align = []                     # [(عنصر p، محاذاةٌ بصريّة)]
        self.fonts = []                     # [(عنصر r، خطّ)]
        self.used_fonts = set()


# ─────────────────────────── XML ───────────────────────────
def _shade(el_pr, fill):
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), fill)
    el_pr.append(shd)


def _cell_pr(cell):
    return cell._tc.get_or_add_tcPr()


def _cell_fill(cell, fill):
    if fill:
        _shade(_cell_pr(cell), fill)


def _cell_borders(cell, spec):
    """spec: {"top": (لون، سُمك pt), ...} — ما لم يُذكر: لا حدّ."""
    tcPr = _cell_pr(cell)
    b = OxmlElement("w:tcBorders")
    for side in ("top", "left", "bottom", "right"):
        e = OxmlElement("w:" + side)
        if side in spec and spec[side]:
            col, sz = spec[side]
            e.set(qn("w:val"), "single")
            e.set(qn("w:sz"), str(int(sz * 8)))
            e.set(qn("w:color"), col)
        else:
            e.set(qn("w:val"), "nil")
        b.append(e)
    tcPr.append(b)


def _cell_margins(cell, pad_in):
    tcPr = _cell_pr(cell)
    m = OxmlElement("w:tcMar")
    for side in ("top", "left", "bottom", "right"):
        e = OxmlElement("w:" + side)
        e.set(qn("w:w"), str(int(pad_in * 1440)))
        e.set(qn("w:type"), "dxa")
        m.append(e)
    tcPr.append(m)


def _cell_valign(cell, v="center"):
    e = OxmlElement("w:vAlign")
    e.set(qn("w:val"), v)
    _cell_pr(cell).append(e)


def _table(ctx, container, ncols, widths, bleed=False):
    """جدولُ تخطيطٍ بلا حدود: أعمدةٌ بعروضٍ بالبوصة؛ وفي العربيّ من اليمين."""
    t = container.add_table(rows=1, cols=ncols)
    t.autofit = False
    tblPr = t._tbl.tblPr
    for tag in ("w:tblBorders",):
        old = tblPr.find(qn(tag))
        if old is not None:
            tblPr.remove(old)
    bd = OxmlElement("w:tblBorders")
    for side in ("top", "left", "bottom", "right", "insideH", "insideV"):
        e = OxmlElement("w:" + side)
        e.set(qn("w:val"), "nil")
        bd.append(e)
    tblPr.append(bd)
    lay = OxmlElement("w:tblLayout")
    lay.set(qn("w:type"), "fixed")
    tblPr.append(lay)
    if ctx.rtl:
        tblPr.append(OxmlElement("w:bidiVisual"))
    tw = OxmlElement("w:tblW")
    tw.set(qn("w:w"), str(int(sum(widths) * 1440)))
    tw.set(qn("w:type"), "dxa")
    old = tblPr.find(qn("w:tblW"))
    if old is not None:
        tblPr.remove(old)
    tblPr.append(tw)
    if bleed:
        ind = OxmlElement("w:tblInd")
        ind.set(qn("w:w"), str(-int(bleed * 1440)))
        ind.set(qn("w:type"), "dxa")
        tblPr.append(ind)
    grid = t._tbl.tblGrid
    for i, gc in enumerate(grid.findall(qn("w:gridCol"))):
        gc.set(qn("w:w"), str(int(widths[i] * 1440)))
    for i, c in enumerate(t.rows[0].cells):
        c.width = Inches(widths[i])
    return t


def _add_row(t, widths):
    r = t.add_row()
    for i, c in enumerate(r.cells):
        c.width = Inches(widths[i])
    return r


def _row_height(row, h_in):
    trPr = row._tr.get_or_add_trPr()
    e = OxmlElement("w:trHeight")
    e.set(qn("w:val"), str(int(h_in * 1440)))
    e.set(qn("w:hRule"), "atLeast")
    trPr.append(e)


def _para(ctx, container, text, size=12, bold=False, color=None, align=None,
          font=None, before=0, after=6, ls=1.15, keep_next=False, italic=False,
          first=False, runs=None):
    """فقرة. container: المستند أو خليّة. first: استعمل فقرةَ الخليّة الأولى الفارغة."""
    if first and hasattr(container, "paragraphs") and container.paragraphs \
            and not container.paragraphs[0].text and len(container.paragraphs) == 1:
        p = container.paragraphs[0]
    else:
        p = container.add_paragraph()
    pf = p.paragraph_format
    pf.space_before = Pt(before)
    pf.space_after = Pt(after)
    pf.line_spacing = ls
    pf.keep_with_next = keep_next
    for txt, o in (runs or [(text, {})]):
        r = p.add_run(str(txt))
        r.font.size = Pt(o.get("size", size))
        r.font.bold = o.get("bold", bold)
        r.font.italic = italic
        col = _hex(o.get("color", color))
        if col:
            r.font.color.rgb = RGBColor.from_string(col)
        f = o.get("font", font)
        if f:
            ctx.fonts.append((r._r, f))
    if not str(text or "").strip() and not runs:
        # فقرةٌ فارغة (فاصل): ارتفاعُها من علامة الفقرة لا من الـrun — قِيس:
        # بلا هذا كانت ٢٦pt (الخطُّ الافتراضيّ) بدل ٤، فنزلت كتلةٌ إلى الصفحة التالية
        pPr = p._p.get_or_add_pPr()
        rpr = pPr.find(qn("w:rPr"))
        if rpr is None:
            rpr = OxmlElement("w:rPr")
            pPr.append(rpr)
        for tag in ("w:sz", "w:szCs"):
            e = OxmlElement(tag)
            e.set(qn("w:val"), str(max(2, int(size * 2))))
            rpr.append(e)
        pf.line_spacing = 1.0
    if align:
        ctx.align.append((p._p, align))
    return p


def _bottom_rule(p, color, sz_pt=1.5, space=4):
    pPr = p._p.get_or_add_pPr()
    bdr = OxmlElement("w:pBdr")
    b = OxmlElement("w:bottom")
    b.set(qn("w:val"), "single")
    b.set(qn("w:sz"), str(int(sz_pt * 8)))
    b.set(qn("w:space"), str(space))
    b.set(qn("w:color"), color)
    bdr.append(b)
    pPr.append(bdr)


# ─────────────────────────── الكتل ───────────────────────────
def b_hero(ctx, c, b, width, bg_under):
    bg = _hex(b.get("bg"), "1E3A5F")
    col = _hex(b.get("color"), _auto(bg))
    bleed = _f(b.get("bleed"), 0) if b.get("bleed") else 0
    w = width + 2 * bleed
    t = _table(ctx, c, 1, [w], bleed=bleed or False)
    cell = t.rows[0].cells[0]
    _cell_fill(cell, bg)
    _cell_margins(cell, _f(b.get("padding"), 0.35))
    _cell_valign(cell)
    _row_height(t.rows[0], _f(b.get("height"), 2.0))
    _no_split(t)
    al = b.get("align")
    if b.get("kicker"):
        _para(ctx, cell, b["kicker"], size=_f(b.get("kicker_size"), 12), bold=True,
              color=_hex(b.get("accent"), col), align=al, first=True, after=4)
    _para(ctx, cell, b.get("title", ""), size=_f(b.get("size"), 30), bold=True,
          color=col, align=al, first=not b.get("kicker"), after=6, ls=1.05,
          font=b.get("font"))
    if b.get("subtitle"):
        _para(ctx, cell, b["subtitle"], size=_f(b.get("subtitle_size"), 15),
              color=_hex(b.get("subtitle_color"), col), align=al, after=0)
    _para(ctx, c, "", size=4, after=_f(b.get("after"), 10))


def b_heading(ctx, c, b, width, bg_under):
    p = _para(ctx, c, b.get("text", ""), size=_f(b.get("size"), 20), bold=True,
              color=_hex(b.get("color"), "1F2937"), align=b.get("align"),
              before=_f(b.get("before"), 12), after=_f(b.get("after"), 6),
              keep_next=True, ls=1.1, font=b.get("font"))
    if b.get("rule"):
        _bottom_rule(p, _hex(b.get("rule"), "C8A04A"), _f(b.get("rule_w"), 2))


def b_text(ctx, c, b, width, bg_under):
    for i, it in enumerate(_lines_of(b.get("text"))):
        _para(ctx, c, it["text"], size=_f(it.get("size", b.get("size")), 12),
              bold=bool(it.get("bold", b.get("bold"))),
              color=_hex(it.get("color", b.get("color")), _auto(bg_under)),
              align=it.get("align", b.get("align")),
              after=_f(b.get("after"), 6), ls=_f(b.get("line_spacing"), 1.3),
              font=it.get("font", b.get("font")), first=(i == 0 and b.get("_first")))


def b_bullets(ctx, c, b, width, bg_under):
    mk = str(b.get("marker") or "●")
    mc = _hex(b.get("marker_color"), _hex(b.get("color"), "C8A04A"))
    col = _hex(b.get("color"), _auto(bg_under))
    sz = _f(b.get("size"), 12)
    for i, it in enumerate(_lines_of(b.get("items"))):
        _para(ctx, c, "", align=b.get("align"), after=_f(b.get("after"), 4),
              ls=_f(b.get("line_spacing"), 1.25), first=(i == 0 and b.get("_first")),
              runs=[(mk + "  ", {"color": mc, "size": sz, "bold": True}),
                    (it["text"], {"color": _hex(it.get("color"), col), "size": sz,
                                  "bold": bool(it.get("bold"))})])


def b_callout(ctx, c, b, width, bg_under):
    bg = _hex(b.get("bg"), "FFF7E6")
    t = _table(ctx, c, 1, [width])
    cell = t.rows[0].cells[0]
    _cell_fill(cell, bg)
    _cell_margins(cell, _f(b.get("padding"), 0.22))
    acc = _hex(b.get("accent"), _hex(b.get("border")))
    if acc:
        _cell_borders(cell, {"top": (acc, _f(b.get("accent_w"), 3))})
    _no_split(t)
    col = _hex(b.get("color"), _auto(bg))
    first = True
    if b.get("title"):
        _para(ctx, cell, b["title"], size=_f(b.get("title_size"), 14), bold=True,
              color=_hex(b.get("title_color"), acc or col), align=b.get("align"),
              first=True, after=4)
        first = False
    for it in _lines_of(b.get("text")):
        _para(ctx, cell, it["text"], size=_f(b.get("size"), 12), color=col,
              align=b.get("align"), first=first, after=3, ls=1.25)
        first = False
    _para(ctx, c, "", size=4, after=_f(b.get("after"), 8))


def _grid(ctx, c, items, per_row, width, gap, fill_fn):
    """صفوفٌ من خلايا متساوية بفراغٍ بينها (أعمدةٌ فارغة)."""
    k = max(1, min(int(per_row or len(items) or 1), 6))
    cw = (width - gap * (k - 1)) / k
    widths = []
    for i in range(k):
        widths.append(cw)
        if i < k - 1:
            widths.append(gap)
    t = _table(ctx, c, len(widths), widths)
    rows = [items[i:i + k] for i in range(0, len(items), k)]
    for ri, chunk in enumerate(rows):
        row = t.rows[0] if ri == 0 else _add_row(t, widths)
        if ri > 0:
            pass
        for j, it in enumerate(chunk):
            fill_fn(row.cells[j * 2], it, cw)
            _trim_cell(row.cells[j * 2])
    _no_split(t)
    _para(ctx, c, "", size=4, after=8)
    return t


def b_cards(ctx, c, b, width, bg_under):
    items = [it if isinstance(it, dict) else {"text": str(it)}
             for it in b.get("items") or []]
    bg = _hex(b.get("bg"), "F3F4F6")
    acc = _hex(b.get("accent"))
    col = _hex(b.get("color"), _auto(bg))
    al = b.get("align")

    def fill(cell, it, cw):
        _cell_fill(cell, _hex(it.get("bg"), bg))
        _cell_margins(cell, _f(b.get("padding"), 0.18))
        if acc:
            _cell_borders(cell, {"top": (_hex(it.get("accent"), acc), 3)})
        first = True
        if it.get("value"):
            _para(ctx, cell, it["value"], size=_f(b.get("value_size"), 26), bold=True,
                  color=_hex(it.get("value_color"), acc or col), align=al, first=True,
                  after=2, ls=1.05)
            first = False
        if it.get("title"):
            _para(ctx, cell, it["title"], size=_f(b.get("title_size"), 14), bold=True,
                  color=_hex(it.get("title_color"), col), align=al, first=first,
                  after=3)
            first = False
        if it.get("text"):
            _para(ctx, cell, it["text"], size=_f(b.get("size"), 11), color=col,
                  align=al, first=first, after=0, ls=1.25)
    _grid(ctx, c, items, b.get("per_row") or min(3, len(items) or 1), width,
          _f(b.get("gap"), 0.18), fill)


def b_stats(ctx, c, b, width, bg_under):
    b = dict(b)
    b.setdefault("value_size", 32)
    b.setdefault("align", "center")
    b.setdefault("per_row", len(b.get("items") or []) or 1)
    items = []
    for it in b.get("items") or []:
        it = dict(it) if isinstance(it, dict) else {"value": str(it)}
        if it.get("label") and not it.get("text"):
            it["text"] = it.pop("label")
        items.append(it)
    b["items"] = items
    b_cards(ctx, c, b, width, bg_under)


def b_quote(ctx, c, b, width, bg_under):
    acc = _hex(b.get("accent"), "C8A04A")
    col = _hex(b.get("color"), _auto(bg_under))
    al = b.get("align", "center")
    _para(ctx, c, "”" if is_rtl(b.get("text"), ctx.rtl) else "“", size=48, bold=True,
          color=acc, align=al, after=0, ls=0.8)
    _para(ctx, c, b.get("text", ""), size=_f(b.get("size"), 17), italic=True, color=col,
          align=al, after=4, ls=1.3, font=b.get("font"))
    if b.get("author"):
        _para(ctx, c, "— " + str(b["author"]), size=11,
              color=_hex(b.get("author_color"), "6B7280"), align=al, after=10)


def b_columns(ctx, c, b, width, bg_under, render_blocks):
    cols = [col if isinstance(col, list) else [col] for col in b.get("columns") or []]
    if not cols:
        return
    gap = _f(b.get("gap"), 0.3)
    ws = [max(0.1, _f(x, 1)) for x in (b.get("widths") or [1] * len(cols))][:len(cols)]
    ws += [1] * (len(cols) - len(ws))
    avail = width - gap * (len(cols) - 1)
    cw = [avail * w / sum(ws) for w in ws]
    widths = []
    for i, w in enumerate(cw):
        widths.append(w)
        if i < len(cw) - 1:
            widths.append(gap)
    t = _table(ctx, c, len(widths), widths)
    fills = b.get("fills") or []
    for i, blocks in enumerate(cols):
        cell = t.rows[0].cells[i * 2]
        f = _hex(fills[i]) if i < len(fills) else None
        if f:
            _cell_fill(cell, f)
            _cell_margins(cell, _f(b.get("padding"), 0.18))
        render_blocks(ctx, cell, blocks, cw[i] - (0.36 if f else 0), f or bg_under,
                      in_cell=True)
    _no_split(t)
    _para(ctx, c, "", size=4, after=8)


def b_image(ctx, c, b, width, bg_under, chart_png=None):
    path = b.get("path")
    w = min(width, _f(b.get("width"), width * 0.8))
    al = b.get("align", "center")
    if path and os.path.isfile(str(path)):
        p = _para(ctx, c, "", align=al, after=4)
        p.add_run().add_picture(str(path), width=Inches(w))
        p.paragraph_format.keep_with_next = bool(b.get("caption"))
    else:
        # إطارٌ فارغ يضع فيه المستخدمُ صورته (كأطر العروض)
        t = _table(ctx, c, 1, [w])
        cell = t.rows[0].cells[0]
        _cell_fill(cell, "E8EAF0")
        _cell_borders(cell, {s: ("C9A44C", 1.5) for s in
                             ("top", "left", "bottom", "right")})
        _cell_valign(cell)
        _row_height(t.rows[0], _f(b.get("height"), w * 0.56))
        _no_split(t)
        _para(ctx, cell, "+  " + (b.get("placeholder") or (
            PLACEHOLDER if ctx.rtl else "Add image")), size=14, color="8A8FA0",
            align="center", first=True, after=0)
        _center_table(t)
    if b.get("caption"):
        _para(ctx, c, b["caption"], size=10, italic=True,
              color=_hex(b.get("caption_color"), "6B7280"), align=al, after=10)


def _center_table(t):
    jc = OxmlElement("w:jc")
    jc.set(qn("w:val"), "center")
    t._tbl.tblPr.append(jc)


def b_chart(ctx, c, b, width, bg_under, chart_png):
    spec = dict(b.get("chart") or {})
    if b.get("colors"):
        spec["colors"] = b["colors"]
    spec.setdefault("lang", ctx.lang)
    if ctx.font:
        spec.setdefault("font", ctx.font)
    png = chart_png(spec)
    nb = dict(b, path=png)
    b_image(ctx, c, nb, width, bg_under)


def b_table(ctx, c, b, width, bg_under):
    heads = [str(v) for v in b.get("headers") or []]
    rows = [[str(v) for v in r] for r in b.get("rows") or []]
    ncol = max([len(heads)] + [len(r) for r in rows] + [1])
    heads += [""] * (ncol - len(heads))
    rows = [r + [""] * (ncol - len(r)) for r in rows]
    lens = [max([len(heads[i])] + [len(r[i]) for r in rows]) + 4 for i in range(ncol)]
    ws = [width * x / sum(lens) for x in lens]
    t = _table(ctx, c, ncol, ws)
    hf = _hex(b.get("header_fill"), "1E3A5F")
    hc = _hex(b.get("header_color"), _auto(hf))
    f1 = _hex(b.get("fill"), "FFFFFF")
    f2 = _hex(b.get("alt_fill"), "F3F4F6")
    col = _hex(b.get("color"), _auto(f1))
    bc = _hex(b.get("border"), "E5E7EB")
    sz = _f(b.get("size"), 11)
    allrows = [heads] + rows
    for ri, vals in enumerate(allrows):
        row = t.rows[0] if ri == 0 else _add_row(t, ws)
        for ci, v in enumerate(vals):
            cell = row.cells[ci]
            _cell_fill(cell, hf if ri == 0 else (f1 if ri % 2 else f2))
            _cell_margins(cell, 0.08)
            _cell_borders(cell, {"bottom": (bc, 0.75)})
            _para(ctx, cell, v, size=sz, bold=ri == 0, color=hc if ri == 0 else col,
                  align=b.get("align"), first=True, after=0)
    _para(ctx, c, "", size=4, after=10)


def b_divider(ctx, c, b, width, bg_under):
    p = _para(ctx, c, "", size=4, before=_f(b.get("before"), 4),
              after=_f(b.get("after"), 10))
    _bottom_rule(p, _hex(b.get("color"), "D1D5DB"), _f(b.get("thickness"), 1))


def b_spacer(ctx, c, b, width, bg_under):
    p = _para(ctx, c, "", size=2, after=0)
    p.paragraph_format.space_before = Pt(_f(b.get("height"), 0.3) * 72)


def b_page_break(ctx, c, b, width, bg_under):
    p = ctx.doc.add_paragraph()
    p.add_run().add_break(WD_BREAK.PAGE)


HANDLERS = {"hero": b_hero, "heading": b_heading, "text": b_text, "bullets": b_bullets,
            "callout": b_callout, "cards": b_cards, "stats": b_stats, "quote": b_quote,
            "divider": b_divider, "spacer": b_spacer, "page_break": b_page_break,
            "table": b_table}


def _shrink_mark(p_el, half_pt=4):
    pPr = p_el.find(qn("w:pPr"))
    if pPr is None:
        pPr = OxmlElement("w:pPr")
        p_el.insert(0, pPr)
    sp = OxmlElement("w:spacing")
    sp.set(qn("w:before"), "0")
    sp.set(qn("w:after"), "0")
    sp.set(qn("w:line"), "240")
    sp.set(qn("w:lineRule"), "auto")
    old = pPr.find(qn("w:spacing"))
    if old is not None:
        pPr.remove(old)
    pPr.append(sp)
    rpr = pPr.find(qn("w:rPr"))
    if rpr is None:
        rpr = OxmlElement("w:rPr")
        pPr.append(rpr)
    for tag in ("w:sz", "w:szCs"):
        e = rpr.find(qn(tag))
        if e is None:
            e = OxmlElement(tag)
            rpr.append(e)
        e.set(qn("w:val"), str(half_pt))


def _empty(p_el):
    return p_el.tag == qn("w:p") and not "".join(
        t.text or "" for t in p_el.iter(qn("w:t"))).strip() and \
        not list(p_el.iter(qn("w:drawing"))) and not list(p_el.iter(qn("w:br")))


def _trim_cell(cell):
    """خليّةٌ تبدأ بفقرةٍ فارغة (افتراضيّة، ١٢pt) قبل محتواها، وتنتهي بفقرةٍ فارغةٍ
    يفرضها Word بعد جدولٍ داخلها — الأولى تُحذف والأخيرة تُصغَّر. قِيس: عمودٌ
    عنوانُه تحت سطرٍ فارغ، فانزاحت الكتلُ وانقسم صندوقٌ بين صفحتين."""
    kids = [k for k in cell._tc if k.tag in (qn("w:p"), qn("w:tbl"))]
    if len(kids) > 1 and _empty(kids[0]):
        cell._tc.remove(kids[0])
        kids = kids[1:]
    if len(kids) > 1 and _empty(kids[-1]) and kids[-2].tag == qn("w:tbl"):
        _shrink_mark(kids[-1], 2)


def _no_split(t):
    for row in t.rows:
        trPr = row._tr.get_or_add_trPr()
        if trPr.find(qn("w:cantSplit")) is None:
            trPr.insert(0, OxmlElement("w:cantSplit"))


def render_blocks(ctx, container, blocks, width, bg_under, chart_png=None,
                  in_cell=False):
    first = in_cell
    for b in blocks or []:
        if not isinstance(b, dict):
            b = {"type": "text", "text": str(b)}
        t = str(b.get("type") or "text").lower()
        if first and t in ("text", "bullets"):
            b = dict(b, _first=True)
        if t == "columns":
            b_columns(ctx, container, b, width, bg_under,
                      lambda cx, cc, bl, w, bg, in_cell=True: render_blocks(
                          cx, cc, bl, w, bg, chart_png, in_cell))
        elif t == "image":
            b_image(ctx, container, b, width, bg_under)
        elif t == "chart":
            b_chart(ctx, container, b, width, bg_under, chart_png)
        elif t == "page_break" and in_cell:
            continue
        elif t in HANDLERS:
            HANDLERS[t](ctx, container, b, width, bg_under)
        first = False
    if in_cell:
        _trim_cell(container)


def _visual_align(p_el, visual, doc_rtl):
    """المحاذاةُ البصريّة ⟵ قيمةُ jc المنطقيّة (بعد finalize_direction)."""
    text = "".join(t.text or "" for t in p_el.iter(qn("w:t")))
    rtl = is_rtl(text, doc_rtl)
    v = str(visual or "").lower()
    val = {"center": "center", "justify": "both"}.get(v)
    if val is None:
        if v == "right":
            val = None if rtl else "right"
        elif v == "left":
            val = "right" if rtl else None      # في فقرةٍ من اليمين right = يسار
        else:
            return
    pPr = p_el.get_or_add_pPr()
    old = pPr.find(qn("w:jc"))
    if old is not None:
        pPr.remove(old)
    if val:
        jc = OxmlElement("w:jc")
        jc.set(qn("w:val"), val)
        docx_rtl._put(pPr, jc, docx_rtl._PPR)


def build(spec, out, lang, chart_png, font=None, font_en=None):
    """يبني المستند. يعيد (عددَ الكتل، الخطوطَ المستعملة)."""
    doc = Document()
    pg = spec.get("page") or {}
    pw, ph = PAGE.get(str(pg.get("size") or "A4"), PAGE["A4"])
    m = _f(pg.get("margins"), 0.8)
    sec = doc.sections[0]
    sec.page_width, sec.page_height = Inches(pw), Inches(ph)
    sec.left_margin = sec.right_margin = Inches(m)
    sec.top_margin = sec.bottom_margin = Inches(_f(pg.get("margin_y"), m))
    # المسافاتُ الافتراضيّة صفر: كلُّ كتلةٍ تضع مسافتها
    st = doc.styles["Normal"]
    st.paragraph_format.space_after = Pt(0)
    st.font.size = Pt(12)
    bg = _hex(pg.get("bg"))
    if bg:
        b = OxmlElement("w:background")
        b.set(qn("w:color"), bg)
        doc.element.insert(0, b)
        s = doc.settings.element
        if s.find(qn("w:displayBackgroundShape")) is None:
            s.insert(0, OxmlElement("w:displayBackgroundShape"))
    ctx = Ctx(doc, lang, font, font_en, pw - 2 * m)
    blocks = spec.get("blocks") or []
    render_blocks(ctx, doc, blocks, ctx.width, bg or "FFFFFF", chart_png)
    if spec.get("page_numbers"):
        try:
            from docx_advanced import add_page_numbers
            add_page_numbers(sec, lang, "صفحة " if ctx.rtl else "Page ")
        except Exception:
            pass
    # الاتّجاه (المقيس) ثمّ الخطوط ثمّ المحاذاةُ البصريّة ثمّ خطوطُ الكتل بعينها
    docx_rtl.finalize_direction(doc, lang)
    if font or font_en:
        docx_rtl.apply_fonts(doc, cs=font or font_en, latin=font_en or font)
    for p_el, al in ctx.align:
        _visual_align(p_el, al, ctx.rtl)
    for r_el, f in ctx.fonts:
        rPr = r_el.find(qn("w:rPr"))
        if rPr is not None:
            docx_rtl._set_fonts(rPr, cs=f, latin=f)
            ctx.used_fonts.add(f)
    doc.core_properties.title = str(spec.get("title") or "")[:250]
    doc.core_properties.keywords = "weaver-free"
    doc.save(out)
    return len(blocks), sorted(ctx.used_fonts)


# ─────────────────────── المعاينة (Pillow + raqm) ───────────────────────
PX = 96


def _font(family, size_pt, bold=False):
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(_HERE)),
                                    "pptx_builder", "scripts"))
    import pptx_free
    f = pptx_free._font(family, size_pt * PX / pptx_free.PX, bold)
    if bold and pptx_free._font_file(family, True) == pptx_free._font_file(family,
                                                                             False):
        f = pptx_free._Bold(f)
    return f


def _line_em(family):
    try:
        import docx_pages
        m = docx_pages._metrics(family)
        return (m or {}).get("line") or 1.2
    except Exception:
        return 1.2


class _R:
    """مُخطِّطُ الصفحات: قطعٌ (ارتفاع، رسم) تُرصّ صفحةً صفحة."""

    def __init__(self, spec, lang, font, font_en, chart_png):
        pg = spec.get("page") or {}
        self.pw, self.ph = PAGE.get(str(pg.get("size") or "A4"), PAGE["A4"])
        self.m = _f(pg.get("margins"), 0.8)
        self.my = _f(pg.get("margin_y"), self.m)
        self.bg = _hex(pg.get("bg"), "FFFFFF")
        self.rtl = lang == "ar"
        self.lang = lang
        self.font = font or "Kufyan Arabic Regular"
        self.font_en = font_en or self.font
        self.chart_png = chart_png
        self.issues = []
        self.label = ""

    # ── نصّ ──
    def lines(self, text, size, bold, width_px, font=None, ls=1.15):
        import pptx_free
        rtl = is_rtl(text, self.rtl)
        fam = font or (self.font if rtl else self.font_en)
        f = _font(fam, size, bold)
        lh = size * PX / 72 * _line_em(fam) * ls
        words = str(text).split(" ")
        out, cur = [], ""
        for wd in words:
            cand = (cur + " " + wd) if cur else wd
            if not cur or pptx_free._length(f, cand, rtl) <= width_px:
                cur = cand
            else:
                out.append(cur)
                cur = wd
        out.append(cur)
        return out, f, rtl, lh

    def para_chunks(self, text, size=12, bold=False, color="1F2937", align=None,
                    width_px=100, font=None, after=6, before=0, ls=1.15, under=None,
                    runs_prefix=None):
        import pptx_free
        lines, f, rtl, lh = self.lines(text, size, bold, width_px, font, ls)
        if size < 9 and str(text).strip():
            self.issues.append("%s: font %gpt is too small to read — ≥ 10" % (
                self.label, size))
        if under is not None and str(text).strip() and contrast(color, under) < (
                3.0 if size >= 18 else 4.5):
            self.issues.append("%s: low contrast between text #%s and its background "
                               "#%s — change one of them" % (self.label, color, under))
        chunks = []
        al = str(align or ("right" if rtl else "left")).lower()
        for k, ln in enumerate(lines):
            h = lh + (before * PX / 72 if k == 0 else 0) + (
                after * PX / 72 if k == len(lines) - 1 else 0)

            def draw(img, x, y, w, ln=ln, k=k):
                from PIL import ImageDraw
                d = ImageDraw.Draw(img)
                yy = y + (before * PX / 72 if k == 0 else 0)
                txt = ln if not (runs_prefix and k == 0) else runs_prefix[0] + ln
                tw = pptx_free._length(f, txt, rtl)
                xx = {"right": x + w - tw, "center": x + (w - tw) / 2}.get(
                    al if al != "justify" else ("right" if rtl else "left"), x)
                top = yy + pptx_free._glyph_top(f, lh)
                pptx_free._ink(d, (xx, top), txt, f, _rgb(color), rtl)
            chunks.append((h, draw, True))
        return chunks

    # ── كتل ──
    def blocks(self, blocks, width_px, under):
        out = []
        for i, b in enumerate(blocks or [], 1):
            if not isinstance(b, dict):
                b = {"type": "text", "text": str(b)}
            t = str(b.get("type") or "text").lower()
            self.label = "block #%d (%s)" % (i, t)
            fn = getattr(self, "r_" + t, None)
            if fn:
                out += fn(b, width_px, under)
        return out

    def box(self, inner, width_px, fill, pad_px, min_h=0, border_top=None,
            valign="top", border_all=None):
        """صندوقٌ ذرّيّ: خلفيّةٌ وقطعٌ داخليّة."""
        ih = sum(h for h, _d, _s in inner)
        H = max(min_h, ih + 2 * pad_px)

        def draw(img, x, y, w):
            from PIL import ImageDraw
            d = ImageDraw.Draw(img)
            if fill:
                d.rectangle([x, y, x + w, y + H], fill=_rgb(fill))
            if border_all:
                d.rectangle([x, y, x + w, y + H], outline=_rgb(border_all), width=2)
            if border_top:
                d.rectangle([x, y, x + w, y + 3], fill=_rgb(border_top))
            yy = y + pad_px + (max(0, (H - 2 * pad_px - ih) / 2)
                               if valign == "center" else 0)
            for h, dr, _s in inner:
                dr(img, x + pad_px, yy, w - 2 * pad_px)
                yy += h
        return [(H, draw, False)]

    def gap(self, pt):
        return [(pt * PX / 72, lambda *a: None, True)]

    def r_hero(self, b, W, under):
        bg = _hex(b.get("bg"), "1E3A5F")
        col = _hex(b.get("color"), _auto(bg))
        pad = _f(b.get("padding"), 0.35) * PX
        bleed = _f(b.get("bleed"), 0) * PX if b.get("bleed") else 0
        w = W + 2 * bleed - 2 * pad
        inner = []
        if b.get("kicker"):
            inner += self.para_chunks(b["kicker"], _f(b.get("kicker_size"), 12), True,
                                      _hex(b.get("accent"), col), b.get("align"), w,
                                      after=4, under=bg)
        inner += self.para_chunks(b.get("title", ""), _f(b.get("size"), 30), True, col,
                                  b.get("align"), w, b.get("font"), 6, ls=1.05, under=bg)
        if b.get("subtitle"):
            inner += self.para_chunks(b["subtitle"], _f(b.get("subtitle_size"), 15),
                                      False, _hex(b.get("subtitle_color"), col),
                                      b.get("align"), w, after=0, under=bg)
        bx = self.box(inner, W + 2 * bleed, bg, pad, _f(b.get("height"), 2.0) * PX,
                      valign="center")
        h, dr, s = bx[0]
        return [(h, lambda img, x, y, ww, dr=dr: dr(img, x - bleed, y, ww + 2 * bleed),
                 s)] + self.gap(4 + _f(b.get("after"), 10))

    def r_heading(self, b, W, under):
        col = _hex(b.get("color"), "1F2937")
        ch = self.para_chunks(b.get("text", ""), _f(b.get("size"), 20), True, col,
                              b.get("align"), W, b.get("font"),
                              _f(b.get("after"), 6), _f(b.get("before"), 12), 1.1,
                              under=under)
        if b.get("rule") and ch:
            rc = _hex(b.get("rule"), "C8A04A")
            h, dr, s = ch[-1]

            def draw(img, x, y, w, dr=dr, h=h):
                from PIL import ImageDraw
                dr(img, x, y, w)
                ImageDraw.Draw(img).rectangle(
                    [x, y + h - _f(b.get("after"), 6) * PX / 72 - 2, x + w,
                     y + h - _f(b.get("after"), 6) * PX / 72], fill=_rgb(rc))
            ch[-1] = (h, draw, s)
        # العنوانُ لا يُترك في أسفل صفحة: يلتصق بما بعده
        return [(h, d, False) for h, d, _s in ch]

    def r_text(self, b, W, under):
        out = []
        for it in _lines_of(b.get("text")):
            out += self.para_chunks(it["text"], _f(it.get("size", b.get("size")), 12),
                                    bool(it.get("bold", b.get("bold"))),
                                    _hex(it.get("color", b.get("color")), _auto(under)),
                                    it.get("align", b.get("align")), W,
                                    it.get("font", b.get("font")),
                                    _f(b.get("after"), 6),
                                    ls=_f(b.get("line_spacing"), 1.3), under=under)
        return out

    def r_bullets(self, b, W, under):
        out = []
        mk = str(b.get("marker") or "●") + "  "
        col = _hex(b.get("color"), _auto(under))
        for it in _lines_of(b.get("items")):
            out += self.para_chunks(it["text"], _f(b.get("size"), 12), False, col,
                                    b.get("align"), W, None, _f(b.get("after"), 4),
                                    ls=_f(b.get("line_spacing"), 1.25), under=under,
                                    runs_prefix=(mk,))
        return out

    def r_callout(self, b, W, under):
        bg = _hex(b.get("bg"), "FFF7E6")
        acc = _hex(b.get("accent"), _hex(b.get("border")))
        col = _hex(b.get("color"), _auto(bg))
        pad = _f(b.get("padding"), 0.22) * PX
        w = W - 2 * pad
        inner = []
        if b.get("title"):
            inner += self.para_chunks(b["title"], _f(b.get("title_size"), 14), True,
                                      _hex(b.get("title_color"), acc or col),
                                      b.get("align"), w, after=4, under=bg)
        for it in _lines_of(b.get("text")):
            inner += self.para_chunks(it["text"], _f(b.get("size"), 12), False, col,
                                      b.get("align"), w, after=3, ls=1.25, under=bg)
        return self.box(inner, W, bg, pad, border_top=acc) + self.gap(
            4 + _f(b.get("after"), 8))

    def _grid(self, items, per_row, W, gap_in, cell_fn):
        k = max(1, min(int(per_row or len(items) or 1), 6))
        gap = gap_in * PX
        cw = (W - gap * (k - 1)) / k
        rows = [items[i:i + k] for i in range(0, len(items), k)]
        out = []
        for chunk in rows:
            cells = [cell_fn(it, cw) for it in chunk]
            H = max(sum(h for h, _d, _s in c) for c in cells) if cells else 0

            def draw(img, x, y, w, cells=cells, H=H):
                for j, c in enumerate(cells):
                    xx = (x + w - (j + 1) * cw - j * gap) if self.rtl else (
                        x + j * (cw + gap))
                    for h, dr, _s in c:
                        dr(img, xx, y, cw, H)
            out.append((H, draw, False))
        return out + self.gap(12)

    def r_cards(self, b, W, under):
        items = [it if isinstance(it, dict) else {"text": str(it)}
                 for it in b.get("items") or []]
        bg = _hex(b.get("bg"), "F3F4F6")
        acc = _hex(b.get("accent"))
        col = _hex(b.get("color"), _auto(bg))
        pad = _f(b.get("padding"), 0.18) * PX
        al = b.get("align")

        def cell(it, cw):
            fill = _hex(it.get("bg"), bg)
            w = cw - 2 * pad
            inner = []
            if it.get("value"):
                inner += self.para_chunks(it["value"], _f(b.get("value_size"), 26), True,
                                          _hex(it.get("value_color"), acc or col), al, w,
                                          after=2, ls=1.05, under=fill)
            if it.get("title"):
                inner += self.para_chunks(it["title"], _f(b.get("title_size"), 14), True,
                                          _hex(it.get("title_color"), col), al, w,
                                          after=3, under=fill)
            if it.get("text"):
                inner += self.para_chunks(it["text"], _f(b.get("size"), 11), False, col,
                                          al, w, after=0, ls=1.25, under=fill)
            ih = sum(h for h, _d, _s in inner) + 2 * pad
            topc = _hex(it.get("accent"), acc)

            def draw(img, x, y, w2, H, inner=inner, fill=fill, topc=topc):
                from PIL import ImageDraw
                d = ImageDraw.Draw(img)
                d.rectangle([x, y, x + w2, y + H], fill=_rgb(fill))
                if topc:
                    d.rectangle([x, y, x + w2, y + 3], fill=_rgb(topc))
                yy = y + pad
                for h, dr, _s in inner:
                    dr(img, x + pad, yy, w2 - 2 * pad)
                    yy += h
            return [(ih, draw, False)]
        return self._grid(items, b.get("per_row") or min(3, len(items) or 1), W,
                          _f(b.get("gap"), 0.18), cell)

    def r_stats(self, b, W, under):
        b = dict(b)
        b.setdefault("value_size", 32)
        b.setdefault("align", "center")
        b.setdefault("per_row", len(b.get("items") or []) or 1)
        items = []
        for it in b.get("items") or []:
            it = dict(it) if isinstance(it, dict) else {"value": str(it)}
            if it.get("label") and not it.get("text"):
                it["text"] = it.pop("label")
            items.append(it)
        b["items"] = items
        return self.r_cards(b, W, under)

    def r_quote(self, b, W, under):
        acc = _hex(b.get("accent"), "C8A04A")
        col = _hex(b.get("color"), _auto(under))
        al = b.get("align", "center")
        out = self.para_chunks("”" if is_rtl(b.get("text"), self.rtl) else "“", 48,
                               True, acc, al, W, after=0, ls=0.8)
        out += self.para_chunks(b.get("text", ""), _f(b.get("size"), 17), False, col, al,
                                W, b.get("font"), 4, ls=1.3, under=under)
        if b.get("author"):
            out += self.para_chunks("— " + str(b["author"]), 11, False,
                                    _hex(b.get("author_color"), "6B7280"), al, W,
                                    after=10)
        return out

    def r_columns(self, b, W, under):
        cols = [c if isinstance(c, list) else [c] for c in b.get("columns") or []]
        if not cols:
            return []
        gap = _f(b.get("gap"), 0.3) * PX
        ws = [max(0.1, _f(x, 1)) for x in (b.get("widths") or [1] * len(cols))]
        ws = (ws + [1] * len(cols))[:len(cols)]
        avail = W - gap * (len(cols) - 1)
        cw = [avail * w / sum(ws) for w in ws]
        fills = b.get("fills") or []
        pad = _f(b.get("padding"), 0.18) * PX
        cells = []
        for i, blocks in enumerate(cols):
            f = _hex(fills[i]) if i < len(fills) else None
            inner = self.blocks(blocks, cw[i] - (2 * pad if f else 0), f or under)
            cells.append((inner, f))
        H = max(sum(h for h, _d, _s in inner) + (2 * pad if f else 0)
                for inner, f in cells)

        def draw(img, x, y, w):
            from PIL import ImageDraw
            xs = []
            acc = 0.0
            for i in range(len(cols)):
                xs.append((x + w - acc - cw[i]) if self.rtl else (x + acc))
                acc += cw[i] + gap
            for i, (inner, f) in enumerate(cells):
                if f:
                    ImageDraw.Draw(img).rectangle([xs[i], y, xs[i] + cw[i], y + H],
                                                  fill=_rgb(f))
                yy = y + (pad if f else 0)
                for h, dr, _s in inner:
                    dr(img, xs[i] + (pad if f else 0), yy, cw[i] - (2 * pad if f else 0))
                    yy += h
        return [(H, draw, False)] + self.gap(12)

    def r_image(self, b, W, under):
        path = b.get("path")
        w = min(W, _f(b.get("width"), W / PX * 0.8) * PX)
        al = b.get("align", "center")
        out = []
        if path and os.path.isfile(str(path)):
            from PIL import Image
            im = Image.open(str(path)).convert("RGB")
            h = im.height * w / max(1, im.width)

            def draw(img, x, y, ww, im=im, h=h):
                xx = {"right": x + ww - w, "left": x}.get(al, x + (ww - w) / 2)
                img.paste(im.resize((int(w), int(h))), (int(xx), int(y)))
            out.append((h + 6, draw, False))
        else:
            h = _f(b.get("height"), w / PX * 0.56) * PX

            def draw(img, x, y, ww, h=h):
                from PIL import ImageDraw
                d = ImageDraw.Draw(img)
                xx = x + (ww - w) / 2
                d.rectangle([xx, y, xx + w, y + h], fill=(232, 234, 240),
                            outline=(201, 164, 76), width=2)
                f = _font("Cairo", 14)
                d.text((xx + w / 2, y + h / 2), "+  " + (PLACEHOLDER if self.rtl else
                                                         "Add image"),
                       font=f.f if hasattr(f, "f") else f, fill=(138, 143, 160),
                       anchor="mm", direction="rtl" if self.rtl else "ltr")
            out.append((h + 6, draw, False))
        if b.get("caption"):
            out += self.para_chunks(b["caption"], 10, False,
                                    _hex(b.get("caption_color"), "6B7280"), al, W,
                                    after=10)
        return out

    def r_chart(self, b, W, under):
        try:
            spec = dict(b.get("chart") or {})
            if b.get("colors"):
                spec["colors"] = b["colors"]
            spec.setdefault("lang", self.lang)
            spec.setdefault("font", self.font)
            png = self.chart_png(spec)
            return self.r_image(dict(b, path=png), W, under)
        except Exception:
            return self.r_image(dict(b, path=None), W, under)

    def r_table(self, b, W, under):
        heads = [str(v) for v in b.get("headers") or []]
        rows = [[str(v) for v in r] for r in b.get("rows") or []]
        ncol = max([len(heads)] + [len(r) for r in rows] + [1])
        heads += [""] * (ncol - len(heads))
        rows = [r + [""] * (ncol - len(r)) for r in rows]
        lens = [max([len(heads[i])] + [len(r[i]) for r in rows]) + 4
                for i in range(ncol)]
        ws = [W * x / sum(lens) for x in lens]
        hf = _hex(b.get("header_fill"), "1E3A5F")
        hc = _hex(b.get("header_color"), _auto(hf))
        f1, f2 = _hex(b.get("fill"), "FFFFFF"), _hex(b.get("alt_fill"), "F3F4F6")
        col = _hex(b.get("color"), _auto(f1))
        sz = _f(b.get("size"), 11)
        pad = 0.08 * PX
        out = []
        for ri, vals in enumerate([heads] + rows):
            fill = hf if ri == 0 else (f1 if ri % 2 else f2)
            cells = [self.para_chunks(v, sz, ri == 0, hc if ri == 0 else col,
                                      b.get("align"), ws[ci] - 2 * pad, after=0,
                                      under=fill) for ci, v in enumerate(vals)]
            H = max(sum(h for h, _d, _s in c) for c in cells) + 2 * pad

            def draw(img, x, y, w, cells=cells, fill=fill, H=H):
                from PIL import ImageDraw
                d = ImageDraw.Draw(img)
                acc = 0.0
                for ci, c in enumerate(cells):
                    xx = (x + w - acc - ws[ci]) if self.rtl else (x + acc)
                    d.rectangle([xx, y, xx + ws[ci], y + H], fill=_rgb(fill))
                    yy = y + pad
                    for h, dr, _s in c:
                        dr(img, xx + pad, yy, ws[ci] - 2 * pad)
                        yy += h
                    acc += ws[ci]
                d.line([x, y + H, x + w, y + H], fill=(229, 231, 235), width=1)
            out.append((H, draw, False))
        return out + self.gap(10)

    def r_divider(self, b, W, under):
        col = _rgb(_hex(b.get("color"), "D1D5DB"))
        th = max(1, _f(b.get("thickness"), 1) * PX / 72)
        h = (_f(b.get("before"), 4) + _f(b.get("after"), 10)) * PX / 72 + th

        def draw(img, x, y, w):
            from PIL import ImageDraw
            yy = y + _f(b.get("before"), 4) * PX / 72
            ImageDraw.Draw(img).rectangle([x, yy, x + w, yy + th], fill=col)
        return [(h, draw, True)]

    def r_spacer(self, b, W, under):
        return self.gap(_f(b.get("height"), 0.3) * 72)

    def r_page_break(self, b, W, under):
        return [("BREAK", None, True)]


def render_check(spec, out_dir, stem, lang, font=None, font_en=None, chart_png=None,
                 max_pages=40):
    """صورٌ للصفحات + صورةٌ جامعة + مشكلاتٌ مقيسة. يعيد (المسارات، الجامعة، المشكلات)."""
    from PIL import Image
    R = _R(spec, lang, font, font_en, chart_png)
    W = (R.pw - 2 * R.m) * PX
    chunks = R.blocks(spec.get("blocks") or [], W, R.bg)
    pages, y = [[]], 0.0
    H = (R.ph - 2 * R.my) * PX
    for h, dr, splittable in chunks:
        if h == "BREAK":
            pages.append([])
            y = 0.0
            continue
        if y and y + h > H:
            pages.append([])
            y = 0.0
        pages[-1].append((y, dr))
        y += h
        if len(pages) > max_pages:
            break
    os.makedirs(out_dir, exist_ok=True)
    paths = []
    for i, items in enumerate(pages, 1):
        img = Image.new("RGB", (int(R.pw * PX), int(R.ph * PX)), _rgb(R.bg))
        for yy, dr in items:
            dr(img, R.m * PX, R.my * PX + yy, W)
        p = os.path.join(out_dir, "%s-p%02d.png" % (stem, i))
        img.save(p, optimize=True)
        paths.append(p)
    ov = _overview(paths, os.path.join(out_dir, "%s-overview.png" % stem))
    issues = list(dict.fromkeys(R.issues))
    return paths, ov, issues, len(pages)


def _overview(paths, out):
    from PIL import Image, ImageDraw
    if not paths:
        return None
    cols = min(4, len(paths))
    tw, th = 300, 424
    rows = (len(paths) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * (tw + 12) + 12, rows * (th + 30) + 12), (40, 40, 48))
    d = ImageDraw.Draw(sheet)
    for i, p in enumerate(paths):
        im = Image.open(p)
        im.thumbnail((tw, th))
        x = 12 + (i % cols) * (tw + 12)
        y = 12 + (i // cols) * (th + 30)
        sheet.paste(im, (x, y + 20))
        d.text((x, y + 2), "%d" % (i + 1), fill=(230, 230, 235))
    sheet.save(out, optimize=True)
    return out
