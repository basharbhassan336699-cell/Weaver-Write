# -*- coding: utf-8 -*-
"""
docx_pages.py — كم صفحةً سيكون المستند؟ تقديرٌ بلا LibreOffice ولا Word
======================================================================
قِيس على اختبار المستخدم: طلب «تقريراً من صفحتين» فخرج أربعَ صفحات، وقيل له
«صفحتان تقريباً» — النموذجُ لا يرى الصفحات. فهنا محاكاةُ التخطيط من الملفّ
نفسِه: عرضُ كلِّ كلمةٍ من جدول hmtx في ملفّ الخطّ الفعليّ (Amiri، Kufyan…)،
وارتفاعُ السطر من مقاييس الخطّ (winAscent+winDescent) ومن تباعد الأسطر،
وأبعادُ الصفحة وهوامشُها، والصورُ بارتفاعها، والجداولُ صفّاً صفّاً، وفواصلُ
الصفحات، و«ابقَ مع التالي» للعناوين. معايَرٌ على LibreOffice (tests).

estimate_pages(path) ⟵ {"pages": int, "fill": float, "words": int,
                         "words_per_page": int}
لا يحتاج مكتبةً غيرَ python-docx؛ والخطُّ غيرُ الموجود يُقدَّر بمتوسّط.
"""
from __future__ import annotations

import math
import os
import re
import struct
import sys

_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
_WP = "{http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing}"
_AR = re.compile(r"[؀-ۿݐ-ݿࢠ-ࣿﭐ-﷿ﹰ-﻿]")
_MARKS = re.compile(r"[ً-ٰٟۖ-ۭ]")     # حركاتٌ بلا عرض
# معايرةٌ على LibreOffice (انظر tests/test_docx_pages.py): الحروفُ العربيّةُ
# المتّصلةُ أضيقُ من أشكالها المنفردة في hmtx.
K_AR = 1.0
K_LAT = 1.0
# معايَرٌ على LibreOffice، فقرةً فقرة (٤١ فقرة لكلِّ خطّ — tests/test_docx_pages):
# بالتشكيل المبسَّط يطابق Cairo وKufyan وNoto Naskh وTajawal بلا تصحيح؛ وAmiri
# أضيقُ قليلاً (قِيس: ٠٫٩٨ ⟵ ٢٢٠ سطراً من ٢٢٠).
K_FONT = {"Amiri": 0.98}

_MCACHE = {}


def _font_metrics(path):
    """{upm, line, adv{codepoint: em}} من ملفّ ttf/otf — أو None."""
    if path in _MCACHE:
        return _MCACHE[path]
    m = None
    try:
        with open(path, "rb") as f:
            data = f.read()
        n = struct.unpack(">H", data[4:6])[0]
        tabs = {}
        for i in range(n):
            tag, _c, off, ln = struct.unpack(">4sIII", data[12 + 16 * i:28 + 16 * i])
            tabs[tag.decode("latin-1")] = (off, ln)
        ho = tabs["head"][0]
        upm = struct.unpack(">H", data[ho + 18:ho + 20])[0]
        hh = tabs["hhea"][0]
        h_asc, h_desc, h_gap = struct.unpack(">hhh", data[hh + 4:hh + 10])
        nhm = struct.unpack(">H", data[hh + 34:hh + 36])[0]
        line = (h_asc - h_desc + h_gap) / upm
        if "OS/2" in tabs:
            # USE_TYPO_METRICS ⟵ مقاييسُ typo، وإلّا hhea. قِيس على LibreOffice:
            # سطرُ Amiri ١٤pt×1.15 = 28.25pt ⟵ 1.755em (typo)، لا 2.76 (win)
            oo = tabs["OS/2"][0]
            fsel = struct.unpack(">H", data[oo + 62:oo + 64])[0]
            ta, td, tg = struct.unpack(">hhh", data[oo + 68:oo + 74])
            if fsel & 128 and ta - td:
                line = (ta - td + tg) / upm
        hm = tabs["hmtx"][0]
        advs = [struct.unpack(">H", data[hm + 4 * i:hm + 4 * i + 2])[0]
                for i in range(nhm)]
        # cmap: الصيغةُ ٤ (BMP) من (3,1) أو (0,x)
        co = tabs["cmap"][0]
        nt = struct.unpack(">H", data[co + 2:co + 4])[0]
        sub = None
        for i in range(nt):
            pid, eid, off = struct.unpack(">HHI", data[co + 4 + 8 * i:co + 12 + 8 * i])
            fmt = struct.unpack(">H", data[co + off:co + off + 2])[0]
            if fmt == 4 and (pid, eid) in ((3, 1), (0, 3), (0, 4), (0, 1), (0, 0)):
                sub = co + off
                break
        adv = {}
        if sub is not None:
            seg2 = struct.unpack(">H", data[sub + 6:sub + 8])[0]
            segs = seg2 // 2
            e0 = sub + 14
            ends = struct.unpack(">%dH" % segs, data[e0:e0 + seg2])
            s0 = e0 + seg2 + 2
            starts = struct.unpack(">%dH" % segs, data[s0:s0 + seg2])
            d0 = s0 + seg2
            deltas = struct.unpack(">%dh" % segs, data[d0:d0 + seg2])
            r0 = d0 + seg2
            ranges = struct.unpack(">%dH" % segs, data[r0:r0 + seg2])
            for k in range(segs):
                st, en = starts[k], ends[k]
                if st == 0xFFFF:
                    continue
                # النطاقاتُ المفيدة فقط: لاتينيّ وعربيّ، وأشكالُ العرض العربيّة
                # (FB50–FEFF) لعرض الحرف المتّصل
                cps = [c for lo, hi in ((max(st, 0x20), min(en, 0x06FF)),
                                        (max(st, 0xFB50), min(en, 0xFEFF)))
                       for c in range(lo, hi + 1)]
                for cp in cps:
                    if ranges[k] == 0:
                        g = (cp + deltas[k]) & 0xFFFF
                    else:
                        a = r0 + 2 * k + ranges[k] + 2 * (cp - st)
                        g = struct.unpack(">H", data[a:a + 2])[0]
                        if g:
                            g = (g + deltas[k]) & 0xFFFF
                    if g:
                        adv[cp] = advs[min(g, nhm - 1)] / upm
        m = {"upm": upm, "line": line, "adv": adv}
    except Exception:
        m = None
    _MCACHE[path] = m
    return m


# خطوطٌ لاتينيّةٌ تجاريّةٌ لا نملكها (Times New Roman، Arial…): يعرضها الجهازُ بها
# أو بمكافئٍ متريّ (Liberation) — فعروضُ ASCII هنا من Liberation Serif/Sans
# (مطابقةٌ متريّاً لـTimes/Arial)، لا من الخطّ العربيّ البديل. قِيس: بمقاييس
# Amiri البديلة قُدِّر مستندٌ إنجليزيٌّ ٦ صفحاتٍ وهو ٤.
_SERIF = "250,333,408,500,500,833,778,180,333,333,500,564,250,333,250,278,500,500,500,500,500,500,500,500,500,500,278,278,564,564,564,444,921,722,667,667,722,611,556,722,722,333,389,722,611,889,722,722,556,722,667,556,611,722,722,944,722,722,611,333,278,333,469,500,333,444,500,444,500,444,333,500,500,278,278,500,278,778,500,500,500,500,333,389,278,500,500,722,500,500,444,480,200,480,541"
_SANS = "278,278,355,556,556,889,667,191,333,333,389,584,278,333,278,278,556,556,556,556,556,556,556,556,556,556,278,278,584,584,584,556,1015,667,667,722,722,667,611,778,722,278,500,667,556,833,722,778,667,778,722,667,611,722,667,944,667,667,611,278,278,278,469,556,333,556,556,500,556,556,278,556,556,222,222,500,222,833,556,556,556,556,333,500,278,556,500,722,500,500,500,334,260,334,584"
_SANS_NAMES = ("arial", "helvetica", "calibri", "segoe", "tahoma", "verdana",
               "aptos", "sans", "gill", "trebuchet", "roboto", "open sans")


def _generic(family):
    tab = _SANS if any(k in family.lower() for k in _SANS_NAMES) else _SERIF
    adv = {32 + i: int(v) / 1000 for i, v in enumerate(tab.split(","))}
    return {"upm": 1000, "line": 1.15, "adv": adv}


def _font_file(family, latin_generic=False, weight=None):
    if not family:
        return None
    try:
        here = os.path.dirname(os.path.abspath(__file__))
        fc = os.path.join(here, "..", "..", "..", "..", "engines", "fonts-core")
        fc = os.path.normpath(fc)
        if fc not in sys.path:
            sys.path.insert(0, fc)
        import font_catalog
        e = font_catalog.find_font(family)
        if not e:
            return None
        if not e.get("bundled"):
            if latin_generic and e.get("script") != "ar":
                return "generic:" + family
            if e.get("stand_in"):
                e = font_catalog.find_font(e["stand_in"])
        return font_catalog.file_for(e, weight)
    except Exception:
        return None


def _metrics(family, bold=False):
    """مقاييسُ الخطّ — بملفّ العريض إن وُجد (فلا يُضاف تعريضٌ تقديريّ)."""
    p = _font_file(family, latin_generic=True, weight="bold" if bold else None)
    if p and p.startswith("generic:"):
        return _generic(family)
    m = _font_metrics(p) if p else None
    if m is None:
        return None
    m = dict(m)
    m["bold_file"] = bool(bold and re.search(r"bold|black", os.path.basename(p), re.I))
    m["k"] = next((v for k, v in K_FONT.items() if family and
                   family.lower().startswith(k.lower())), 1.0)
    return m


# ───────────────────────── قراءةُ الخصائص مع الوراثة ─────────────────────────
class _Styles:
    def __init__(self, doc):
        self.by_id = {}
        root = doc.styles.element
        for st in root.findall(_W + "style"):
            self.by_id[st.get(_W + "styleId")] = st
        dd = root.find(_W + "docDefaults")
        self.d_rpr = dd.find(_W + "rPrDefault/" + _W + "rPr") if dd is not None else None
        self.d_ppr = dd.find(_W + "pPrDefault/" + _W + "pPr") if dd is not None else None
        self.default_p = next((sid for sid, st in self.by_id.items()
                               if st.get(_W + "type") == "paragraph"
                               and st.get(_W + "default") == "1"), None)

    def chain(self, sid):
        out, seen = [], set()
        while sid and sid in self.by_id and sid not in seen:
            seen.add(sid)
            st = self.by_id[sid]
            out.append(st)
            b = st.find(_W + "basedOn")
            sid = b.get(_W + "val") if b is not None else None
        return out


def _first(elems, path, attr=None):
    """أوّلُ قيمةٍ موجودة عبر سلسلة عناصر (الأقربُ أوّلاً)."""
    for e in elems:
        if e is None:
            continue
        x = e.find(path)
        if x is not None:
            return x if attr is None else x.get(_W + attr)
    return None


def _on(x):
    return x is not None and x.get(_W + "val") not in ("0", "false", "off")


def _para_props(p, S, tbl_style=None):
    ppr = p.find(_W + "pPr")
    sid = None
    if ppr is not None:
        ps = ppr.find(_W + "pStyle")
        sid = ps.get(_W + "val") if ps is not None else None
    chain = S.chain(sid or S.default_p)
    if tbl_style:
        # داخل جدول: نمطُ الجدول فوق النمط الافتراضيّ (Normal) وتحت غيره —
        # قِيس: TableGrid يجعل after=0 والسطرَ مفرداً، فالصفُّ ٢٠pt لا ٣٤
        own = [st for st in chain if st.get(_W + "styleId") != S.default_p
               and st.get(_W + "default") != "1"]
        rest = [st for st in chain if st not in own]
        tchain = S.chain(tbl_style)
        chain = own + tchain + rest
    pprs = [ppr] + [st.find(_W + "pPr") for st in chain] + [S.d_ppr]
    rprs = [st.find(_W + "rPr") for st in chain] + [S.d_rpr]
    sp = {}
    for k in ("before", "after", "line", "lineRule", "beforeAutospacing"):
        v = _first(pprs, _W + "spacing[@" + _W + k + "]", k)
        sp[k] = v
    ind = {}
    for k in ("left", "right", "start", "end", "firstLine", "hanging"):
        v = _first(pprs, _W + "ind[@" + _W + k + "]", k)
        ind[k] = int(v) / 20 if v and v.lstrip("-").isdigit() else 0
    return {
        "before": int(sp["before"] or 0) / 20,
        "after": int(sp["after"] or 0) / 20,
        "line": int(sp["line"]) if sp["line"] else 240,
        "rule": sp["lineRule"] or "auto",
        "keep_next": _on(_first(pprs, _W + "keepNext")),
        "keep_lines": _on(_first(pprs, _W + "keepLines")),
        "break_before": _on(_first(pprs, _W + "pageBreakBefore")),
        "indent": max(ind["left"], ind["start"]) + max(ind["right"], ind["end"]),
        "first": ind["firstLine"] - ind["hanging"],
        "contextual": _on(_first(pprs, _W + "contextualSpacing")),
        "sid": sid,
        "rprs": rprs,
    }


def _run_font(r, base_rprs):
    rpr = r.find(_W + "rPr")
    rprs = [rpr] + base_rprs
    sz = _first(rprs, _W + "szCs", "val") or _first(rprs, _W + "sz", "val")
    sz_l = _first(rprs, _W + "sz", "val") or sz
    fonts = _first(rprs, _W + "rFonts")
    cs = latin = None
    for e in rprs:
        if e is None:
            continue
        f = e.find(_W + "rFonts")
        if f is None:
            continue
        cs = cs or f.get(_W + "cs")
        latin = latin or f.get(_W + "ascii") or f.get(_W + "hAnsi")
    bold = _on(_first(rprs, _W + "bCs")) or _on(_first(rprs, _W + "b"))
    del fonts
    return {"cs_size": int(sz or 22) / 2, "lat_size": int(sz_l or 22) / 2,
            "cs": cs, "latin": latin, "bold": bold}


# ── تشكيلٌ مبسَّط: الحرفُ العربيُّ بشكله في الكلمة (أوّل/وسط/آخر/منفرد) ──
# قِيس: عرضُ الحرف المنفرد من hmtx لا يمثّل المتّصل — Kufyan خرج سطرُه ضعفَ
# التقدير. فأشكالُ العرض (FExx) من ملفّ الخطّ نفسِه، وجدولُها من unicodedata.
_FORMS = None


def _forms():
    global _FORMS
    if _FORMS is None:
        import unicodedata
        f = {}
        for cp in list(range(0xFB50, 0xFDFF)) + list(range(0xFE70, 0xFEFF)):
            dec = unicodedata.decomposition(chr(cp)).split()
            if len(dec) == 2 and dec[0] in ("<isolated>", "<final>", "<initial>",
                                            "<medial>"):
                f.setdefault((int(dec[1], 16), dec[0][1:-1]), cp)
            elif len(dec) == 3 and dec[0] in ("<isolated>", "<final>"):
                f.setdefault((int(dec[1], 16), int(dec[2], 16), dec[0][1:-1]), cp)
        _FORMS = f
    return _FORMS


def _word_w(word, size, met, bold):
    """عرضُ كلمةٍ عربيّةٍ بأشكال حروفها المتّصلة (pt)."""
    if not met:
        return sum(_char_w(c, size, met, bold) for c in word)
    F = _forms()
    adv = met["adv"]
    letters = [c for c in word if not _MARKS.match(c)]
    total, i = 0.0, 0
    n = len(letters)

    def dual(c):
        return (ord(c), "medial") in F

    def joins(c):
        return (ord(c), "final") in F
    while i < n:
        c = letters[i]
        o = ord(c)
        prev = i > 0 and dual(letters[i - 1]) and joins(c)
        # لام ألف
        if o == 0x0644 and i + 1 < n and (o, ord(letters[i + 1]), "final") in F:
            key = (o, ord(letters[i + 1]), "final" if prev else "isolated")
            cp = F.get(key)
            w = adv.get(cp) if cp else None
            if w:
                total += w
                i += 2
                continue
        nxt = i + 1 < n and dual(c) and joins(letters[i + 1])
        form = ("medial" if prev and nxt else "initial" if nxt else
                "final" if prev else "isolated")
        cp = F.get((o, form))
        w = adv.get(cp) if cp else None
        total += w if w else adv.get(o, 0.5)
        i += 1
    k = 1.0 if (not bold or met.get("bold_file")) else 1.06
    return total * size * k * K_AR * met.get("k", 1.0)


def _char_w(ch, size, met, bold):
    if _MARKS.match(ch):
        return 0.0
    k = 1.0 if (not bold or (met or {}).get("bold_file")) else 1.06
    if met and ord(ch) in met["adv"]:
        w = met["adv"][ord(ch)]
    elif ch == " ":
        w = 0.25
    else:
        w = 0.5
    return w * size * k * (K_AR if _AR.match(ch) else K_LAT)


def _para_lines(p, S, width, props):
    """(عددُ الأسطر، ارتفاعُ السطر pt، عددُ الكلمات)."""
    words = []          # [عرض]
    cur = 0.0
    biggest = 0.0
    line_mult = 1.15
    nwords = 0
    for r in p.iter(_W + "r"):
        f = _run_font(r, props["rprs"])
        m_cs = _metrics(f["cs"], f["bold"])
        m_lat = _metrics(f["latin"], f["bold"]) or m_cs
        seg = []                          # حروفٌ عربيّةٌ متتالية ⟵ تُشكَّل معاً

        def flush():
            nonlocal cur
            if seg:
                cur += _word_w("".join(seg), f["cs_size"], m_cs, f["bold"])
                del seg[:]
        for t in r:
            if t.tag == _W + "t" and t.text:
                for ch in t.text:
                    ar = bool(_AR.match(ch))
                    size = f["cs_size"] if ar else f["lat_size"]
                    met = m_cs if ar else m_lat
                    lh = size * ((met or {}).get("line") or line_mult)
                    biggest = max(biggest, lh)
                    if ar:
                        seg.append(ch)
                        continue
                    flush()
                    if ch == " ":
                        if cur:
                            words.append(cur)
                            nwords += 1
                        cur = 0.0
                        words.append(-_char_w(" ", size, met, False))
                    else:
                        cur += _char_w(ch, size, met, f["bold"])
                flush()
            elif t.tag == _W + "tab":
                cur += 36
            elif t.tag == _W + "br" and t.get(_W + "type") in (None, "textWrapping"):
                words.append(cur)
                words.append(None)
                cur = 0.0
    if cur:
        words.append(cur)
        nwords += 1
    if not biggest:
        f = _run_font(p, props["rprs"])
        met = _metrics(f["cs"]) or _metrics(f["latin"])
        biggest = f["cs_size"] * ((met or {}).get("line") or line_mult)
    lines, x = 1, 0.0
    w = max(36.0, width - props["indent"])
    pend_space = 0.0
    first = props["first"]
    for ww in words:
        if ww is None:
            lines += 1
            x, pend_space = 0.0, 0.0
            continue
        if ww < 0:
            pend_space += -ww
            continue
        avail = w - (first if lines == 1 else 0)
        if x and x + pend_space + ww > avail:
            lines += 1
            x = ww
        else:
            x += (pend_space if x else 0) + ww
        pend_space = 0.0
        while x > w:                      # كلمةٌ أطولُ من السطر
            lines += 1
            x -= w
    rule, line = props["rule"], props["line"]
    if rule == "exact":
        lh = line / 20
    elif rule == "atLeast":
        lh = max(line / 20, biggest)
    else:
        lh = biggest * line / 240
    return lines, lh, nwords


def _drawing_h(p):
    h = 0.0
    for ext in p.iter(_WP + "extent"):
        try:
            h = max(h, int(ext.get("cy")) / 12700)
        except (TypeError, ValueError):
            pass
    return h


# ───────────────────────────── المحاكاة ─────────────────────────────
def _blocks(body, S, width):
    """كتلٌ متسلسلة: {"kind": para|atom|break, ...}."""
    out = []
    for el in body:
        tag = el.tag
        if tag == _W + "p":
            props = _para_props(el, S)
            if props["break_before"]:
                out.append({"kind": "break"})
            img = _drawing_h(el)
            text = "".join(t.text or "" for t in el.iter(_W + "t"))
            brk = [b for b in el.iter(_W + "br") if b.get(_W + "type") == "page"]
            if img:
                out.append({"kind": "atom", "h": img + props["before"] + props["after"],
                            "keep_next": props["keep_next"], "words": 0})
            else:
                n, lh, nw = _para_lines(el, S, width, props)
                if not text.strip() and brk:
                    n = 0
                out.append({"kind": "para", "lines": n, "lh": lh,
                            "before": props["before"], "after": props["after"],
                            "keep_next": props["keep_next"],
                            "keep_lines": props["keep_lines"], "words": nw,
                            "sid": props["sid"], "contextual": props["contextual"]})
            for _ in brk:
                out.append({"kind": "break"})
            ppr = el.find(_W + "pPr")
            if ppr is not None and ppr.find(_W + "sectPr") is not None:
                t = ppr.find(_W + "sectPr/" + _W + "type")
                if t is None or t.get(_W + "val") != "continuous":
                    out.append({"kind": "break"})
        elif tag == _W + "tbl":
            ts = el.find(_W + "tblPr/" + _W + "tblStyle")
            ts = ts.get(_W + "val") if ts is not None else None
            grid = [int(g.get(_W + "w") or 0) / 20 for g in
                    el.findall(_W + "tblGrid/" + _W + "gridCol")]
            words = 0
            rows = []
            for tr in el.findall(_W + "tr"):
                rh = 0.0
                for ci, tc in enumerate(tr.findall(_W + "tc")):
                    cw = grid[ci] if ci < len(grid) and grid[ci] else (
                        width / max(1, len(tr.findall(_W + "tc"))))
                    span = tc.find(_W + "tcPr/" + _W + "gridSpan")
                    if span is not None:
                        k = int(span.get(_W + "val") or 1)
                        cw = sum(grid[ci:ci + k]) or cw
                    h = 0.0
                    for cp in tc.findall(_W + "p"):
                        pr = _para_props(cp, S, ts)
                        n, lh, nw = _para_lines(cp, S, cw - 10.8, pr)
                        words += nw
                        h += n * lh + pr["before"] + pr["after"]
                    rh = max(rh, h)
                rows.append(rh + 2)
            out.append({"kind": "table", "rows": rows, "words": words})
    return out


def estimate_pages(path_or_doc):
    from docx import Document
    doc = Document(path_or_doc) if isinstance(path_or_doc, str) else path_or_doc
    S = _Styles(doc)
    sec = doc.sections[-1]
    pw = (sec.page_width or 7772400) / 12700
    ph = (sec.page_height or 10058400) / 12700
    lm = (sec.left_margin if sec.left_margin is not None else 914400) / 12700
    rm = (sec.right_margin if sec.right_margin is not None else 914400) / 12700
    tm = (sec.top_margin if sec.top_margin is not None else 914400) / 12700
    bm = (sec.bottom_margin if sec.bottom_margin is not None else 914400) / 12700
    width = pw - lm - rm
    height = ph - tm - bm
    cols = 1
    sp = sec._sectPr.find(_W + "cols")
    if sp is not None and (sp.get(_W + "num") or "1").isdigit():
        cols = max(1, int(sp.get(_W + "num") or 1))
        if cols > 1:
            gap = int(sp.get(_W + "space") or 720) / 20
            width = (width - gap * (cols - 1)) / cols
    blocks = _blocks(doc.element.body, S, width)

    pages, y = 1, 0.0          # «pages» هنا أعمدة؛ تُقسم على cols في النهاية
    words = 0

    def new_page():
        nonlocal pages, y
        pages += 1
        y = 0.0

    def first_need(b):
        if b is None:
            return 0.0
        if b["kind"] == "para":
            return b["before"] + b["lh"] * min(b["lines"], 2)
        if b["kind"] == "table":
            return b["rows"][0] if b["rows"] else 0.0
        if b["kind"] == "atom":
            return b["h"]
        return 0.0

    for i, b in enumerate(blocks):
        nxt = blocks[i + 1] if i + 1 < len(blocks) else None
        words += b.get("words", 0)
        if b["kind"] == "break":
            new_page()
            continue
        if b["kind"] == "atom":
            need = b["h"] + (first_need(nxt) if b["keep_next"] else 0)
            if y and y + need > height:
                new_page()
            y += b["h"]
            continue
        if b["kind"] == "table":
            for rh in b["rows"]:
                if y and y + rh > height:
                    new_page()
                y += rh
            continue
        # فقرة: «بعد» السابقة و«قبل» هذه يُجمعان (Word)؛ وفي أعلى الصفحة لا «قبل»
        before = 0.0 if y == 0 else b["before"]
        body = b["lines"] * b["lh"]
        if b["keep_next"] and nxt is not None:
            need = before + body + first_need(nxt)
            if y and y + need > height:
                new_page()
                before = 0.0
        elif b["keep_lines"] and y and y + before + body > height:
            new_page()
            before = 0.0
        y += before
        left = b["lines"]
        while left:
            room = int(max(0.0, height - y) // b["lh"]) if b["lh"] else left
            if room >= left:
                y += left * b["lh"]
                left = 0
            else:
                # التحكّمُ بالأرامل واليتامى: سطران على الأقلّ في كلِّ جهة
                split = room if left - room >= 2 else left - 2
                if split < 2:
                    if y == 0:            # لا مكانَ أصلاً: تُكسر كيفما اتّفق
                        split = max(1, room)
                    else:
                        new_page()
                        continue
                left -= split
                y += split * b["lh"]
                new_page()
        y += b["after"]
    total_cols = pages
    fill = min(1.0, max(0.0, y / height)) if height else 1.0
    n_pages = int(math.ceil(total_cols / cols))
    if cols > 1:
        fill = ((total_cols - 1) % cols + fill) / cols
    full = (n_pages - 1) + fill
    wpp = int(words / full) if full > 0.2 else words
    return {"pages": n_pages, "fill": round(fill, 2), "words": words,
            "words_per_page": wpp, "exact": round(full, 2)}


if __name__ == "__main__":
    for a in sys.argv[1:]:
        print(a, estimate_pages(a))
