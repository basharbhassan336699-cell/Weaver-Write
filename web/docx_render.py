"""docx_render.py — صفحاتُ مستند Word صوراً، كما تُطبع، بلا LibreOffice ولا Word.

    render_docx(path) ⟵ [PIL.Image …]   صفحةٌ لكلِّ عنصر

لا LibreOffice على الهاتف (Termux)، فالتخطيطُ هنا من الملفّ نفسِه:
· الخصائصُ بالوراثة (docDefaults ⟵ الأنماط ⟵ الفقرة ⟵ المقطع) — من
  capabilities/skills/docx_builder/scripts/docx_pages.py (معايَرٌ على LibreOffice).
· الخطُّ الفعليُّ لكلِّ مقطع (font_catalog: المجمَّعُ أو أقربُ بديل)، وعرضُ كلِّ
  كلمةٍ يُقاس بالخطّ نفسِه مشكَّلاً (raqm)، وارتفاعُ السطر من مقاييس الخطّ.
· اتّجاهُ الفقرة (bidi) وترتيبُ الكلمات المختلطة (عربيّ/لاتينيّ/أرقام)،
  والمحاذاة والضبط، والمسافاتُ قبل/بعد، والإزاحات، والترقيمُ والتعداد.
· الجداول: أعرضةُ الأعمدة، والدمج، والتظليل، والحدود (الخليّة ⟵ الجدول ⟵
  نمطُه)، والصفُّ الأوّل من نمط الجدول، وتكرارُ صفِّ العنوان.
· الصورُ بأبعادها، وفواصلُ الصفحات، و«ابقَ مع التالي»، والأراملُ واليتامى.
· الترويسةُ والتذييل، ورقمُ الصفحة (PAGE / NUMPAGES).

ليس Word نفسَه: قد يختلف موضعُ انكسار سطرٍ أو صفحةٍ قليلاً. لا يرفع أبداً
إلا من render_docx إن كان الملفُّ تالفاً (يلتقطه المُنادي).
"""
from __future__ import annotations

import io
import os
import re
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
_DP = os.path.join(_ROOT, "capabilities", "skills", "docx_builder", "scripts")
_FC = os.path.join(_ROOT, "engines", "fonts-core")
for _p in (_DP, _FC):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import docx_pages as DP  # noqa: E402

_W = DP._W
_A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
_R = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
_WP = "{http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing}"
_V = "{urn:schemas-microsoft-com:vml}"
_AR = re.compile("[֐-ࣿיִ-﷿ﹰ-﻿]")
_LAT = re.compile("[A-Za-zÀ-ɏͰ-ϿЀ-ӿ]")
_DIG = re.compile("[0-9٠-٩۰-۹]")

SCALE = 1.5            # بكسلٌ لكلِّ نقطة: A4 ⟵ 893×1263
MAX_PAGES = 60


# ───────────────────────────── الخطوط ─────────────────────────────
_FONT_CACHE = {}
_FILE_CACHE = {}
_RAQM = None


def _raqm():
    global _RAQM
    if _RAQM is None:
        try:
            from PIL import features
            _RAQM = bool(features.check("raqm"))
        except Exception:
            _RAQM = False
    return _RAQM


_SANS_HINT = ("arial", "helvetica", "calibri", "segoe", "tahoma", "verdana",
              "aptos", "sans", "trebuchet", "roboto", "dubai", "cairo", "tajawal")


def _font_path(family, script, bold, italic):
    """(ملفُّ الخطّ، هل العريضُ حقيقيّ) للعائلة المطلوبة أو أقربِ بديل."""
    key = (family or "", script, bold, italic)
    if key in _FILE_CACHE:
        return _FILE_CACHE[key]
    path, real_bold = None, False
    try:
        import font_catalog as FC
        e = FC.find_font(family) if family else None
        if e and not e.get("bundled") and e.get("stand_in"):
            e = FC.find_font(e["stand_in"])
        if e and e.get("files") and (script == "ar" and e.get("script") == "ar"
                                     or script != "ar"):
            w = "bolditalic" if bold and italic else "bold" if bold else \
                "italic" if italic else "regular"
            path = FC.file_for(e, w)
            # الخطُّ المتغيّر (Cairo-Variable) يُعرَّض بمحوره لا برسمٍ مضاعف
            real_bold = bool(bold and path and re.search(
                r"bold|black|variable", os.path.basename(path), re.I))
    except Exception:
        path = None
    if not path:
        sans = any(h in (family or "").lower() for h in _SANS_HINT)
        d_ar = os.path.join(_FC, "arabic")
        if sans:
            path = os.path.join(d_ar, "Tajawal-Bold.ttf" if bold else "Tajawal-Regular.ttf")
            real_bold = bold
        else:
            path = os.path.join(d_ar, "Amiri-Bold.ttf" if bold else "Amiri-Regular.ttf")
            real_bold = bold
    _FILE_CACHE[key] = (path, real_bold)
    return path, real_bold


# ── تغطيةُ الحروف: حرفٌ ليس في الخطّ (◀ ✓ ■ …) يُؤخذ من خطٍّ يحمله ──
_CMAPS = {}


def _cmap(path):
    """مجموعةُ نقاط الترميز في الخطّ (جدول cmap: الصيغة ٤ و١٢) — بلا مكتبة."""
    if path in _CMAPS:
        return _CMAPS[path]
    import struct
    cps = set()
    try:
        with open(path, "rb") as fh:
            data = fh.read()
        if data[:4] == b"ttcf":
            off0 = struct.unpack(">I", data[12:16])[0]
        else:
            off0 = 0
        n = struct.unpack(">H", data[off0 + 4:off0 + 6])[0]
        co = None
        for i in range(n):
            tag, _c, off, _l = struct.unpack(">4sIII", data[off0 + 12 + 16 * i:
                                                           off0 + 28 + 16 * i])
            if tag == b"cmap":
                co = off
        if co is not None:
            nt = struct.unpack(">H", data[co + 2:co + 4])[0]
            for i in range(nt):
                pid, eid, off = struct.unpack(">HHI", data[co + 4 + 8 * i:co + 12 + 8 * i])
                sub = co + off
                fmt = struct.unpack(">H", data[sub:sub + 2])[0]
                if fmt == 4:
                    seg2 = struct.unpack(">H", data[sub + 6:sub + 8])[0]
                    segs = seg2 // 2
                    e0 = sub + 14
                    ends = struct.unpack(">%dH" % segs, data[e0:e0 + seg2])
                    starts = struct.unpack(">%dH" % segs, data[e0 + seg2 + 2:e0 + 2 * seg2 + 2])
                    for a, b in zip(starts, ends):
                        if a != 0xFFFF:
                            cps.update(range(a, b + 1))
                elif fmt == 12:
                    ng = struct.unpack(">I", data[sub + 12:sub + 16])[0]
                    for g in range(ng):
                        a, b, _ = struct.unpack(">III", data[sub + 16 + 12 * g:sub + 28 + 12 * g])
                        if b - a < 200000:
                            cps.update(range(a, b + 1))
    except Exception:
        cps = None
    _CMAPS[path] = cps
    return cps


def _fallbacks():
    if "list" in _CMAPS:
        return _CMAPS["list"]
    out = []
    d_ar = os.path.join(_FC, "arabic")
    d_lat = os.path.join(_FC, "latin")
    for fn in ("Tajawal-Regular.ttf", "Amiri-Regular.ttf", "NotoNaskhArabic-Regular.ttf",
               "Cairo-Variable.ttf"):
        out.append(os.path.join(d_ar, fn))
    for fn in ("WorkSans-Regular.ttf", "IBMPlexSerif-Regular.ttf", "JetBrainsMono-Regular.ttf"):
        out.append(os.path.join(d_lat, fn))
    # خطوطُ النظام: أندرويد (Termux يقرؤها) ولينكس
    import glob
    for pat in ("/system/fonts/NotoSansSymbols*.ttf", "/system/fonts/Roboto-Regular.ttf",
                "/system/fonts/NotoSans-Regular.ttf", "/system/fonts/DroidSans.ttf",
                "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                "/usr/share/fonts/dejavu/DejaVuSans.ttf",
                "/usr/share/fonts/truetype/noto/NotoSansSymbols*-Regular.ttf",
                "/usr/share/fonts/truetype/freefont/FreeSerif.ttf"):
        out.extend(sorted(glob.glob(pat))[:3])
    out = [p for p in out if os.path.isfile(p)]
    _CMAPS["list"] = out
    return out


def _cover(path, text):
    """(ملفٌّ يحمل كلَّ حروف النصّ، النصّ) — وما لا يحمله أيُّ خطٍّ يصير «•»."""
    need = {ord(c) for c in text if not c.isspace() and ord(c) > 0x20 and
            not (0x064B <= ord(c) <= 0x065F) and ord(c) not in (0x200C, 0x200D,
                                                                0x200E, 0x200F)}
    cm = _cmap(path)
    if cm is None or need <= cm:
        return path, text
    for fb in _fallbacks():
        c2 = _cmap(fb)
        if c2 and need <= c2:
            return fb, text
    keep = cm
    return path, "".join(c if ord(c) in keep or c.isspace() or ord(c) not in need
                         else "•" for c in text)


def _pil_font(path, px, bold):
    from PIL import ImageFont
    px = max(4, int(round(px)))
    key = (path, px, bold)
    f = _FONT_CACHE.get(key)
    if f is not None:
        return f
    try:
        if _raqm():
            f = ImageFont.truetype(path, px, layout_engine=ImageFont.Layout.RAQM)
        else:
            f = ImageFont.truetype(path, px)
        if "Variable" in os.path.basename(path):
            try:
                f.set_variation_by_name("Bold" if bold else "Regular")
            except Exception:
                pass
    except Exception:
        f = ImageFont.load_default()
    _FONT_CACHE[key] = f
    return f


_MIRROR = str.maketrans("()[]{}«»", ")(][}{»«")


def _vis(text, rtl):
    """النصُّ كما يُرسم بلا raqm: يُشكَّل ويُعكس هنا."""
    if _raqm() or not rtl:
        return text
    if not _AR.search(text):
        return text.translate(_MIRROR)
    try:
        import arabic_reshaper
        from bidi.algorithm import get_display
        return get_display(arabic_reshaper.reshape(text))
    except Exception:
        return text


def _measure(font, text, rtl):
    try:
        if _raqm():
            return font.getlength(text, direction="rtl" if rtl else "ltr")
        return font.getlength(_vis(text, rtl))
    except Exception:
        return len(text) * getattr(font, "size", 10) * 0.5


# ───────────────────────────── الخصائص ─────────────────────────────
def _val(e, attr="val"):
    return e.get(_W + attr) if e is not None else None


def _color(v, default=None):
    if not v or v == "auto" or not re.fullmatch(r"[0-9A-Fa-f]{6}", v):
        return default
    return tuple(int(v[i:i + 2], 16) for i in (0, 2, 4))


_HL = {"yellow": (255, 255, 0), "green": (0, 255, 0), "cyan": (0, 255, 255),
       "magenta": (255, 0, 255), "blue": (0, 0, 255), "red": (255, 0, 0),
       "darkBlue": (0, 0, 139), "darkCyan": (0, 139, 139), "darkGreen": (0, 100, 0),
       "darkMagenta": (139, 0, 139), "darkRed": (139, 0, 0),
       "darkYellow": (128, 128, 0), "darkGray": (169, 169, 169),
       "lightGray": (211, 211, 211), "black": (0, 0, 0)}


class _Ctx:
    def __init__(self, doc):
        self.doc = doc
        self.S = DP._Styles(doc)
        self.counters = {}
        self.num = {}
        self.abstract = {}
        try:
            np = doc.part.numbering_part.element
            for an in np.findall(_W + "abstractNum"):
                self.abstract[_val(an, "abstractNumId")] = an
            for n in np.findall(_W + "num"):
                aid = _val(n.find(_W + "abstractNumId"))
                self.num[_val(n, "numId")] = (aid, n)
        except Exception:
            pass
        self.theme_minor = "Calibri"
        self.theme_major = "Calibri Light"
        self.theme_cs = "Times New Roman"
        # خطوطُ القالب (theme1.xml): اللاتينيّ، والعربيُّ (script="Arab")
        try:
            for part in doc.part.package.iter_parts():
                if str(part.partname).startswith("/word/theme/"):
                    from lxml import etree
                    t = etree.fromstring(part.blob)
                    for tag, attr in (("minorFont", "theme_minor"),
                                      ("majorFont", "theme_major")):
                        f = t.find(".//" + _A + tag)
                        if f is None:
                            continue
                        lat = f.find(_A + "latin")
                        if lat is not None and lat.get("typeface"):
                            setattr(self, attr, lat.get("typeface"))
                        if tag == "minorFont":
                            cs = f.find(_A + "cs")
                            arab = [x for x in f.findall(_A + "font")
                                    if x.get("script") == "Arab"]
                            name = (cs.get("typeface") if cs is not None else "") or \
                                (arab[0].get("typeface") if arab else "")
                            if name:
                                self.theme_cs = name
                    break
        except Exception:
            pass

    # سلسلةُ عناصر pPr/rPr من الأقرب إلى الأبعد
    def chains(self, p, tbl_style=None):
        ppr = p.find(_W + "pPr")
        sid = _val(ppr.find(_W + "pStyle")) if ppr is not None and \
            ppr.find(_W + "pStyle") is not None else None
        chain = self.S.chain(sid or self.S.default_p)
        if tbl_style:
            own = [st for st in chain if st.get(_W + "styleId") != self.S.default_p
                   and st.get(_W + "default") != "1"]
            rest = [st for st in chain if st not in own]
            chain = own + self.S.chain(tbl_style) + rest
        pprs = [ppr] + [st.find(_W + "pPr") for st in chain] + [self.S.d_ppr]
        rprs = [st.find(_W + "rPr") for st in chain] + [self.S.d_rpr]
        return sid, pprs, rprs


def _first(elems, tag, attr="val"):
    for e in elems:
        if e is None:
            continue
        x = e.find(tag)
        if x is not None:
            return x if attr is None else x.get(_W + attr)
    return None


def _on(elems, tag):
    for e in elems:
        if e is None:
            continue
        x = e.find(tag)
        if x is not None:
            return x.get(_W + "val") not in ("0", "false", "off")
    return False


def _run_style(ctx, rpr, rprs):
    rp = [rpr] + rprs
    f_cs = f_lat = None
    for e in rp:
        if e is None:
            continue
        rf = e.find(_W + "rFonts")
        if rf is None:
            continue
        if f_cs is None:
            f_cs = rf.get(_W + "cs") or (ctx.theme_cs if rf.get(_W + "cstheme") else None)
        if f_lat is None:
            f_lat = rf.get(_W + "ascii") or rf.get(_W + "hAnsi") or (
                (ctx.theme_major if "major" in (rf.get(_W + "asciiTheme") or "")
                 else ctx.theme_minor) if rf.get(_W + "asciiTheme") else None)
    sz = _first(rp, _W + "sz")
    szcs = _first(rp, _W + "szCs") or sz
    b = _on(rp, _W + "b")
    bcs = _first(rp, _W + "bCs", None)
    i = _on(rp, _W + "i")
    col = _color(_first(rp, _W + "color"), (0, 0, 0))
    u = _first(rp, _W + "u")
    hl = _first(rp, _W + "highlight")
    shd = _first(rp, _W + "shd", "fill")
    vert = _first(rp, _W + "vertAlign")
    caps = _on(rp, _W + "caps")
    strike = _on(rp, _W + "strike")
    vanish = _on(rp, _W + "vanish")
    return {
        "f_cs": f_cs or ctx.theme_cs, "f_lat": f_lat or ctx.theme_minor,
        "sz": int(sz or 22) / 2, "szcs": int(szcs or sz or 22) / 2,
        "b": b, "bcs": (bcs.get(_W + "val") not in ("0", "false", "off"))
        if bcs is not None else b,
        "i": i, "color": col, "u": bool(u and u != "none"),
        "hl": _HL.get(hl) if hl else _color(shd), "vert": vert, "caps": caps,
        "strike": strike, "vanish": vanish,
    }


# ───────────────────────────── الأجزاء (tokens) ─────────────────────────────
class Tok:
    __slots__ = ("kind", "text", "font", "rtl", "w", "asc", "desc", "color",
                 "u", "hl", "strike", "synth", "img", "h", "dirc", "px", "lf")

    def __init__(self, kind, text="", font=None, rtl=False, w=0.0, asc=0.0,
                 desc=0.0, color=(0, 0, 0), u=False, hl=None, strike=False,
                 synth=0, img=None, h=0.0, px=0.0):
        self.kind, self.text, self.font, self.rtl, self.w = kind, text, font, rtl, w
        self.asc, self.desc, self.color, self.u, self.hl = asc, desc, color, u, hl
        self.strike, self.synth, self.img, self.h, self.px = strike, synth, img, h, px
        self.dirc = "R" if rtl else ("L" if kind == "img" else "N")
        self.lf = 0.0


def _strong(text):
    for ch in text:
        if _AR.match(ch):
            return "R"
        if _LAT.match(ch):
            return "L"
        if _DIG.match(ch):
            return "D"
    return "N"


def _text_toks(text, st, out, field_val=None):
    if st["vanish"]:
        return
    if st["caps"]:
        text = text.upper()
    # كلماتٌ ومسافات؛ والكلمةُ المختلطةُ تُقسم على حدود العربيّ/غيره
    for part in re.findall(r"\s+|[^\s]+", text):
        if part.isspace():
            ar = False
            size = st["sz"]
            path, rb = _font_path(st["f_lat"], "lat", st["b"], st["i"])
            f = _pil_font(path, size * SCALE, st["b"])
            w = _measure(f, " ", False) * len(part.replace("\t", "    "))
            out.append(Tok("space", " ", f, False, w, color=st["color"],
                           u=st["u"], hl=st["hl"], px=size * SCALE))
            continue
        # الأقواسُ أجزاءٌ مستقلّة: اتّجاهُها يُحسم بزوجها (قاعدةُ N0)
        for seg in re.findall(r"[()\[\]{}«»]|[\u0590-\u08FF\uFB1D-\uFDFF\uFE70-\uFEFF\u064B-\u065F]+|"
                              r"[^()\[\]{}«»\u0590-\u08FF\uFB1D-\uFDFF\uFE70-\uFEFF]+", part):
            ar = bool(_AR.search(seg))
            size = st["szcs"] if ar else st["sz"]
            bold = st["bcs"] if ar else st["b"]
            if st["vert"] in ("superscript", "subscript"):
                size *= 0.65
            path, rb = _font_path(st["f_cs"] if ar else st["f_lat"],
                                  "ar" if ar else "lat", bold, st["i"])
            # حرفٌ لا يحمله الخطّ (◀ ✓ ■ …) ⟵ خطٌّ يحمله، وإلّا «•»
            p2, seg = _cover(path, seg)
            if p2 != path:
                path, rb = p2, False
            f = _pil_font(path, size * SCALE, bold)
            w = _measure(f, seg, ar)
            asc, desc = f.getmetrics() if hasattr(f, "getmetrics") else (size, size * 0.3)
            t = Tok("text", seg, f, ar, w, asc, desc, st["color"], st["u"], st["hl"],
                    st["strike"], synth=(max(1, int(size * SCALE / 28))
                                         if bold and not rb else 0), px=size * SCALE)
            t.dirc = "R" if ar else ("D" if _strong(seg) == "D" else
                                     ("L" if _strong(seg) == "L" else "N"))
            # ارتفاعُ السطر كما يحسبه Word: مقاييسُ الخطّ (typo/hhea) × الحجم —
            # الحسابُ نفسُه المعايَرُ في docx_pages
            fam = st["f_cs"] if ar else st["f_lat"]
            met = _line_factor(fam, bold)
            t.lf = size * SCALE * met
            out.append(t)
            # مقطعٌ متّصلٌ بما قبله بلا مسافة (حدّ عربيّ/لاتينيّ داخل كلمة)
    return


_LF = {}


def _line_factor(family, bold):
    key = (family, bold)
    if key not in _LF:
        try:
            m = DP._metrics(family, bold)
            _LF[key] = (m or {}).get("line") or 1.17
        except Exception:
            _LF[key] = 1.17
    return _LF[key]


def _num_label(ctx, ppr_list, para_text_rtl):
    """نصُّ الترقيم/التعداد وإزاحتُه — أو (None, None)."""
    numpr = _first(ppr_list, _W + "numPr", None)
    if numpr is None:
        return None, None
    nid = _val(numpr.find(_W + "numId"))
    ilvl = int(_val(numpr.find(_W + "ilvl")) or 0)
    if not nid or nid == "0" or nid not in ctx.num:
        return None, None
    aid, num_el = ctx.num[nid]
    an = ctx.abstract.get(aid)
    if an is None:
        return None, None
    lvl = None
    for lv in an.findall(_W + "lvl"):
        if int(_val(lv, "ilvl") or 0) == ilvl:
            lvl = lv
            break
    if lvl is None:
        return None, None
    fmt = _val(lvl.find(_W + "numFmt")) or "decimal"
    txt = _val(lvl.find(_W + "lvlText")) or ""
    start = int(_val(lvl.find(_W + "start")) or 1)
    key = (nid, ilvl)
    c = ctx.counters.get(key, start - 1) + 1
    ctx.counters[key] = c
    for k in list(ctx.counters):
        if k[0] == nid and k[1] > ilvl:
            del ctx.counters[k]
    if fmt == "bullet":
        label = txt if txt and txt.strip() else "•"
        if label in ("", "", "", "o"):
            label = "•" if label != "o" else "◦"
        if ord(label[0]) >= 0xF000:
            label = "•"
    else:
        def fmt_n(n, f):
            if f in ("arabicAbjad", "arabicAlpha"):
                return "أبجدهوزحطيكلمنسعفصقرشتثخذضظغ"[(n - 1) % 28]
            if f == "lowerLetter":
                return chr(96 + (n - 1) % 26 + 1)
            if f == "upperLetter":
                return chr(64 + (n - 1) % 26 + 1)
            if f == "lowerRoman":
                return _roman(n).lower()
            if f == "upperRoman":
                return _roman(n)
            if f in ("hindiNumbers", "arabicNumbers"):
                return str(n).translate(str.maketrans("0123456789", "٠١٢٣٤٥٦٧٨٩"))
            return str(n)
        label = re.sub(r"%(\d)", lambda m: fmt_n(
            ctx.counters.get((nid, int(m.group(1)) - 1), 1) if int(m.group(1)) - 1 != ilvl
            else c, fmt), txt) or "%d." % c
    lppr = lvl.find(_W + "pPr")
    return label, lppr


def _roman(n):
    vals = [(1000, "M"), (900, "CM"), (500, "D"), (400, "CD"), (100, "C"), (90, "XC"),
            (50, "L"), (40, "XL"), (10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I")]
    out = ""
    for v, s in vals:
        while n >= v:
            out += s
            n -= v
    return out


def _twip(v):
    try:
        return int(v) / 20.0
    except (TypeError, ValueError):
        return 0.0


# ───────────────────────────── الفقرة ─────────────────────────────
class Line:
    __slots__ = ("toks", "w", "asc", "desc", "h", "x0", "avail", "last", "rtl",
                 "align", "lead_x", "brk")

    def __init__(self):
        self.toks, self.w, self.asc, self.desc, self.h = [], 0.0, 0.0, 0.0, 0.0
        self.x0, self.avail, self.last, self.rtl, self.align = 0.0, 0.0, False, False, "left"
        self.lead_x = 0.0
        self.brk = False          # فاصلُ صفحةٍ بعد هذا السطر


class Para:
    """فقرةٌ مخطَّطة: أسطرٌ بارتفاعاتها، ومسافاتٌ، وخصائصُ الصفحة."""

    def __init__(self):
        self.lines, self.before, self.after = [], 0.0, 0.0
        self.keep_next = self.keep_lines = self.break_before = False
        self.page_break_after = 0
        self.shd = None
        self.bdr_top = self.bdr_bottom = None
        self.sid = None
        self.contextual = False
        self.box_l = self.box_r = 0.0


def _runs(el, fk=None):
    """(مقطع، نوعُ الحقل) بترتيبها، نزولاً في الروابط والإدراجات والحقول
    البسيطة (fldSimple PAGE ⟵ نصُّه يُستبدل برقم الصفحة)."""
    for ch in el:
        tag = ch.tag
        if tag == _W + "r":
            yield ch, fk
        elif tag in (_W + "hyperlink", _W + "ins", _W + "smartTag", _W + "customXml",
                     _W + "fldSimple", _W + "sdt", _W + "sdtContent", _W + "bdo",
                     _W + "dir"):
            k = fk
            if tag == _W + "fldSimple":
                instr = (ch.get(_W + "instr") or "").strip().split()
                if instr and instr[0].upper() in ("PAGE", "NUMPAGES"):
                    k = instr[0].upper()
            yield from _runs(ch, k)


def layout_para(ctx, p, width, tbl_style=None, field_vals=None, base_rtl=None):
    """فقرةٌ ⟵ Para (أسطرٌ وأجزاؤها بمواضعها النسبيّة)."""
    sid, pprs, rprs = ctx.chains(p, tbl_style)
    para = Para()
    para.sid = sid
    sp_before = _first(pprs, _W + "spacing[@" + _W + "before]", "before")
    sp_after = _first(pprs, _W + "spacing[@" + _W + "after]", "after")
    para.before = _twip(sp_before) if sp_before else 0.0
    para.after = _twip(sp_after) if sp_after else 0.0
    if _on(pprs, _W + "spacing[@" + _W + "beforeAutospacing]") and not sp_before:
        para.before = 14.0
    line_v = _first(pprs, _W + "spacing[@" + _W + "line]", "line")
    rule = _first(pprs, _W + "spacing[@" + _W + "lineRule]", "lineRule") or "auto"
    line_v = int(line_v) if line_v and line_v.lstrip("-").isdigit() else 240
    para.keep_next = _on(pprs, _W + "keepNext")
    para.keep_lines = _on(pprs, _W + "keepLines")
    para.break_before = _on(pprs, _W + "pageBreakBefore")
    para.contextual = _on(pprs, _W + "contextualSpacing")
    rtl = _on(pprs, _W + "bidi") if _first(pprs, _W + "bidi", None) is not None else \
        bool(base_rtl)
    jc = _first(pprs, _W + "jc")
    # الإزاحات (pt)
    ind = {}
    for k in ("left", "right", "start", "end", "firstLine", "hanging"):
        v = _first(pprs, _W + "ind[@" + _W + k + "]", k)
        ind[k] = _twip(v) if v else 0.0
    label, lvl_ppr = _num_label(ctx, pprs, rtl)
    if lvl_ppr is not None:
        li = lvl_ppr.find(_W + "ind")
        if li is not None and p.find(_W + "pPr/" + _W + "ind") is None:
            for k in ("left", "right", "start", "end", "firstLine", "hanging"):
                v = li.get(_W + k)
                if v:
                    ind[k] = _twip(v)
    lead = ind["start"] or ind["left"]
    trail = ind["end"] or ind["right"]
    first = ind["firstLine"] - ind["hanging"]
    # التظليلُ والحدود
    para.shd = _color(_first(pprs, _W + "shd", "fill"))
    bdr = _first(pprs, _W + "pBdr", None)
    if bdr is not None:
        for side, attr in (("top", "bdr_top"), ("bottom", "bdr_bottom")):
            e = bdr.find(_W + side)
            if e is not None and _val(e) not in (None, "nil", "none"):
                setattr(para, attr, (_color(_val(e, "color"), (0, 0, 0)),
                                     max(0.5, int(_val(e, "sz") or 4) / 8)))
    # الأجزاء
    toks = []
    mark_rpr = p.find(_W + "pPr/" + _W + "rPr")
    if label:
        st = _run_style(ctx, mark_rpr, rprs)
        lt = []
        _text_toks(label, st, lt)
        lw = sum(t.w for t in lt)
        hang = max(ind["hanging"], 0) * SCALE
        gap = max(hang - lw, 4 * SCALE)
        for t in lt:
            toks.append(t)
        sp = Tok("space", " ", lt[0].font if lt else None, False, gap, px=st["sz"] * SCALE)
        sp.kind = "tabgap"
        toks.append(sp)
    in_instr = False
    fld_kind = None
    for r, simple in _runs(p):
        if simple:
            fld_kind = simple
        rpr = r.find(_W + "rPr")
        st = _run_style(ctx, rpr, rprs)
        for ch in r:
            tag = ch.tag
            if tag == _W + "fldChar":
                t = ch.get(_W + "fldCharType")
                if t == "begin":
                    in_instr, fld_kind = True, None
                elif t == "separate":
                    in_instr = False
                elif t == "end":
                    in_instr, fld_kind = False, None
                continue
            if tag == _W + "instrText":
                w0 = (ch.text or "").strip().split()
                if w0 and w0[0].upper() in ("PAGE", "NUMPAGES"):
                    fld_kind = w0[0].upper()
                continue
            if in_instr:
                continue
            if tag == _W + "t":
                text = ch.text or ""
                if fld_kind and field_vals:
                    text = str(field_vals.get(fld_kind, text))
                    fld_kind = None
                _text_toks(text, st, toks)
            elif tag == _W + "tab":
                f = toks[-1].font if toks else None
                t = Tok("tab", "\t", f, False, 24 * SCALE, px=st["sz"] * SCALE)
                toks.append(t)
            elif tag in (_W + "br", _W + "cr"):
                if ch.get(_W + "type") == "page":
                    toks.append(Tok("pagebr"))
                else:
                    toks.append(Tok("br"))
            elif tag == _W + "drawing" or tag.endswith("}AlternateContent") or tag == _W + "pict":
                for im, wpt, hpt in _images_in(ctx, ch):
                    if im is None:
                        continue
                    w = min(wpt * SCALE, (width - lead - trail) * SCALE)
                    h = hpt * SCALE * (w / (wpt * SCALE)) if wpt else hpt * SCALE
                    toks.append(Tok("img", "", None, False, w, h, 0, img=im, h=h))
            elif tag == _W + "sym":
                _text_toks("•", st, toks)
    # أسطر
    mark_st = _run_style(ctx, mark_rpr, rprs)
    path, _rb = _font_path(mark_st["f_cs"] if rtl else mark_st["f_lat"],
                           "ar" if rtl else "lat", False, False)
    mfont = _pil_font(path, (mark_st["szcs"] if rtl else mark_st["sz"]) * SCALE, False)
    m_asc, m_desc = mfont.getmetrics() if hasattr(mfont, "getmetrics") else (12, 4)
    met = DP._metrics(mark_st["f_cs"] if rtl else mark_st["f_lat"]) or {}
    mline = (mark_st["szcs"] if rtl else mark_st["sz"]) * (met.get("line") or 1.15) * SCALE

    def line_h(asc, desc, natural):
        if rule == "exact":
            return abs(line_v) / 20 * SCALE
        if rule == "atLeast":
            return max(line_v / 20 * SCALE, natural)
        return natural * line_v / 240

    full_w = max(20.0, width - lead - trail) * SCALE
    if jc in ("center",):
        align = "center"
    elif jc in ("both", "distribute", "thaiDistribute", "lowKashida", "mediumKashida",
                "highKashida"):
        align = "justify"
    elif jc in ("right", "end"):
        align = "left" if rtl else "right"
    else:
        align = "right" if rtl else "left"
    lines = []
    cur = Line()
    first_line = True

    def avail():
        return full_w - (first * SCALE if first_line else 0)

    def push(last=False):
        nonlocal cur, first_line
        # مسافاتٌ في الطرفين لا تُحسب
        while cur.toks and cur.toks[-1].kind == "space":
            cur.w -= cur.toks[-1].w
            cur.toks.pop()
        cur.last = last
        lines.append(cur)
        cur = Line()
        first_line = False

    for t in toks:
        if t.kind in ("br", "pagebr"):
            push(last=True)
            if t.kind == "pagebr":
                para.page_break_after += 1
                lines[-1].last = True
                lines[-1].brk = True
            continue
        if t.kind == "space":
            if not cur.toks:
                continue
            cur.toks.append(t)
            cur.w += t.w
            continue
        if cur.toks and cur.w + t.w > avail() and t.kind not in ("tabgap",):
            # قطعةٌ ملتصقةٌ بما قبلها (بلا مسافة) تنتقل معه
            carry = []
            while cur.toks and cur.toks[-1].kind not in ("space", "tab", "tabgap"):
                carry.insert(0, cur.toks.pop())
            if not cur.toks:
                cur.toks = carry
                carry = []
            cur.w = sum(x.w for x in cur.toks)
            push()
            for c in carry:
                cur.toks.append(c)
                cur.w += c.w
        cur.toks.append(t)
        cur.w += t.w
    push(last=True)
    # مقاييسُ كلِّ سطر
    for ln in lines:
        txt = [t for t in ln.toks if t.kind == "text"]
        imgh = max([t.h for t in ln.toks if t.kind == "img"] + [0])
        if txt:
            big = max(txt, key=lambda t: t.lf)
            nat = big.lf
            # خطُّ الأساس: نسبةُ الصاعد من الخطّ الأكبر في السطر
            ratio = big.asc / float(big.asc + big.desc or 1)
            asc, desc = nat * ratio, nat * (1 - ratio)
        else:
            nat = mline
            ratio = m_asc / float(m_asc + m_desc or 1)
            asc, desc = nat * ratio, nat * (1 - ratio)
        lh = line_h(asc, desc, nat)
        if imgh:
            lh = max(lh, imgh + desc)
            asc = max(asc, imgh)
        ln.asc, ln.desc, ln.h = asc, desc, lh
        ln.rtl = rtl
        ln.align = align
    if not lines:
        ln = Line()
        ln.h = line_h(m_asc, m_desc, mline)
        ratio = m_asc / float(m_asc + m_desc or 1)
        ln.asc, ln.desc = mline * ratio, mline * (1 - ratio)
        lines.append(ln)
    # مواضعُ الأجزاء داخل السطر (بصريّاً)
    for idx, ln in enumerate(lines):
        fi = first * SCALE if idx == 0 else 0.0
        av = full_w - fi
        _place(ln, av, rtl)
        # يسارُ منطقة السطر داخل صندوق الفقرة: الإزاحةُ الأولى في جهة البداية
        ln.lead_x = (lead * SCALE + fi) if not rtl else trail * SCALE
        ln.x0 = _align_x(ln, av, align)
    para.lines = lines
    para.rtl = rtl
    para.lead, para.trail, para.first = lead, trail, first
    return para


def _place(ln, avail, base_rtl):
    """رتّب الأجزاء بصريّاً (خوارزميّةُ اتّجاهٍ مبسّطة على مستوى الكلمة)."""
    toks = [t for t in ln.toks if t.kind != "pagebr"]
    if not toks:
        ln.toks = []
        ln.w = 0.0
        return
    base = "R" if base_rtl else "L"
    # ١ الأنواع: R عربيّ، L لاتينيّ، D أرقام، N محايد
    types = []
    for t in toks:
        if t.kind == "text":
            types.append(t.dirc if t.dirc in ("R", "L", "D") else "N")
        else:
            types.append("N")
    # ٢ (W7) رقمٌ قبله لاتينيٌّ قويّ ⟵ لاتينيّ
    last = base
    for i, ty in enumerate(types):
        if ty in ("R", "L"):
            last = ty
        elif ty == "D" and last == "L":
            types[i] = "L"

    def strong(ty):
        return "R" if ty in ("R", "D") else ty
    # ٣ (N0) الأقواس: زوجاها باتّجاه الفقرة، إلّا إن كان داخلُها معاكساً كلُّه
    # وقبلها معاكسٌ أيضاً
    opens, pairs = [], []
    for i, t in enumerate(toks):
        if t.kind != "text":
            continue
        if t.text in ("(", "[", "{", "«"):
            opens.append(i)
        elif t.text in (")", "]", "}", "»") and opens:
            pairs.append((opens.pop(), i))
    for a, b in pairs:
        inside = {strong(types[k]) for k in range(a + 1, b) if types[k] != "N"}
        d = base
        if inside and base not in inside:
            prev = next((strong(types[k]) for k in range(a - 1, -1, -1)
                         if types[k] != "N"), base)
            if prev != base:
                d = prev
        types[a] = types[b] = d
    # ٤ (N1) المحايدُ بين قويّين متماثلين يأخذهما (الأرقامُ تُعدّ R)، وإلّا الفقرة
    n = len(types)
    res = list(types)
    i = 0
    while i < n:
        if res[i] != "N":
            i += 1
            continue
        j = i
        while j < n and res[j] == "N":
            j += 1
        left = strong(res[i - 1]) if i > 0 else base
        right = strong(res[j]) if j < n else base
        d = left if left == right else base
        for k in range(i, j):
            res[k] = d
        i = j
    # ٥ المحايدُ المحسومُ R يُرسم RTL — فتنعكس الأقواس كما في Word
    for t, ty in zip(toks, res):
        if t.kind == "text" and not _AR.search(t.text):
            t.rtl = ty == "R" and t.dirc not in ("L", "D")
    res = ["L" if ty == "D" else ty for ty in res]
    # مجموعاتٌ متتالية بنفس الاتّجاه
    groups = []
    for t, d in zip(toks, res):
        if groups and groups[-1][0] == d:
            groups[-1][1].append(t)
        else:
            groups.append([d, [t]])
    vis = []
    if base == "R":
        for d, g in reversed(groups):
            vis.extend(g if d == "L" else list(reversed(g)))
        # تسلسلٌ عربيٌّ داخل R يُعكس كاملاً (من اليمين) — ما سبق رتّبه من اليسار
    else:
        for d, g in groups:
            vis.extend(list(reversed(g)) if d == "R" else g)
    ln.toks = vis
    ln.w = sum(t.w for t in vis)


def _align_x(ln, avail, align):
    extra = max(0.0, avail - ln.w)
    if align == "center":
        return extra / 2
    if align == "right":
        return extra
    if align == "justify":
        if ln.last:
            return extra if ln.rtl else 0.0
        spaces = [t for t in ln.toks if t.kind == "space"]
        if spaces and extra > 0:
            add = extra / len(spaces)
            if add < avail * 0.25:
                for t in spaces:
                    t.w += add
                ln.w = sum(t.w for t in ln.toks)
                return 0.0
        return extra if ln.rtl else 0.0
    return 0.0


def _images_in(ctx, el):
    """[(PIL.Image، عرض pt، ارتفاع pt)] للصور داخل عنصر رسم."""
    from PIL import Image
    out = []
    for container in list(el.iter(_WP + "inline")) + list(el.iter(_WP + "anchor")):
        ext = container.find(_WP + "extent")
        try:
            wpt = int(ext.get("cx")) / 12700
            hpt = int(ext.get("cy")) / 12700
        except Exception:
            continue
        im = None
        for b in container.iter(_A + "blip"):
            rid = b.get(_R + "embed")
            try:
                part = ctx.doc.part.related_parts[rid]
                im = Image.open(io.BytesIO(part.blob))
                im.load()
                im = im.convert("RGBA")
            except Exception:
                im = None
            break
        if im is None:
            # شكلٌ أو مربّعُ نصٍّ بلا صورة ⟵ لا يُرسم
            continue
        out.append((im, wpt, hpt))
    if not out:
        for im_el in el.iter(_V + "imagedata"):
            rid = im_el.get(_R + "id")
            try:
                part = ctx.doc.part.related_parts[rid]
                im = Image.open(io.BytesIO(part.blob))
                im.load()
                out.append((im.convert("RGBA"), im.width * 0.75, im.height * 0.75))
            except Exception:
                pass
    return out


# ───────────────────────────── الرسم ─────────────────────────────
def draw_line(img, d, ln, box_x, top):
    """سطرٌ عند (box_x: يسارُ صندوق الفقرة، top) بالبكسل."""
    base = top + ln.asc + max(0.0, (ln.h - ln.asc - ln.desc)) * 0.0
    x = box_x + ln.x0
    for t in ln.toks:
        if t.kind == "text":
            if t.hl:
                d.rectangle([x, base - t.asc, x + t.w, base + t.desc], fill=t.hl)
            try:
                if _raqm():
                    d.text((x, base), t.text, font=t.font, fill=t.color, anchor="ls",
                           direction="rtl" if t.rtl else "ltr",
                           stroke_width=t.synth, stroke_fill=t.color if t.synth else None)
                else:
                    d.text((x, base), _vis(t.text, t.rtl), font=t.font, fill=t.color,
                           anchor="ls", stroke_width=t.synth,
                           stroke_fill=t.color if t.synth else None)
            except Exception:
                pass
            if t.u:
                d.line([x, base + max(2, t.px * 0.08), x + t.w,
                        base + max(2, t.px * 0.08)], fill=t.color, width=max(1, int(t.px / 16)))
            if t.strike:
                d.line([x, base - t.asc * 0.3, x + t.w, base - t.asc * 0.3],
                       fill=t.color, width=max(1, int(t.px / 16)))
        elif t.kind == "space":
            if t.hl:
                d.rectangle([x, base - (t.px * 0.8), x + t.w, base + t.px * 0.22], fill=t.hl)
            if t.u:
                d.line([x, base + max(2, t.px * 0.08), x + t.w, base + max(2, t.px * 0.08)],
                       fill=t.color, width=max(1, int(t.px / 16)))
        elif t.kind == "img" and t.img is not None:
            try:
                im = t.img.resize((max(1, int(t.w)), max(1, int(t.h))))
                img.paste(im, (int(x), int(base - t.h)), im)
            except Exception:
                pass
        x += t.w


# ───────────────────────────── الجداول ─────────────────────────────
def _border(e):
    if e is None:
        return None
    v = _val(e)
    if v in (None, "nil", "none"):
        return False
    return (_color(_val(e, "color"), (0, 0, 0)), max(0.5, int(_val(e, "sz") or 4) / 8))


class Row:
    def __init__(self):
        self.h = 0.0
        self.cells = []        # (x_px, w_px, items, shd, borders, valign, vmerge)
        self.header = False
        self.cant_split = False


def layout_table(ctx, tbl, width, base_rtl=False):
    """جدولٌ ⟵ قائمةُ صفوف (Row) بعرض المحتوى width (pt)."""
    tpr = tbl.find(_W + "tblPr")
    ts = _val(tpr.find(_W + "tblStyle")) if tpr is not None and \
        tpr.find(_W + "tblStyle") is not None else None
    style_chain = ctx.S.chain(ts) if ts else []
    style_tprs = [st.find(_W + "tblPr") for st in style_chain]
    rtl = tpr is not None and tpr.find(_W + "bidiVisual") is not None and \
        _val(tpr.find(_W + "bidiVisual")) not in ("0", "false")
    grid = [_twip(g.get(_W + "w")) for g in tbl.findall(_W + "tblGrid/" + _W + "gridCol")]
    rows_el = tbl.findall(_W + "tr")
    ncol = len(grid) or max((sum(int(_val(tc.find(_W + "tcPr/" + _W + "gridSpan")) or 1)
                                 for tc in tr.findall(_W + "tc")) for tr in rows_el),
                                default=1)
    if not grid or sum(grid) <= 0:
        grid = [width / max(1, ncol)] * ncol
    total = sum(grid)
    k = min(1.0, width / total) if total else 1.0
    grid = [g * k for g in grid]
    total = sum(grid)
    jc = _val(tpr.find(_W + "jc")) if tpr is not None and tpr.find(_W + "jc") is not None else None
    if jc == "center":
        off = (width - total) / 2
    elif (jc in ("right", "end") and not rtl) or (rtl and jc in (None, "left", "start")):
        off = width - total
    else:
        off = 0.0
    # الحدود: الجدول ⟵ نمطُه
    def tbl_border(side):
        for e in [tpr] + style_tprs:
            if e is None:
                continue
            b = e.find(_W + "tblBorders/" + _W + side)
            if b is not None:
                return _border(b)
        return None
    tb = {s: tbl_border(s) for s in ("top", "bottom", "left", "right", "start", "end",
                                     "insideH", "insideV")}
    # الصفُّ الأوّل من نمط الجدول (tblStylePr firstRow)
    first_row_shd, first_row_bold, first_row_color = None, False, None
    look = tpr.find(_W + "tblLook") if tpr is not None else None
    use_first = look is None or _val(look, "firstRow") not in ("0", "false")
    if use_first:
        for st in style_chain:
            for sp in st.findall(_W + "tblStylePr"):
                if _val(sp, "type") == "firstRow":
                    s = sp.find(_W + "tcPr/" + _W + "shd")
                    first_row_shd = first_row_shd or _color(_val(s, "fill") if s is not None else None)
                    rp = sp.find(_W + "rPr")
                    if rp is not None:
                        first_row_bold = first_row_bold or rp.find(_W + "b") is not None
                        c = rp.find(_W + "color")
                        first_row_color = first_row_color or _color(_val(c))
    # هوامشُ الخليّة الافتراضيّة
    mar_l = mar_r = 5.4
    for e in [tpr] + style_tprs:
        if e is None:
            continue
        cm = e.find(_W + "tblCellMar")
        if cm is not None:
            for side, var in (("left", "l"), ("start", "l"), ("right", "r"), ("end", "r")):
                x = cm.find(_W + side)
                if x is not None:
                    if var == "l":
                        mar_l = _twip(_val(x, "w"))
                    else:
                        mar_r = _twip(_val(x, "w"))
            break
    out = []
    for ri, tr in enumerate(rows_el):
        row = Row()
        trpr = tr.find(_W + "trPr")
        row.header = trpr is not None and trpr.find(_W + "tblHeader") is not None
        row.cant_split = trpr is not None and trpr.find(_W + "cantSplit") is not None
        min_h, exact = 0.0, False
        if trpr is not None and trpr.find(_W + "trHeight") is not None:
            th = trpr.find(_W + "trHeight")
            min_h = _twip(_val(th))
            exact = _val(th, "hRule") == "exact"
        col = 0
        gb = trpr.find(_W + "gridBefore") if trpr is not None else None
        if gb is not None:
            col += int(_val(gb) or 0)
        for tc in tr.findall(_W + "tc"):
            tcpr = tc.find(_W + "tcPr")
            span = int(_val(tcpr.find(_W + "gridSpan")) or 1) if tcpr is not None and \
                tcpr.find(_W + "gridSpan") is not None else 1
            cw = sum(grid[col:col + span]) or (width / max(1, ncol))
            cx = off + sum(grid[:col])
            if rtl:
                cx = off + total - sum(grid[:col]) - cw
            vm = tcpr.find(_W + "vMerge") if tcpr is not None else None
            vmerge = None
            if vm is not None:
                vmerge = "restart" if _val(vm) == "restart" else "continue"
            shd = None
            if tcpr is not None and tcpr.find(_W + "shd") is not None:
                shd = _color(_val(tcpr.find(_W + "shd"), "fill"))
            if shd is None and ri == 0 and first_row_shd:
                shd = first_row_shd
            borders = {}
            cb = tcpr.find(_W + "tcBorders") if tcpr is not None else None
            for side in ("top", "bottom", "left", "right", "start", "end"):
                b = _border(cb.find(_W + side)) if cb is not None else None
                borders[side] = b
            va = _val(tcpr.find(_W + "vAlign")) if tcpr is not None and \
                tcpr.find(_W + "vAlign") is not None else "top"
            inner = cw - mar_l - mar_r
            items = layout_blocks(ctx, list(tc), max(10.0, inner), tbl_style=ts,
                                  base_rtl=rtl, force_bold=(ri == 0 and first_row_bold),
                                  force_color=(first_row_color if ri == 0 else None))
            h = sum(_item_h(it) for it in items)
            row.cells.append({"x": cx * SCALE, "w": cw * SCALE, "items": items,
                              "shd": shd, "b": borders, "va": va, "vm": vmerge,
                              "ml": mar_l * SCALE, "mr": mar_r * SCALE, "h": h,
                              "col": col, "span": span})
            col += span
        content_h = max([c["h"] for c in row.cells if c["vm"] != "continue"] + [0]) + 2
        row.h = (min_h * SCALE if exact else max(min_h * SCALE, content_h))
        out.append(row)
    return {"rows": out, "tb": tb, "rtl": rtl, "x_off": off * SCALE, "w": total * SCALE}


def _item_h(it):
    kind = it[0]
    if kind == "line":
        return it[2] + it[1].h + it[3]
    if kind == "table":
        return sum(r.h for r in it[1]["rows"])
    if kind == "space":
        return it[1]
    return 0.0


def draw_items(img, d, items, x, y):
    """عناصرُ مسطّحة (أسطرٌ وجداول) عموديّاً من (x, y)."""
    for it in items:
        if it[0] == "line":
            _, ln, before, after, para, idx = it
            y += before
            _draw_para_deco(d, para, ln, idx, x, y)
            draw_line(img, d, ln, x + ln.lead_x, y)
            y += ln.h + after
        elif it[0] == "table":
            for row in it[1]["rows"]:
                draw_row(img, d, it[1], row, x, y)
                y += row.h
        elif it[0] == "space":
            y += it[1]
    return y


def _draw_para_deco(d, para, ln, idx, x, y):
    if para is None:
        return
    x0 = x + para.lead * SCALE if not para.rtl else x + para.trail * SCALE
    right = x + para.box_w - (para.trail * SCALE if not para.rtl else para.lead * SCALE)
    if para.shd:
        d.rectangle([x0, y, right, y + ln.h], fill=para.shd)
    if para.bdr_top and idx == 0:
        c, wpt = para.bdr_top
        d.line([x0, y - 1, right, y - 1], fill=c, width=max(1, int(wpt * SCALE)))
    if para.bdr_bottom and idx == len(para.lines) - 1:
        c, wpt = para.bdr_bottom
        d.line([x0, y + ln.h + 2, right, y + ln.h + 2], fill=c,
               width=max(1, int(wpt * SCALE)))


def draw_row(img, d, tbl, row, x, y):
    tb = tbl["tb"]
    for c in row.cells:
        cx = x + c["x"]
        cw = c["w"]
        h = row.h
        if c["shd"] and c["vm"] != "continue":
            d.rectangle([cx, y, cx + cw, y + h], fill=c["shd"])
        elif c["shd"]:
            d.rectangle([cx, y, cx + cw, y + h], fill=c["shd"])
        if c["vm"] != "continue":
            ch = c["h"]
            top = y
            if c["va"] == "center":
                top = y + max(0.0, (h - ch) / 2)
            elif c["va"] == "bottom":
                top = y + max(0.0, h - ch)
            draw_items(img, d, c["items"], cx + c["ml"], top + 1)
        b = c["b"]
        for side, (x1, y1, x2, y2) in (("top", (cx, y, cx + cw, y)),
                                       ("bottom", (cx, y + h, cx + cw, y + h)),
                                       ("left", (cx, y, cx, y + h)),
                                       ("right", (cx + cw, y, cx + cw, y + h))):
            v = b.get(side)
            if v is None and side in ("left", "right"):
                v = b.get("start" if (side == "left") != tbl["rtl"] else "end")
            if v is None:
                # حدودُ الجدول: الخارجيّةُ أو الداخليّة
                if side in ("top", "bottom"):
                    v = tb.get("insideH")
                    if v is None or v is False:
                        v = tb.get(side) if v is None else v
                else:
                    v = tb.get("insideV")
                    if v is None:
                        v = tb.get(side) or tb.get("start" if side == "left" else "end")
            if side == "top" and c["vm"] == "continue":
                continue
            if v:
                col, wpt = v
                d.line([x1, y1, x2, y2], fill=col, width=max(1, int(round(wpt * SCALE))))


# ───────────────────────────── الكتل ─────────────────────────────
def layout_blocks(ctx, elements, width, tbl_style=None, base_rtl=False,
                  force_bold=False, force_color=None, field_vals=None):
    """عناصرُ الجسم/الخليّة ⟵ قائمةٌ مسطّحة:
         ("line", Line, قبل، بعد، Para، رقمُ السطر)
         ("table", جدول)
         ("break",)   فاصلُ صفحة
    """
    items = []
    prev_para = None
    for el in elements:
        tag = el.tag
        if tag in (_W + "sdt",):
            c = el.find(_W + "sdtContent")
            if c is not None:
                items.extend(layout_blocks(ctx, list(c), width, tbl_style, base_rtl,
                                           force_bold, force_color, field_vals))
            continue
        if tag == _W + "p":
            para = layout_para(ctx, el, width, tbl_style, field_vals, base_rtl)
            para.box_w = width * SCALE
            if force_bold or force_color:
                for ln in para.lines:
                    for t in ln.toks:
                        if t.kind == "text":
                            if force_bold and not t.synth:
                                t.synth = max(1, int(t.px / 28))
                            if force_color:
                                t.color = force_color
            if para.break_before:
                items.append(("break",))
            before = para.before
            if prev_para is not None and para.contextual and prev_para.sid == para.sid:
                before = 0.0
                # «بعد» السابقة أيضاً
                for j in range(len(items) - 1, -1, -1):
                    if items[j][0] == "line" and items[j][4] is prev_para:
                        it = items[j]
                        items[j] = (it[0], it[1], it[2], 0.0, it[4], it[5], *it[6:])
                        break
            n = len(para.lines)
            for i, ln in enumerate(para.lines):
                b = before * SCALE if i == 0 else 0.0
                a = para.after * SCALE if i == n - 1 else 0.0
                items.append(("line", ln, b, a, para, i))
                if ln.brk:
                    items.append(("break",))
            # نصٌّ في مربّعات النصّ (لا يُفقد)
            for tx in el.iter(_W + "txbxContent"):
                items.extend(layout_blocks(ctx, list(tx), width, tbl_style, base_rtl,
                                           force_bold, force_color, field_vals))
            ppr = el.find(_W + "pPr")
            if ppr is not None and ppr.find(_W + "sectPr") is not None:
                tp = ppr.find(_W + "sectPr/" + _W + "type")
                if tp is None or _val(tp) != "continuous":
                    items.append(("break",))
            prev_para = para
        elif tag == _W + "tbl":
            items.append(("table", layout_table(ctx, el, width, base_rtl)))
            prev_para = None
    return items


# ───────────────────────────── التصفيح ─────────────────────────────
def _paginate(items, height):
    """[[(item, y)] لكلِّ صفحة] — مع «ابقَ مع التالي» والأرامل/اليتامى."""
    pages = [[]]
    y = 0.0

    def new_page():
        nonlocal y
        pages.append([])
        y = 0.0

    i = 0
    n = len(items)
    while i < n:
        it = items[i]
        kind = it[0]
        if kind == "break":
            if pages[-1]:
                new_page()
            i += 1
            continue
        if kind == "table":
            tbl = it[1]
            hdr = [r for r in tbl["rows"] if r.header]
            for r in tbl["rows"]:
                if y and y + r.h > height:
                    new_page()
                    if hdr and not r.header:
                        sub = dict(tbl)
                        sub["rows"] = hdr
                        pages[-1].append((("table", sub), y))
                        y += sum(h.h for h in hdr)
                sub = dict(tbl)
                sub["rows"] = [r]
                pages[-1].append((("table", sub), y))
                y += r.h
            i += 1
            continue
        # سطر
        _, ln, before, after, para, idx = it
        if y == 0:
            before = 0.0
        need = before + ln.h
        # «ابقَ مع التالي»: سلسلةُ الفقرات المتتالية التي تحمله كلُّها (عناوينُ
        # متتالية) تبقى معاً ومع أوّل سطرٍ ممّا بعدها — كما يفعل Word
        if idx == 0 and para is not None:
            block = sum(l.h for l in para.lines) + before
            if para.keep_next and i + len(para.lines) < n:
                j = i + len(para.lines)
                while j < n:
                    nx = items[j]
                    if nx[0] == "line":
                        np_ = nx[4]
                        if np_ is not None and np_.keep_next and nx[5] == 0:
                            block += nx[2] + sum(l.h for l in np_.lines) + np_.after
                            j += len(np_.lines)
                            continue
                        block += nx[2] + nx[1].h
                    elif nx[0] == "table" and nx[1]["rows"]:
                        block += nx[1]["rows"][0].h
                    break
                if y and y + block > height and block < height:
                    new_page()
                    before = 0.0
                    need = ln.h
            elif para.keep_lines and y and y + block > height and block < height:
                new_page()
                before = 0.0
                need = ln.h
            elif len(para.lines) >= 2 and y and y + before + ln.h + para.lines[1].h > height:
                # يتيم: لا سطرَ وحيداً في أسفل الصفحة
                new_page()
                before = 0.0
                need = ln.h
        if para is not None and idx == len(para.lines) - 2 and len(para.lines) >= 3 and y:
            # أرملة: لا سطرَ أخيراً وحيداً في أعلى التالية
            if y + ln.h <= height and y + ln.h + para.lines[-1].h > height:
                new_page()
                before = 0.0
                need = ln.h
        if y and y + need > height:
            new_page()
            before = 0.0
        pages[-1].append((("line", ln, before, after, para, idx), y))
        y += before + ln.h + after
        i += 1
    if len(pages) > 1 and not pages[-1]:
        pages.pop()
    return pages


def _hf_part(sec, kind, first):
    try:
        if first and sec.different_first_page_header_footer:
            part = sec.first_page_header if kind == "h" else sec.first_page_footer
        else:
            part = sec.header if kind == "h" else sec.footer
        if part.is_linked_to_previous and part._element is None:
            return None
        return part._element
    except Exception:
        return None


def render_docx(path, max_pages=MAX_PAGES):
    from PIL import Image, ImageDraw
    import docx
    doc = docx.Document(path)
    ctx = _Ctx(doc)
    sec = doc.sections[-1]
    pw = (sec.page_width or 7772400) / 12700
    ph = (sec.page_height or 10058400) / 12700

    def m(v, dflt):
        return (v if v is not None else dflt) / 12700
    lm, rm = m(sec.left_margin, 914400), m(sec.right_margin, 914400)
    tm, bm = m(sec.top_margin, 914400), m(sec.bottom_margin, 914400)
    hd, fd = m(sec.header_distance, 457200), m(sec.footer_distance, 457200)
    width = pw - lm - rm
    height = ph - tm - bm
    items = layout_blocks(ctx, list(doc.element.body), width, base_rtl=False)
    pages = _paginate(items, height * SCALE)[:max_pages]
    total = len(pages)
    W, H = int(pw * SCALE), int(ph * SCALE)
    out = []
    for pi, page in enumerate(pages):
        img = Image.new("RGB", (W, H), (255, 255, 255))
        d = ImageDraw.Draw(img)
        x = lm * SCALE
        for it, y in page:
            draw_items(img, d, [it], x, tm * SCALE + y)
        # الترويسةُ والتذييل
        fv = {"PAGE": pi + 1, "NUMPAGES": total}
        for kind in ("h", "f"):
            el = _hf_part(sec, kind, pi == 0)
            if el is None:
                continue
            try:
                ctx.counters = {}
                its = layout_blocks(ctx, list(el), width, field_vals=fv)
                hgt = sum(_item_h(t) for t in its)
                if kind == "h":
                    y0 = hd * SCALE
                else:
                    y0 = H - fd * SCALE - hgt
                draw_items(img, d, its, x, y0)
            except Exception:
                pass
        out.append(img)
    return out
