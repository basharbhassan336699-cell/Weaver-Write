"""
pptx_design.py — تصميمٌ احترافيٌّ للعروض (working module)
==========================================================
قِيس على عرضٍ حقيقيٍّ من هاتف المستخدم (٢١ شريحة، طلب ١٦):
  · القالبُ الوحيدُ في build_pptx: عنوانٌ ونقاطٌ بحجم ١٨ في زاوية الشريحة،
    وثلثاها فارغ؛ والفواصلُ ذهبيّةٌ بسطرٍ واحد.
  · الغلافُ والختامُ يُضافان دائماً — فلا يملك النموذجُ عددَ الشرائح.
  · لا أشكال: كتب النموذجُ سكربتاً بنفسه ووضع المربّعات والدوائر في شريحتين
    منفصلتين في الآخر.

هنا نظامُ تصميمٍ بأشكال PowerPoint الأصليّة (قابلةٌ للتعديل كلُّها):
  cover · section · points · image_text · cards · circles · images · steps ·
  stats · quote · table · chart · closing
العربيُّ من اليمين (والترتيبُ من اليمين: البطاقةُ الأولى يميناً)، والإنجليزيُّ
من اليسار — لكلِّ سطرٍ اتّجاهُه من نصّه. الألوانُ من القوالب الـ٢١
(themes.json). وأطرُ الصور مربّعةً ودائريّةً داخل الشرائح نفسِها: تُملأ من
PowerPoint (تعبئة الشكل ⟵ صورة) أو بـfill_frame.

الحجمُ يُقدَّر من طول النصّ ومساحته (لا قياسَ للخطّ في python-pptx)، والحدُّ
الأدنى مقروءٌ على الشاشة.
"""
from __future__ import annotations

import json
import math
import os
import re

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.dml import MSO_LINE_DASH_STYLE
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.oxml.ns import qn
from pptx.util import Emu, Inches, Pt

_HERE = os.path.dirname(os.path.abspath(__file__))
_THEMES = os.path.join(os.path.dirname(_HERE), "themes", "themes.json")
FRAME_NAME = "Weaver Image Frame"

W_IN, H_IN = 13.333, 7.5
M = 0.6                                  # الهامش
_AR = re.compile(r"[؀-ۿݐ-ݿࢠ-ࣿﭐ-﷿ﹰ-﻿]")
_AR_DIGITS = str.maketrans("0123456789", "٠١٢٣٤٥٦٧٨٩")


# ─────────────────────────── ألوان ───────────────────────────
def _hex(c):
    return str(c or "000000").lstrip("#")[:6].upper()


def _mix(a, b, t):
    """لونٌ بين a وb (t=0 ⟵ a، t=1 ⟵ b)."""
    a, b = _hex(a), _hex(b)
    ca = [int(a[i:i + 2], 16) for i in (0, 2, 4)]
    cb = [int(b[i:i + 2], 16) for i in (0, 2, 4)]
    return "".join("%02X" % round(x + (y - x) * t) for x, y in zip(ca, cb))


def _lum(c):
    c = _hex(c)
    r, g, b = (int(c[i:i + 2], 16) / 255 for i in (0, 2, 4))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def load_theme(theme=None):
    """قالبٌ بالاسم، أو بوصفٍ حرّ («رسمي»، «تقني»…)، أو بلون (#1B2A4A)."""
    with open(_THEMES, encoding="utf-8") as f:
        themes = json.load(f)["themes"]
    tid = theme if theme in themes else None
    if tid is None and theme:
        cand = str(theme).lstrip("#")
        if len(cand) == 6 and all(ch in "0123456789abcdefABCDEF" for ch in cand):
            try:
                import sys
                if _HERE not in sys.path:
                    sys.path.insert(0, _HERE)
                from palette_generator import custom_theme
                t = custom_theme(cand)
                t.setdefault("bg_title", t.get("primary"))
                t.setdefault("text_on_dark", "FFFFFF")
                return _norm_theme(t, "custom")
            except Exception:
                pass
        try:
            import sys
            if _HERE not in sys.path:
                sys.path.insert(0, _HERE)
            from html_deck_generator import pick_theme
            tid = pick_theme(str(theme), themes)
        except Exception:
            tid = None
    return _norm_theme(themes.get(tid or "academic_navy"), tid or "academic_navy")


def _norm_theme(t, tid):
    t = dict(t)
    for k, d in (("primary", "1B2A4A"), ("accent", "C8A04A"), ("bg", "FFFFFF"),
                 ("text", "222A38"), ("text_on_dark", "FFFFFF")):
        t[k] = _hex(t.get(k) or d)
    t["bg_title"] = _hex(t.get("bg_title") or t["primary"])
    t["dark"] = _lum(t["bg"]) < 0.45
    # بطاقة: بيضاءُ على خلفيّةٍ فاتحة، وأفتحُ قليلاً على الداكنة
    t["card"] = _mix(t["bg"], "FFFFFF", 0.08) if t["dark"] else "FFFFFF"
    t["line"] = _mix(t["bg"], t["text"], 0.18)
    t["muted"] = _mix(t["text"], t["bg"], 0.45)
    t["soft"] = _mix(t["primary"], t["bg"], 0.88)       # تعبئةٌ خفيفة
    # لونٌ يُقرأ على الخلفيّة: primary إن تباين، وإلّا النصّ
    t["title_c"] = t["primary"] if abs(_lum(t["primary"]) - _lum(t["bg"])) > 0.35 \
        else t["text"]
    t["id"] = tid
    return t


# ─────────────────────────── نصّ ───────────────────────────
def is_rtl(text, default=True):
    t = str(text or "")
    letters = [c for c in t if c.isalpha()]
    if not letters:
        return default
    return len(_AR.findall(t)) / len(letters) >= 0.4


def num(n, ar):
    s = str(n)
    return s.translate(_AR_DIGITS) if ar else s


def _em(ch):
    """عرضُ الحرف تقديراً بوحدة em. قِيس: «ADHD» انكسرت سطرين حين قُدِّر كلُّ
    حرفٍ ٠٫٥٢ — والحروفُ اللاتينيّةُ الكبيرةُ العريضةُ أعرضُ من ذلك."""
    if ch == " ":
        return 0.28
    if "A" <= ch <= "Z" or ch in "MW%&@":
        return 0.8                 # قِيس: بـ٠٫٧٢ بقيت «ADHD» تنكسر بخطٍّ بديلٍ عريض
    if ch.isdigit():
        return 0.58
    if _AR.match(ch):
        return 0.5
    return 0.52


def _lines(t, w_pt, pt, bold):
    """أسطرُ نصٍّ بعرضٍ ما، بلفّ الكلمات (كلمةٌ أطولُ من السطر تُعدّ سطراً)."""
    k = 1.12 if bold else 1.0
    n, cur = 1, 0.0
    for word in str(t).split(" "):
        ww = sum(_em(c) for c in word) * pt * k
        if ww > w_pt:
            return None                        # كلمةٌ لا تتّسع ⟵ الحجمُ أكبر
        add = ww + (0.28 * pt if cur else 0)
        if cur + add > w_pt:
            n += 1
            cur = ww
        else:
            cur += add
    return n


def fit(texts, w_in, h_in, max_pt, min_pt, spacing=1.3, bold=False):
    """أكبرُ حجمٍ يتّسع فيه النصُّ: بلا كلمةٍ مكسورة، وأسطرُه في الارتفاع."""
    texts = [str(t or "") for t in (texts if isinstance(texts, (list, tuple))
                                     else [texts])]
    w_pt, h_pt = w_in * 72 * 0.94, h_in * 72
    for pt in range(int(max_pt), int(min_pt) - 1, -1):
        total = 0
        for t in texts:
            n = _lines(t, w_pt, pt, bold)
            if n is None:
                total = None
                break
            total += n
        if total is not None and total * pt * spacing <= h_pt:
            return pt
    return min_pt


class Deck:
    def __init__(self, theme=None, lang="ar", font_ar=None, font_en=None,
                 title="", prs=None):
        self.t = load_theme(theme)
        self.lang = lang
        self.ar = lang == "ar"
        self.fa = font_ar or "Kufyan Arabic Regular"
        self.fe = font_en or font_ar or "Georgia"
        self.title = title
        if prs is None:                  # عرضٌ جديد — أو عرضٌ قائمٌ تُضاف إليه
            prs = Presentation()
            prs.slide_width = Inches(W_IN)
            prs.slide_height = Inches(H_IN)
        self.prs = prs
        lay = self.prs.slide_layouts
        self.blank = next((l for l in lay if l.name.strip().lower() == "blank"),
                          lay[6])

    # ── أدوات ──
    def slide(self, bg):
        s = self.prs.slides.add_slide(self.blank)
        f = s.background.fill
        f.solid()
        f.fore_color.rgb = RGBColor.from_string(_hex(bg))
        return s

    def X(self, x, w):
        """موضعٌ أفقيٌّ مرآة للعربيّ: x من البداية (يمينٌ في العربيّ)."""
        return (W_IN - x - w) if self.ar else x

    def shape(self, s, kind, x, y, w, h, fill=None, line=None, lw=1.0,
              dash=False, alpha=None, radius=None, name=None):
        sh = s.shapes.add_shape(kind, Inches(x), Inches(y), Inches(w), Inches(h))
        sh.shadow.inherit = False
        if fill:
            sh.fill.solid()
            sh.fill.fore_color.rgb = RGBColor.from_string(_hex(fill))
            if alpha is not None:
                clr = sh.fill._xPr.find(qn("a:solidFill")).find(qn("a:srgbClr"))
                a = clr.makeelement(qn("a:alpha"), {"val": str(int(alpha * 100000))})
                clr.append(a)
        else:
            sh.fill.background()
        if line:
            sh.line.color.rgb = RGBColor.from_string(_hex(line))
            sh.line.width = Pt(lw)
            if dash:
                sh.line.dash_style = MSO_LINE_DASH_STYLE.DASH
        else:
            sh.line.fill.background()
        if radius is not None and kind == MSO_SHAPE.ROUNDED_RECTANGLE:
            try:
                sh.adjustments[0] = radius
            except Exception:
                pass
        if name:
            sh.name = name
        return sh

    def text(self, s, x, y, w, h, lines, size=20, color=None, bold=False,
             align=None, anchor="top", rtl=None, spacing=None, box=None):
        """lines: نصٌّ، أو قائمةُ أسطر: str أو (نصّ، {size,bold,color,align}).
        كلُّ سطرٍ باتّجاه نصّه. box: شكلٌ قائمٌ يُكتب فيه بدل مربّع نصّ."""
        if box is None:
            box = s.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
        tf = box.text_frame
        tf.word_wrap = True
        tf.margin_left = tf.margin_right = Inches(0.05)
        tf.margin_top = tf.margin_bottom = Inches(0.02)
        tf.vertical_anchor = {"top": MSO_ANCHOR.TOP, "middle": MSO_ANCHOR.MIDDLE,
                              "bottom": MSO_ANCHOR.BOTTOM}[anchor]
        items = lines if isinstance(lines, list) else [lines]
        first = True
        for it in items:
            txt, o = (it, {}) if not isinstance(it, tuple) else it
            txt = str(txt if txt is not None else "")
            p = tf.paragraphs[0] if first else tf.add_paragraph()
            first = False
            r_ = is_rtl(txt, self.ar) if rtl is None else rtl
            al = o.get("align", align) or ("right" if r_ else "left")
            p.alignment = {"right": PP_ALIGN.RIGHT, "left": PP_ALIGN.LEFT,
                           "center": PP_ALIGN.CENTER}[al]
            p._p.get_or_add_pPr().set("rtl", "1" if r_ else "0")
            if spacing or o.get("space_after"):
                p.space_after = Pt(o.get("space_after", spacing))
            run = p.add_run()
            run.text = txt
            f = run.font
            f.size = Pt(o.get("size", size))
            f.bold = o.get("bold", bold)
            f.color.rgb = RGBColor.from_string(_hex(o.get("color", color or
                                                          self.t["text"])))
            rPr = run._r.get_or_add_rPr()
            for tag, fam in (("a:latin", self.fe if not r_ else self.fa),
                             ("a:cs", self.fa)):
                el = rPr.find(qn(tag))
                if el is None:
                    el = rPr.makeelement(qn(tag), {})
                    rPr.append(el)
                el.set("typeface", fam)
        return box

    def frame(self, s, x, y, w, h, shape="square", path=None, caption_in=True):
        """إطارُ صورة: مربّعٌ مستديرُ الزوايا أو دائرة، بحدٍّ منقّط وعلامة +.
        path ⟵ يُملأ بالصورة مقصوصةً على الشكل."""
        kind = MSO_SHAPE.OVAL if shape == "circle" else MSO_SHAPE.ROUNDED_RECTANGLE
        sh = self.shape(s, kind, x, y, w, h, fill=_mix(self.t["soft"], self.t["bg"],
                                                     0.3),
                        line=self.t["accent"], lw=1.75, dash=True, radius=0.08,
                        name=FRAME_NAME)
        if path and os.path.isfile(path):
            fill_frame(s, sh, path)
        elif caption_in:
            mc = _mix(self.t["primary"], self.t["bg"], 0.45)
            self.text(s, 0, 0, 0, 0, [("+", {"size": int(min(w, h) * 22) or 20,
                                             "color": mc, "align": "center"}),
                                      ("أضف صورة" if self.ar else "Add image",
                                       {"size": 12, "color": mc, "align": "center"})],
                      anchor="middle", box=sh)
        return sh

    def notes(self, s, text):
        if text:
            s.notes_slide.notes_text_frame.text = str(text)

    # ── عناصرُ ثابتة ──
    def header(self, s, title):
        t = self.t
        size = fit(title, W_IN - 2 * M, 0.9, 34, 24)
        self.text(s, M, 0.42, W_IN - 2 * M, 0.95, [(title, {"bold": True})],
                  size=size, color=t["title_c"], anchor="bottom")
        self.shape(s, MSO_SHAPE.RECTANGLE, self.X(M, 1.3), 1.42, 1.3, 0.07,
                   fill=t["accent"])
        # شريطٌ رأسيٌّ على حافّة البداية
        self.shape(s, MSO_SHAPE.RECTANGLE, self.X(0, 0.14), 0, 0.14, H_IN,
                   fill=t["primary"])

    def footer(self, s, n):
        t = self.t
        self.shape(s, MSO_SHAPE.RECTANGLE, M, 7.0, W_IN - 2 * M, 0.012,
                   fill=t["line"])
        self.text(s, self.X(M, 7.5), 7.05, 7.5, 0.35, self.title, size=11,
                  color=t["muted"])
        # رقمُ الشريحة في النهاية (يسارٌ في العربيّ)
        bx = self.X(W_IN - M - 0.6, 0.6)
        self.text(s, bx, 7.05, 0.6, 0.35, [(num(n, self.ar),
                                            {"align": "left" if self.ar else "right",
                                             "bold": True})],
                  size=12, color=t["primary"] if not t["dark"] else t["accent"])

    def content_slide(self, title, n):
        s = self.slide(self.t["bg"])
        self.header(s, title)
        self.footer(s, n)
        return s


# ─────────────────────────── أنواعُ الشرائح ───────────────────────────
TOP, BOTTOM = 1.75, 6.75                  # منطقةُ المحتوى


def _items(v):
    out = []
    for it in v or []:
        if isinstance(it, dict):
            out.append({"title": str(it.get("title") or it.get("label") or ""),
                        "text": str(it.get("text") or it.get("desc") or ""),
                        "value": str(it.get("value") or ""),
                        "path": it.get("path") or it.get("image"),
                        "caption": str(it.get("caption") or it.get("title") or "")})
        else:
            out.append({"title": str(it), "text": "", "value": "", "path": None,
                        "caption": str(it)})
    return out


def cover(D, spec):
    t = D.t
    s = D.slide(t["bg_title"])
    # زخارف: دائرةٌ كبيرةٌ شفّافة تخرج من الحافّة، وحلقة، ونقطة
    D.shape(s, MSO_SHAPE.OVAL, D.X(W_IN - 4.2, 6.4), 2.6, 6.4, 6.4,
            fill=t["accent"], alpha=0.16)
    D.shape(s, MSO_SHAPE.OVAL, D.X(W_IN - 2.6, 3.2), -1.2, 3.2, 3.2,
            line=t["accent"], lw=2.5)
    D.shape(s, MSO_SHAPE.OVAL, D.X(W_IN - 1.55, 0.35), 5.9, 0.35, 0.35,
            fill=t["accent"])
    title = spec.get("title", "")
    size = fit(title, 8.6, 2.2, 48, 30)
    D.text(s, D.X(0.9, 8.8), 1.7, 8.8, 2.3, [(title, {"bold": True})], size=size,
           color=t["text_on_dark"], anchor="bottom")
    D.shape(s, MSO_SHAPE.RECTANGLE, D.X(0.95, 1.8), 4.15, 1.8, 0.09, fill=t["accent"])
    if spec.get("subtitle"):
        D.text(s, D.X(0.9, 8.8), 4.4, 8.8, 1.2, spec["subtitle"],
               size=fit(spec["subtitle"], 8.6, 1.1, 24, 16), color=t["accent"])
    meta = " · ".join(str(spec[k]) for k in ("presenter", "date", "organization")
                      if spec.get(k))
    if meta:
        D.text(s, D.X(0.9, 8.8), 6.3, 8.8, 0.5, meta, size=14,
               color=_mix(t["text_on_dark"], t["bg_title"], 0.25))
    return s


def section(D, sd, n, idx):
    t = D.t
    s = D.slide(t["primary"])
    D.shape(s, MSO_SHAPE.OVAL, D.X(W_IN - 3.6, 5.6), 1.0, 5.6, 5.6,
            line=t["accent"], lw=2.5, alpha=None)
    D.shape(s, MSO_SHAPE.OVAL, D.X(W_IN - 2.9, 4.2), 1.7, 4.2, 4.2,
            fill=t["accent"], alpha=0.12)
    D.text(s, D.X(1.0, 5.0), 1.55, 5.0, 1.9, [(num(idx if D.ar else "%02d" % idx,
                                                    D.ar),
                                                {"bold": True})],
           size=96, color=t["accent"], anchor="bottom")
    title = sd.get("title", "")
    D.text(s, D.X(1.0, 7.8), 3.55, 7.8, 1.6, [(title, {"bold": True})],
           size=fit(title, 7.6, 1.5, 40, 26), color=t["text_on_dark"])
    if sd.get("subtitle") or sd.get("text"):
        st = sd.get("subtitle") or sd.get("text")
        D.text(s, D.X(1.0, 7.8), 5.2, 7.8, 1.0, st, size=18,
               color=_mix(t["text_on_dark"], t["primary"], 0.25))
    D.text(s, D.X(W_IN - M - 0.6, 0.6), 7.05, 0.6, 0.35,
           [(num(n, D.ar), {"align": "left" if D.ar else "right"})], size=12,
           color=t["accent"])
    return s


def _points_block(D, s, pts, x, y, w, h):
    """نقاطٌ بدوائرَ مرقّمة؛ كلُّ نقطةٍ باتّجاه نصّها، والحجمُ يملأ المساحة."""
    t = D.t
    pts = _items(pts)
    n = max(1, len(pts))
    row = min(1.15, h / n)
    texts = [(p["title"] + (" — " + p["text"] if p["text"] else "")) for p in pts]
    size = min(fit([tx], w - 0.9, row - 0.08, 26, 15) for tx in texts) if texts else 20
    y0 = y + (h - row * n) / 2 if row * n < h else y
    for i, p in enumerate(pts):
        yy = y0 + i * row
        r_ = is_rtl(p["title"] or p["text"], D.ar)
        d = min(0.5, row * 0.62)
        cx = (x + w - d) if r_ else x
        D.shape(s, MSO_SHAPE.OVAL, cx, yy + (row - d) / 2, d, d, fill=t["primary"])
        D.text(s, cx, yy + (row - d) / 2, d, d, [(num(i + 1, D.ar),
                                                   {"align": "center", "bold": True})],
               size=max(11, int(d * 30)), color=t["text_on_dark"], anchor="middle")
        tx = x if r_ else x + d + 0.25
        lines = [(p["title"], {"bold": bool(p["text"])})]
        if p["text"]:
            lines = [(p["title"], {"bold": True, "color": t["title_c"]}),
                     (p["text"], {"size": max(13, size - 3)})]
        D.text(s, tx, yy, w - d - 0.25, row, lines, size=size, anchor="middle",
               rtl=r_)


def points(D, sd, n):
    s = D.content_slide(sd.get("title", ""), n)
    _points_block(D, s, sd.get("points"), M + 0.3, TOP, W_IN - 2 * M - 0.3,
                  BOTTOM - TOP)
    return s


def image_text(D, sd, n):
    s = D.content_slide(sd.get("title", ""), n)
    im = sd.get("image")
    im = im if isinstance(im, dict) else {"shape": str(im or "square")}
    shape = "circle" if "circ" in str(im.get("shape", "")) or "دائر" in str(
        im.get("shape", "")) else "square"
    side = 4.4 if shape == "circle" else 4.6
    fw, fh = (side, side) if shape == "circle" else (5.0, 4.5)
    fx = D.X(W_IN - M - fw, fw)                       # الإطارُ في النهاية
    fy = TOP + (BOTTOM - TOP - fh) / 2
    D.frame(s, fx, fy, fw, fh, shape, im.get("path"))
    if im.get("caption"):
        D.text(s, fx, fy + fh + 0.05, fw, 0.4, [(im["caption"], {"align": "center"})],
               size=12, color=D.t["muted"])
    tw = W_IN - 2 * M - fw - 0.6
    _points_block(D, s, sd.get("points"), D.X(M + 0.3, tw - 0.3), TOP,
                  tw - 0.3, BOTTOM - TOP)
    return s


def cards(D, sd, n):
    """٢–٤ بطاقات: شريطٌ ملوّنٌ ودائرةُ رقمٍ وعنوانٌ ونصّ — أو صورةٌ في أعلاها."""
    s = D.content_slide(sd.get("title", ""), n)
    t = D.t
    its = _items(sd.get("cards") or sd.get("items"))[:4] or _items(["—"])
    k = len(its)
    gap = 0.35
    cw = (W_IN - 2 * M - gap * (k - 1)) / k
    with_img = bool(sd.get("images") or any(i["path"] for i in its))
    # ارتفاعُ البطاقة بقدر محتواها (كان ثابتاً فبقي نصفُها السفليُّ فارغاً)
    tsz = min(fit(i["title"], cw - 0.4, 0.9, 24, 15, bold=True) for i in its)
    bsz = min([fit(i["text"], cw - 0.5, 2.2, 20, 12) for i in its if i["text"]]
              or [16])
    body_h = max([(_lines(i["text"], (cw - 0.5) * 72 * 0.94, bsz, False) or 1)
                  * bsz * 1.35 / 72 for i in its if i["text"]] or [0])
    top_h = (min(1.9, (BOTTOM - TOP) * 0.42) + 0.2) if with_img else 1.0
    ch = min(BOTTOM - TOP - 0.1, 0.35 + top_h + 0.95 + body_h + 0.45)
    y0 = TOP + (BOTTOM - TOP - ch) / 2
    for i, it in enumerate(its):
        x = D.X(M + i * (cw + gap), cw)
        D.shape(s, MSO_SHAPE.ROUNDED_RECTANGLE, x, y0, cw, ch, fill=t["card"],
                line=t["line"], lw=1, radius=0.05)
        col = t["primary"] if i % 2 == 0 else t["accent"]
        D.shape(s, MSO_SHAPE.RECTANGLE, x + 0.25, y0, cw - 0.5, 0.08, fill=col)
        yy = y0 + 0.35
        if with_img:
            ih = min(1.9, ch * 0.42)
            D.frame(s, x + 0.25, yy, cw - 0.5, ih, "square", it["path"])
            yy += ih + 0.2
        else:
            d = 0.75
            D.shape(s, MSO_SHAPE.OVAL, x + (cw - d) / 2, yy, d, d, fill=col)
            D.text(s, x + (cw - d) / 2, yy, d, d,
                   [(num(i + 1, D.ar), {"align": "center", "bold": True})],
                   size=22, color=t["text_on_dark"], anchor="middle")
            yy += d + 0.25
        th = 0.9
        D.text(s, x + 0.2, yy, cw - 0.4, th, [(it["title"], {"align": "center",
                                                             "bold": True})],
               size=tsz, color=t["title_c"], anchor="middle")
        yy += th + 0.05
        if it["text"]:
            bh = y0 + ch - yy - 0.2
            D.text(s, x + 0.25, yy, cw - 0.5, bh, [(it["text"], {"align": "center"})],
                   size=bsz)
    return s


def circles(D, sd, n):
    """٣–٥ دوائر: رقمٌ أو صورةٌ داخلها، وعنوانٌ ونصٌّ تحتها."""
    s = D.content_slide(sd.get("title", ""), n)
    t = D.t
    its = _items(sd.get("circles") or sd.get("items"))[:5] or _items(["—"])
    k = len(its)
    slot = (W_IN - 2 * M) / k
    d = min(2.3, slot - 0.5)
    with_img = bool(sd.get("images") or any(i["path"] for i in its))
    cy = TOP + 0.15
    for i, it in enumerate(its):
        x = D.X(M + i * slot, slot)
        cx = x + (slot - d) / 2
        if with_img:
            D.frame(s, cx, cy, d, d, "circle", it["path"])
        else:
            col = t["primary"] if i % 2 == 0 else t["accent"]
            D.shape(s, MSO_SHAPE.OVAL, cx - 0.12, cy - 0.12, d + 0.24, d + 0.24,
                    line=col, lw=2)
            D.shape(s, MSO_SHAPE.OVAL, cx, cy, d, d, fill=col)
            lab = it["value"] or num(i + 1, D.ar)
            D.text(s, cx, cy, d, d, [(lab, {"align": "center", "bold": True})],
                   size=fit(lab, d - 0.3, d - 0.4, 44, 18), color=t["text_on_dark"],
                   anchor="middle")
        yy = cy + d + 0.3
        D.text(s, x + 0.1, yy, slot - 0.2, 0.7, [(it["title"], {"align": "center",
                                                                "bold": True})],
               size=fit(it["title"], slot - 0.2, 0.7, 22, 14), color=t["title_c"],
               anchor="middle")
        if it["text"]:
            bh = BOTTOM - yy - 0.75
            D.text(s, x + 0.15, yy + 0.75, slot - 0.3, bh,
                   [(it["text"], {"align": "center"})],
                   size=fit(it["text"], slot - 0.3, bh, 16, 11))
    return s


def images(D, sd, n):
    """أطرُ صورٍ (مربّعة أو دائريّة) بتعليق — ١ إلى ٦."""
    s = D.content_slide(sd.get("title", ""), n)
    im = sd.get("images")
    shape = "square"
    if isinstance(im, dict):
        shape = im.get("shape", "square")
        its = _items(im.get("items"))
    else:
        its = _items(im if isinstance(im, list) else [])
        shape = sd.get("shape", "square")
    shape = "circle" if ("circ" in str(shape) or "دائر" in str(shape)) else "square"
    its = its[:6] or _items(["", "", ""])
    k = len(its)
    cols = k if k <= 4 else 3
    rows = math.ceil(k / cols)
    gap = 0.4
    cap = 0.45
    slot_w = (W_IN - 2 * M - gap * (cols - 1)) / cols
    slot_h = (BOTTOM - TOP - gap * (rows - 1)) / rows
    for i, it in enumerate(its):
        r, c = divmod(i, cols)
        x = D.X(M + c * (slot_w + gap), slot_w)
        y = TOP + r * (slot_h + gap)
        fh = slot_h - (cap if it["caption"] else 0.05)
        fw = slot_w
        if shape == "circle":
            fw = fh = min(slot_w, fh)
        D.frame(s, x + (slot_w - fw) / 2, y, fw, fh, shape, it["path"])
        if it["caption"]:
            D.text(s, x, y + fh + 0.05, slot_w, cap - 0.05,
                   [(it["caption"], {"align": "center", "bold": True})],
                   size=fit(it["caption"], slot_w, cap, 16, 11), color=D.t["title_c"])
    return s


def steps(D, sd, n):
    """خطواتٌ متتابعة من البداية (اليمين في العربيّ) يصلها خطّ."""
    s = D.content_slide(sd.get("title", ""), n)
    t = D.t
    its = _items(sd.get("steps") or sd.get("items"))[:6] or _items(["—"])
    k = len(its)
    slot = (W_IN - 2 * M) / k
    d = 0.95
    ly = TOP + 0.55
    D.shape(s, MSO_SHAPE.RECTANGLE, M + slot / 2, ly + d / 2 - 0.03,
            W_IN - 2 * M - slot, 0.06, fill=t["line"])
    for i, it in enumerate(its):
        x = D.X(M + i * slot, slot)
        cx = x + (slot - d) / 2
        col = t["primary"] if i % 2 == 0 else t["accent"]
        D.shape(s, MSO_SHAPE.OVAL, cx, ly, d, d, fill=col, line=t["bg"], lw=4)
        D.text(s, cx, ly, d, d, [(num(i + 1, D.ar), {"align": "center", "bold": True})],
               size=26, color=t["text_on_dark"], anchor="middle")
        yy = ly + d + 0.3
        D.text(s, x + 0.1, yy, slot - 0.2, 0.75, [(it["title"], {"align": "center",
                                                                 "bold": True})],
               size=fit(it["title"], slot - 0.2, 0.75, 20, 13), color=t["title_c"],
               anchor="middle")
        if it["text"]:
            bh = BOTTOM - yy - 0.8
            D.text(s, x + 0.15, yy + 0.8, slot - 0.3, bh,
                   [(it["text"], {"align": "center"})],
                   size=fit(it["text"], slot - 0.3, bh, 16, 11))
    return s


def stats(D, sd, n):
    s = D.content_slide(sd.get("title", ""), n)
    t = D.t
    its = _items(sd.get("stats") or sd.get("items"))[:4] or _items(["—"])
    k = len(its)
    gap = 0.35
    cw = (W_IN - 2 * M - gap * (k - 1)) / k
    ch = 3.3
    y = TOP + (BOTTOM - TOP - ch) / 2
    for i, it in enumerate(its):
        x = D.X(M + i * (cw + gap), cw)
        D.shape(s, MSO_SHAPE.ROUNDED_RECTANGLE, x, y, cw, ch, fill=t["card"],
                line=t["line"], radius=0.06)
        D.shape(s, MSO_SHAPE.RECTANGLE, x, y + ch - 0.1, cw, 0.1,
                fill=t["accent"] if i % 2 else t["primary"])
        val = it["value"] or it["title"]
        D.text(s, x + 0.2, y + 0.3, cw - 0.4, 1.6, [(val, {"align": "center",
                                                           "bold": True})],
               size=fit(val, cw - 0.4, 1.5, 60, 24, bold=True),
               color=t["primary"] if not t["dark"] else t["accent"], anchor="middle")
        lab = it["text"] if it["value"] else ""
        lab = lab or (it["title"] if it["value"] else "")
        if lab:
            D.text(s, x + 0.25, y + 1.95, cw - 0.5, 1.15, [(lab, {"align": "center"})],
                   size=fit(lab, cw - 0.5, 1.15, 20, 12), anchor="top")
    return s


def quote(D, sd, n):
    s = D.content_slide(sd.get("title", ""), n)
    t = D.t
    q = str(sd.get("quote") or "")
    D.text(s, M, TOP - 0.2, W_IN - 2 * M, 1.3, [("”" if D.ar else "“",
                                                 {"align": "center"})],
           size=110, color=t["accent"])
    D.text(s, M + 1.2, TOP + 1.0, W_IN - 2 * M - 2.4, 3.0,
           [(q, {"align": "center", "bold": True})],
           size=fit(q, W_IN - 2 * M - 2.4, 2.8, 32, 18), color=t["title_c"],
           anchor="middle")
    if sd.get("author"):
        D.text(s, M, TOP + 4.1, W_IN - 2 * M, 0.5,
               [("— " + str(sd["author"]), {"align": "center"})], size=16,
               color=t["muted"])
    return s


def table(D, sd, n):
    """جدولٌ أصليّ: ترويسةٌ ملوّنة وصفوفٌ متناوبة وعرضُ أعمدةٍ بحسب النصّ.
    العربيّ: العمودُ الأوّلُ يميناً بترتيبٍ فعليٍّ في الملفّ (علَمُ rtl=0 —
    مقيس: PowerPoint يطبّقه فيقلب ثانيةً، وLibreOffice يتجاهله)."""
    s = D.content_slide(sd.get("title", ""), n)
    t = D.t
    tb = sd.get("table") or {}
    heads = [str(h) for h in tb.get("headers") or []]
    rows = [[str(c) for c in r] for r in tb.get("rows") or []]
    if tb.get("totals"):
        rows.append([str(c) for c in tb["totals"]])
    ncol = max([len(heads)] + [len(r) for r in rows] + [1])
    heads += [""] * (ncol - len(heads))
    rows = [r + [""] * (ncol - len(r)) for r in rows]
    rtl = D.ar
    if rtl:
        heads = heads[::-1]
        rows = [r[::-1] for r in rows]
    nrow = 1 + len(rows)
    tw = W_IN - 2 * M - 0.3
    avail = BOTTOM - TOP - (1.0 if sd.get("note") else 0.1)
    rh = min(0.62, avail / nrow)
    fs = int(max(11, min(18, rh * 30)))
    gf = s.shapes.add_table(nrow, ncol, Inches(M + 0.15), Inches(TOP + 0.05),
                            Inches(tw), Inches(rh * nrow))
    tbl = gf.table
    tbl._tbl.find(qn("a:tblPr")).set("rtl", "0")
    for flag in ("bandRow", "firstRow"):
        tbl._tbl.find(qn("a:tblPr")).set(flag, "0")
    lens = [max([len(heads[c])] + [len(r[c]) for r in rows]) + 4 for c in range(ncol)]
    tot = sum(lens)
    for c in range(ncol):
        tbl.columns[c].width = Inches(tw * lens[c] / tot)
    for r in range(nrow):
        tbl.rows[r].height = Inches(rh)
        for c in range(ncol):
            cell = tbl.cell(r, c)
            txt = heads[c] if r == 0 else rows[r - 1][c]
            cell.fill.solid()
            if r == 0:
                cell.fill.fore_color.rgb = RGBColor.from_string(t["primary"])
            elif tb.get("totals") and r == nrow - 1:
                cell.fill.fore_color.rgb = RGBColor.from_string(
                    _mix(t["accent"], t["bg"], 0.55))
            else:
                cell.fill.fore_color.rgb = RGBColor.from_string(
                    t["soft"] if r % 2 == 0 else t["card"])
            cell.margin_left = cell.margin_right = Inches(0.12)
            cell.vertical_anchor = MSO_ANCHOR.MIDDLE
            cell.text_frame.text = ""
            D.text(s, 0, 0, 0, 0, [(txt, {"bold": r == 0 or (
                bool(tb.get("totals")) and r == nrow - 1)})], size=fs,
                color=t["text_on_dark"] if r == 0 else t["text"], box=cell)
    if sd.get("note"):
        D.text(s, M + 0.15, BOTTOM - 0.8, tw, 0.7, sd["note"], size=14,
               color=t["muted"])
    return s


def chart(D, sd, n, chart_png):
    """رسمٌ بألوان القالب؛ ومعه نقاطُ الخلاصة إن وُجدت."""
    s = D.content_slide(sd.get("title", ""), n)
    spec = dict(sd.get("chart") or {})
    spec.setdefault("theme", D.t["id"])
    spec.setdefault("lang", D.lang)
    spec.setdefault("font", D.fa)
    png = chart_png(spec)
    try:
        from PIL import Image
        iw, ih = Image.open(png).size
        pts = sd.get("points")
        aw = (W_IN - 2 * M) * (0.6 if pts else 1.0)
        ah = BOTTOM - TOP
        w = min(aw, ah * iw / ih)
        h = w * ih / iw
        if pts:
            x = D.X(W_IN - M - w, w)                     # الرسمُ في النهاية
            D.shape(s, MSO_SHAPE.ROUNDED_RECTANGLE, x - 0.1, TOP - 0.05, w + 0.2,
                    h + 0.1, fill="FFFFFF", line=D.t["line"], radius=0.03)
            s.shapes.add_picture(png, Inches(x), Inches(TOP), Inches(w), Inches(h))
            tw = W_IN - 2 * M - w - 0.5
            _points_block(D, s, pts, D.X(M, tw), TOP, tw, BOTTOM - TOP)
        else:
            x = (W_IN - w) / 2
            s.shapes.add_picture(png, Inches(x), Inches(TOP), Inches(w), Inches(h))
    finally:
        try:
            os.remove(png)
        except OSError:
            pass
    return s


def closing(D, spec, n):
    t = D.t
    s = D.slide(t["bg_title"])
    D.shape(s, MSO_SHAPE.OVAL, (W_IN - 6.0) / 2, (H_IN - 6.0) / 2, 6.0, 6.0,
            fill=t["accent"], alpha=0.10)
    D.shape(s, MSO_SHAPE.OVAL, (W_IN - 4.8) / 2, (H_IN - 4.8) / 2, 4.8, 4.8,
            line=t["accent"], lw=2)
    txt = spec.get("closing")
    if txt is True or txt is None:
        txt = "شكراً لكم" if D.ar else "Thank you"
    D.text(s, 1.5, 2.9, W_IN - 3.0, 1.3, [(txt, {"align": "center", "bold": True})],
           size=fit(txt, W_IN - 3.0, 1.2, 48, 28), color=t["text_on_dark"],
           anchor="middle")
    if spec.get("closing_subtitle"):
        D.text(s, 1.5, 4.25, W_IN - 3.0, 0.8,
               [(spec["closing_subtitle"], {"align": "center"})], size=18,
               color=t["accent"])
    return s


# ─────────────────────────── الصور في الإطارات ───────────────────────────
def fill_frame(slide, shape, path):
    """املأ شكلاً (مربّعاً أو دائرة) بصورةٍ مقصوصةٍ على نسبته — كتعبئة
    PowerPoint «صورة»، فيبقى الشكلُ دائرةً والصورةُ داخله."""
    from pptx.oxml import parse_xml
    from PIL import Image
    _, rId = slide.part.get_or_add_image_part(path)
    iw, ih = Image.open(path).size
    fw, fh = int(shape.width), int(shape.height)
    fa, ia = fw / max(1, fh), iw / max(1, ih)
    l = r = t = b = 0
    if ia > fa:                                   # أعرض ⟵ يُقصّ الجانبان
        cut = (1 - fa / ia) / 2
        l = r = int(cut * 100000)
    else:
        cut = (1 - ia / fa) / 2
        t = b = int(cut * 100000)
    spPr = shape._element.spPr
    for tag in ("a:noFill", "a:solidFill", "a:gradFill", "a:blipFill", "a:pattFill",
                "a:grpFill"):
        for el in spPr.findall(qn(tag)):
            spPr.remove(el)
    xml = ('<a:blipFill xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
           'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/'
           'relationships" rotWithShape="1"><a:blip r:embed="%s"/>'
           '<a:srcRect l="%d" t="%d" r="%d" b="%d"/><a:stretch><a:fillRect/>'
           '</a:stretch></a:blipFill>' % (rId, l, t, r, b))
    geom = spPr.find(qn("a:prstGeom"))
    if geom is None:
        geom = spPr.find(qn("a:custGeom"))
    el = parse_xml(xml)
    if geom is not None:
        geom.addnext(el)
    else:
        spPr.append(el)
    if shape.has_text_frame:
        for p in list(shape.text_frame.paragraphs)[1:]:
            p._p.getparent().remove(p._p)
        shape.text_frame.paragraphs[0].text = ""
    try:
        shape.line.dash_style = MSO_LINE_DASH_STYLE.SOLID
    except Exception:
        pass
    return shape


# ─────────────────────────── البناء ───────────────────────────
LAYOUTS = ("section", "points", "image_text", "cards", "circles", "images", "steps",
           "stats", "quote", "table", "chart")


def kind_of(sd):
    lay = str(sd.get("layout") or "").lower()
    if lay in LAYOUTS:
        return lay
    for k in ("table", "chart", "cards", "circles", "steps", "stats", "quote"):
        if sd.get(k):
            return k
    if sd.get("images"):
        return "images"
    if sd.get("image") and sd.get("points"):
        return "image_text"
    return "points"


def plan_count(spec):
    slides = [s for s in spec.get("slides") or [] if isinstance(s, dict)]
    c = 1 if spec.get("cover", True) is not False else 0
    e = 1 if spec.get("closing", True) is not False else 0
    return c + len(slides) + e, c, len(slides), e


def build(spec, out, lang, chart_png, font_ar=None, font_en=None):
    """يبني العرضَ كلَّه. chart_png(spec) ⟵ مسارُ صورة PNG. يعيد عددَ الشرائح."""
    D = Deck(spec.get("theme"), lang, font_ar, font_en, spec.get("title", ""))
    n = 0
    sec = 0
    if spec.get("cover", True) is not False:
        cover(D, spec)
        n += 1
    for sd in [s for s in spec.get("slides") or [] if isinstance(s, dict)]:
        n += 1
        k = kind_of(sd)
        if k == "section":
            sec += 1
            s = section(D, sd, n, sec)
        elif k == "chart":
            s = chart(D, sd, n, chart_png)
        else:
            s = {"points": points, "image_text": image_text, "cards": cards,
                 "circles": circles, "images": images, "steps": steps,
                 "stats": stats, "quote": quote, "table": table}[k](D, sd, n)
        D.notes(s, sd.get("notes"))
    if spec.get("closing", True) is not False:
        n += 1
        closing(D, spec, n)
    # القالبُ محفوظٌ في الملفّ — لتأخذه شريحةٌ تُضاف بعدُ بالتعديل
    D.prs.core_properties.category = "weaver-design:%s" % D.t["id"]
    D.prs.core_properties.title = str(spec.get("title", ""))[:250]
    D.prs.save(out)
    return n, D.t["id"]


def add_to(prs, sd, n, lang, chart_png, font_ar=None, font_en=None, theme=None,
           title=""):
    """شريحةٌ مصمَّمةٌ واحدةٌ في عرضٍ قائم (تُلحق في آخره). يعيد الشريحة."""
    cat = str(prs.core_properties.category or "")
    if not theme and cat.startswith("weaver-design:"):
        theme = cat.split(":", 1)[1]
    D = Deck(theme, lang, font_ar, font_en, title or prs.core_properties.title or "",
             prs=prs)
    k = kind_of(sd)
    if k == "section":
        return section(D, sd, n, int(sd.get("number") or 1))
    if k == "chart":
        return chart(D, sd, n, chart_png)
    return {"points": points, "image_text": image_text, "cards": cards,
            "circles": circles, "images": images, "steps": steps,
            "stats": stats, "quote": quote, "table": table}[k](D, sd, n)
