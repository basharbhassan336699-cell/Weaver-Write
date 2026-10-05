"""thumbs.py — صورةٌ مصغّرةٌ لما في الملفّ المرفوع (لا أيقونةٌ عامّة).

    make_thumb(src, dst) ⟵ True إن كُتبت صورةٌ PNG/JPEG في dst، وإلّا False.

لا يرفع أبداً: ما لا يُرسم يعود False فتعرض الواجهةُ بطاقةَ الاسم كما كانت.

· صورة          ⟵ مصغَّرةٌ منها (مع تدوير الكاميرا EXIF).
· PDF           ⟵ الصفحةُ الأولى (PyMuPDF، أو pdftoppm، أو نصُّها مرسوماً).
· docx/pptx/xlsx ⟵ الصورةُ المصغّرةُ المحفوظةُ في الملفّ نفسِه إن وُجدت
                  (docProps/thumbnail — يحفظها PowerPoint عادةً)، وإلّا رسمٌ
                  تقريبيٌّ للصفحة/الشريحة/الجدول الأوّل من محتواه الحقيقيّ.
· نصٌّ وشيفرة    ⟵ أسطرُه الأولى على صفحة.

العربيُّ يُرسم متّصلاً من اليمين: raqm إن وُجد، وإلّا arabic-reshaper + bidi.
"""
import io
import os
import re
import shutil
import subprocess
import zipfile

_HERE = os.path.dirname(os.path.abspath(__file__))
_FONTS = os.path.join(os.path.dirname(_HERE), "engines", "fonts-core", "arabic")

IMAGE_EXT = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".tif", ".tiff"}
TEXT_EXT = {".txt", ".md", ".markdown", ".csv", ".tsv", ".json", ".log", ".py",
            ".js", ".ts", ".html", ".htm", ".css", ".xml", ".yaml", ".yml",
            ".ini", ".cfg", ".sql", ".sh", ".c", ".cpp", ".h", ".java", ".go",
            ".rs"}

PAGE_W, PAGE_H = 360, 509          # A4
SLIDE_W = 480
_AR = re.compile("[؀-ۿݐ-ݿࢠ-ࣿﭐ-﷿ﹰ-﻿]")
_FCACHE = {}
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


def _font(px, bold=False):
    from PIL import ImageFont
    px = max(6, int(round(px)))
    key = (px, bold)
    if key in _FCACHE:
        return _FCACHE[key]
    path = os.path.join(_FONTS, "Tajawal-Bold.ttf" if bold else "Tajawal-Regular.ttf")
    f = None
    try:
        if _raqm():
            f = ImageFont.truetype(path, px, layout_engine=ImageFont.Layout.RAQM)
        else:
            f = ImageFont.truetype(path, px)
    except Exception:
        try:
            f = ImageFont.load_default()
        except Exception:
            f = None
    _FCACHE[key] = f
    return f


def _is_ar(t):
    return bool(_AR.search(t or ""))


def _vis(t):
    """النصُّ كما يُرسم: raqm يتولّى التشكيل والاتّجاه، وإلّا يُشكَّل هنا."""
    if _raqm() or not _is_ar(t):
        return t
    try:
        import arabic_reshaper
        from bidi.algorithm import get_display
        return get_display(arabic_reshaper.reshape(t))
    except Exception:
        return t


def _tlen(draw, t, font):
    try:
        return draw.textlength(_vis(t), font=font)
    except Exception:
        return len(t) * (getattr(font, "size", 10) * 0.55)


def _wrap(draw, text, font, width, max_lines=99):
    words = str(text or "").replace("\t", " ").split()
    lines, cur = [], ""
    for w in words:
        cand = (cur + " " + w).strip()
        if cur and _tlen(draw, cand, font) > width:
            lines.append(cur)
            cur = w
            if len(lines) >= max_lines:
                return lines
        else:
            cur = cand
    if cur:
        lines.append(cur)
    # كلمةٌ واحدةٌ أعرضُ من السطر ⟵ تُقصّ
    out = []
    for ln in lines[:max_lines]:
        while _tlen(draw, ln, font) > width and len(ln) > 1:
            ln = ln[:-1]
        out.append(ln)
    return out


def _text(draw, xy_box, line, font, fill, align=None):
    """سطرٌ داخل [x0, x1]: العربيُّ يميناً افتراضاً، واللاتينيُّ يساراً."""
    x0, x1, y = xy_box
    w = _tlen(draw, line, font)
    if align is None:
        align = "right" if _is_ar(line) else "left"
    if align == "center":
        x = x0 + (x1 - x0 - w) / 2
    elif align == "right":
        x = x1 - w
    else:
        x = x0
    try:
        draw.text((x, y), _vis(line), font=font, fill=fill)
    except Exception:
        pass


# ───────────────────────────── الصفحة ─────────────────────────────
class _Page:
    def __init__(self, w=PAGE_W, h=PAGE_H, margin=26, bg=(255, 255, 255)):
        from PIL import Image, ImageDraw
        self.img = Image.new("RGB", (w, h), bg)
        self.d = ImageDraw.Draw(self.img)
        self.w, self.h, self.m = w, h, margin
        self.y = margin

    @property
    def full(self):
        return self.y >= self.h - self.m

    def para(self, text, px=11, bold=False, color=(40, 40, 40), align=None,
             gap=None, max_lines=40):
        text = str(text or "").strip()
        if not text:
            self.y += px * 0.6
            return
        f = _font(px, bold)
        lh = px * 1.45
        for ln in _wrap(self.d, text, f, self.w - 2 * self.m, max_lines):
            if self.y + lh > self.h - self.m:
                self.y = self.h
                return
            _text(self.d, (self.m, self.w - self.m, self.y), ln, f, color, align)
            self.y += lh
        self.y += px * 0.5 if gap is None else gap

    def image(self, im, max_h_frac=0.4):
        if self.full:
            return
        try:
            im = im.convert("RGB")
            mw = self.w - 2 * self.m
            mh = min(self.h * max_h_frac, self.h - self.m - self.y)
            if mh < 20:
                self.y = self.h
                return
            im.thumbnail((int(mw), int(mh)))
            x = int(self.m + (mw - im.width) / 2)
            self.img.paste(im, (x, int(self.y)))
            self.y += im.height + 8
        except Exception:
            pass

    def table(self, rows, px=9, header_fill=(232, 236, 242), max_rows=8):
        rows = [r for r in rows if any(str(c or "").strip() for c in r)][:max_rows]
        if not rows or self.full:
            return
        ncol = max(len(r) for r in rows) or 1
        ncol = min(ncol, 6)
        f = _font(px)
        fb = _font(px, True)
        cw = (self.w - 2 * self.m) / ncol
        rh = px * 2
        ar = any(_is_ar(str(c)) for r in rows for c in r)
        for ri, r in enumerate(rows):
            if self.y + rh > self.h - self.m:
                self.y = self.h
                return
            for ci in range(ncol):
                cx = (ncol - 1 - ci) if ar else ci
                x0 = self.m + cx * cw
                box = [x0, self.y, x0 + cw, self.y + rh]
                if ri == 0:
                    self.d.rectangle(box, fill=header_fill)
                self.d.rectangle(box, outline=(170, 175, 185))
                val = str(r[ci] if ci < len(r) and r[ci] is not None else "")
                val = val.replace("\n", " ").strip()
                font = fb if ri == 0 else f
                while val and _tlen(self.d, val, font) > cw - 6:
                    val = val[:-1]
                _text(self.d, (x0 + 3, x0 + cw - 3, self.y + px * 0.35), val,
                      font, (30, 30, 30))
            self.y += rh
        self.y += 8


# ───────────────────────────── الأنواع ─────────────────────────────
def _save(im, dst, photo=False):
    im = im.convert("RGB")
    if photo:
        im.save(dst, "JPEG", quality=82)
    else:
        im.save(dst, "PNG", optimize=True)
    return True


def _thumb_image(src, dst):
    from PIL import Image, ImageOps
    with Image.open(src) as im:
        try:
            im = ImageOps.exif_transpose(im)
        except Exception:
            pass
        if im.mode in ("RGBA", "LA", "P"):
            im = im.convert("RGBA")
            bg = Image.new("RGB", im.size, (255, 255, 255))
            bg.paste(im, mask=im.split()[-1])
            im = bg
        im.thumbnail((480, 480))
        return _save(im, dst, photo=True)


_GENERIC = None


def _generic_thumbs():
    """بصماتُ الصور المصغّرة العامّة في قوالب python-docx وpython-pptx."""
    global _GENERIC
    if _GENERIC is None:
        import hashlib
        _GENERIC = set()
        for mod, rel in (("docx", "templates/default.docx"),
                         ("pptx", "templates/default.pptx")):
            try:
                m = __import__(mod)
                tp = os.path.join(os.path.dirname(m.__file__), rel)
                with zipfile.ZipFile(tp) as z:
                    for n in z.namelist():
                        if n.lower().startswith("docprops/thumbnail"):
                            _GENERIC.add(hashlib.md5(z.read(n)).hexdigest())
            except Exception:
                pass
    return _GENERIC


def _embedded_thumb(src, dst):
    """docProps/thumbnail.* داخل ملفّ Office — كما حفظه برنامجُه (Word أو
    PowerPoint)، لا الصورةَ العامّةَ من قالب مكتبة."""
    try:
        import hashlib
        with zipfile.ZipFile(src) as z:
            names = [n for n in z.namelist()
                     if n.lower().startswith("docprops/thumbnail")]
            if not names:
                return False
            data = z.read(names[0])
        if hashlib.md5(data).hexdigest() in _generic_thumbs():
            return False
        from PIL import Image
        im = Image.open(io.BytesIO(data))
        im.load()
        if im.width < 60 or im.height < 60:
            return False
        im.thumbnail((480, 480))
        return _save(im, dst)
    except Exception:
        return False


def _thumb_pdf(src, dst):
    try:
        import fitz  # PyMuPDF
        with fitz.open(src) as doc:
            if doc.page_count:
                pg = doc[0]
                z = PAGE_W / max(1.0, pg.rect.width)
                pix = pg.get_pixmap(matrix=fitz.Matrix(z, z), alpha=False)
                from PIL import Image
                im = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
                return _save(im, dst)
    except Exception:
        pass
    if shutil.which("pdftoppm"):
        try:
            base = dst + ".pp"
            subprocess.run(["pdftoppm", "-f", "1", "-l", "1", "-png",
                            "-scale-to-x", str(PAGE_W), "-scale-to-y", "-1", "-singlefile", src, base],
                           capture_output=True, timeout=60)
            if os.path.isfile(base + ".png"):
                from PIL import Image
                with Image.open(base + ".png") as im:
                    _save(im, dst)
                os.remove(base + ".png")
                return True
        except Exception:
            pass
    try:
        from pypdf import PdfReader
        r = PdfReader(src)
        txt = (r.pages[0].extract_text() or "") if r.pages else ""
    except Exception:
        txt = ""
    if not txt.strip():
        return False
    p = _Page()
    for ln in txt.splitlines():
        p.para(ln, px=10, gap=1)
        if p.full:
            break
    return _save(p.img, dst)


_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
_A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
_R = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"


def _thumb_docx(src, dst):
    import docx
    from PIL import Image
    d = docx.Document(src)
    p = _Page()
    body = d.element.body
    for el in body.iterchildren():
        if p.full:
            break
        tag = el.tag.split("}")[-1]
        if tag == "p":
            # صورةٌ في الفقرة؟
            blips = el.findall(".//" + _A + "blip")
            for b in blips[:1]:
                rid = b.get(_R + "embed")
                try:
                    part = d.part.related_parts[rid]
                    p.image(Image.open(io.BytesIO(part.blob)))
                except Exception:
                    pass
            text = "".join(t.text or "" for t in el.iter(_W + "t"))
            if not text.strip():
                if not blips:
                    p.y += 4
                continue
            style = ""
            try:
                ps = el.find(_W + "pPr")
                st = ps.find(_W + "pStyle") if ps is not None else None
                style = (st.get(_W + "val") or "").lower() if st is not None else ""
                jc = ps.find(_W + "jc") if ps is not None else None
                jcv = (jc.get(_W + "val") or "") if jc is not None else ""
            except Exception:
                jcv = ""
            align = "center" if jcv == "center" else None
            runs = el.findall(_W + "r")
            all_bold = bool(runs) and all(
                r.find(_W + "rPr") is not None and
                r.find(_W + "rPr").find(_W + "b") is not None for r in runs)
            if "title" in style:
                p.para(text, px=20, bold=True, color=(20, 40, 80), align=align or "center")
            elif "heading1" in style or style == "1":
                p.para(text, px=15, bold=True, color=(20, 50, 100), align=align)
            elif "heading" in style:
                p.para(text, px=12.5, bold=True, color=(30, 60, 110), align=align)
            else:
                p.para(text, px=10, bold=all_bold, align=align, max_lines=8)
        elif tag == "tbl":
            rows = []
            for tr in el.findall(_W + "tr"):
                rows.append(["".join(t.text or "" for t in tc.iter(_W + "t"))
                             for tc in tr.findall(_W + "tc")])
            p.table(rows)
    if p.y <= p.m + 2:
        return False
    return _save(p.img, dst)


def _slide_font(family, px, bold, text):
    """خطُّ الشريحة كما في الملفّ (أو أقربُ بديل)، وحرفٌ لا يحمله ⟵ خطٌّ يحمله."""
    try:
        import docx_render as DR
        path, _rb = DR._font_path(family, "ar" if _is_ar(text) else "lat", bold, False)
        path, text = DR._cover(path, text)
        return DR._pil_font(path, px, bold), text
    except Exception:
        return _font(px, bold), text


def _rgb(color_fmt):
    try:
        if color_fmt is not None and color_fmt.type is not None and color_fmt.rgb is not None:
            v = str(color_fmt.rgb)
            return tuple(int(v[i:i + 2], 16) for i in (0, 2, 4))
    except Exception:
        pass
    return None


def _thumb_pptx(src, dst):
    from pptx import Presentation
    prs = Presentation(src)
    if not len(prs.slides):
        return False
    img = _render_slide(prs, prs.slides[0], SLIDE_W)
    if img is None:
        return False
    return _save(img, dst)


def _render_slide(prs, slide, W):
    """شريحةٌ واحدةٌ صورةً بعرض W ⟵ PIL.Image، أو None إن لم يُرسم شيء."""
    from pptx.util import Emu
    from PIL import Image, ImageDraw
    sw, sh = int(prs.slide_width or Emu(12192000)), int(prs.slide_height or Emu(6858000))
    H = int(W * sh / sw)
    k = W / sw
    pt = W / (sw / 12700.0)          # بكسلٌ لكلِّ نقطة
    bg = (255, 255, 255)
    try:
        f = slide.background.fill
        c = _rgb(f.fore_color) if f.type == 1 else None
        bg = c or bg
    except Exception:
        pass
    img = Image.new("RGB", (W, H), bg)
    d = ImageDraw.Draw(img)
    dark = sum(bg) < 300

    def shapes(coll):
        for s in coll:
            if getattr(s, "shape_type", None) == 6:     # مجموعة
                try:
                    yield from shapes(s.shapes)
                except Exception:
                    pass
            else:
                yield s

    drew = False
    for s in shapes(slide.shapes):
        try:
            x, y = int((s.left or 0) * k), int((s.top or 0) * k)
            w, h = int((s.width or 0) * k), int((s.height or 0) * k)
        except Exception:
            continue
        try:
            if getattr(s, "shape_type", None) == 13:     # صورة
                im = Image.open(io.BytesIO(s.image.blob)).convert("RGB")
                if w > 2 and h > 2:
                    img.paste(im.resize((w, h)), (x, y))
                    drew = True
                continue
        except Exception:
            pass
        try:
            if s.fill.type == 1:
                c = _rgb(s.fill.fore_color)
                if c:
                    d.rectangle([x, y, x + w, y + h], fill=c)
                    drew = True
        except Exception:
            pass
        if getattr(s, "has_table", False):
            try:
                rows = [[c.text for c in r.cells] for r in s.table.rows][:6]
                ncol = max(len(r) for r in rows)
                cw, rh = w / max(1, ncol), max(8, h / max(1, len(rows)))
                fnt = _font(max(6, rh * 0.45))
                for ri, r in enumerate(rows):
                    for ci, val in enumerate(r):
                        bx = [x + ci * cw, y + ri * rh, x + (ci + 1) * cw, y + (ri + 1) * rh]
                        d.rectangle(bx, outline=(150, 150, 150),
                                    fill=(225, 230, 240) if ri == 0 else None)
                        _text(d, (bx[0] + 2, bx[2] - 2, bx[1] + 1), str(val)[:40], fnt,
                              (30, 30, 30))
                drew = True
            except Exception:
                pass
            continue
        if not getattr(s, "has_text_frame", False):
            continue
        # الأسطرُ أوّلاً (بخطّ الملفّ نفسِه)، ثمّ موضعُها العموديّ (أعلى/وسط/أسفل)
        laid = []
        for para in s.text_frame.paragraphs:
            txt = "".join(r.text for r in para.runs) or para.text
            if not txt.strip():
                laid.append(None)
                continue
            size, bold, col, fam = None, False, None, None
            for r in para.runs:
                try:
                    if r.font.size:
                        size = r.font.size.pt
                    bold = bold or bool(r.font.bold)
                    col = col or _rgb(r.font.color)
                    rp = r._r.find(_A + "rPr")
                    if rp is not None and fam is None:
                        for tg in (("cs", "latin") if _is_ar(txt) else ("latin", "cs")):
                            e = rp.find(_A + tg)
                            if e is not None and e.get("typeface") and \
                                    not e.get("typeface").startswith("+"):
                                fam = e.get("typeface")
                                break
                except Exception:
                    pass
            if size is None:
                ph = getattr(s, "is_placeholder", False)
                size = 36 if ph and y < H * 0.35 else 18
            px = max(6, size * pt)
            fnt, txt = _slide_font(fam, px, bold, txt)
            al = None
            try:
                a = para.alignment
                al = {2: "center", 3: "right", 1: "left"}.get(int(a)) if a is not None else None
            except Exception:
                al = None
            for ln in _wrap(d, txt, fnt, max(10, w - 2 * 7.2 * k * 12700), 6):
                laid.append((ln, fnt, col, al, px))
        tot = sum((it[4] * 1.25 if it else 4) for it in laid)
        anchor = None
        try:
            anchor = s.text_frame._txBody.find(_A + "bodyPr").get("anchor")
        except Exception:
            anchor = None
        if anchor is None and getattr(s, "is_placeholder", False):
            try:
                anchor = "ctr" if "TITLE" in str(s.placeholder_format.type) else None
            except Exception:
                anchor = None
        ty = y + 3.6 * k * 12700
        if anchor == "ctr":
            ty = y + max(0.0, (h - tot) / 2)
        elif anchor == "b":
            ty = y + max(0.0, h - tot - 3.6 * k * 12700)
        inset = 7.2 * k * 12700
        for it in laid:
            if it is None:
                ty += 4
                continue
            ln, fnt, col, al, px = it
            if ty > H:
                break
            _text(d, (x + inset, x + w - inset, ty), ln, fnt,
                  col or ((240, 240, 240) if dark else (30, 30, 30)), al)
            ty += px * 1.25
            drew = True
    if not drew:
        return None
    return img


def _thumb_xlsx(src, dst):
    import openpyxl
    wb = openpyxl.load_workbook(src, read_only=True, data_only=True)
    ws = wb.worksheets[0]
    rows = []
    for r in ws.iter_rows(min_row=1, max_row=16, max_col=6, values_only=True):
        rows.append(["" if v is None else str(v) for v in r])
    wb.close()
    rows = [r for r in rows if any(c.strip() for c in r)]
    if not rows:
        return False
    p = _Page(w=PAGE_H, h=PAGE_W, margin=14)
    p.para(ws.title, px=11, bold=True, color=(30, 110, 60), gap=4)
    p.table(rows, px=9, header_fill=(220, 238, 226), max_rows=16)
    return _save(p.img, dst)


def _thumb_text(src, dst, ext):
    with open(src, "rb") as fh:
        raw = fh.read(20000)
    txt = raw.decode("utf-8", "replace")
    p = _Page()
    if ext in (".csv", ".tsv"):
        sep = "\t" if ext == ".tsv" else ","
        import csv
        rows = list(csv.reader(io.StringIO(txt), delimiter=sep))[:8]
        p.table(rows)
        return _save(p.img, dst)
    for ln in txt.splitlines()[:60]:
        m = re.match(r"^(#{1,6})\s+(.*)$", ln) if ext in (".md", ".markdown") else None
        if m:
            p.para(m.group(2), px=17 - 2 * len(m.group(1)), bold=True, color=(20, 50, 100))
        else:
            p.para(ln, px=10, gap=1, max_lines=4)
        if p.full:
            break
    return _save(p.img, dst)


def make_thumb(src, dst):
    """اكتب صورةً مصغّرةً لـsrc في dst. لا يرفع."""
    ext = os.path.splitext(src)[1].lower()
    try:
        if ext in IMAGE_EXT:
            return _thumb_image(src, dst)
        if ext == ".pdf":
            return _thumb_pdf(src, dst)
        if ext in (".docx", ".pptx", ".xlsx", ".docm", ".pptm", ".xlsm"):
            # المحتوى أوّلاً: python-docx وpython-pptx يضعان في كلِّ ملفٍّ
            # صورةً مصغّرةً عامّةً من قالبهما (لا علاقةَ لها بالمحتوى) — قِيس.
            fn = {".doc": _thumb_docx, ".ppt": _thumb_pptx, ".xls": _thumb_xlsx}[ext[:4]]
            try:
                if fn(src, dst):
                    return True
            except Exception:
                pass
            return _embedded_thumb(src, dst)
        if ext in TEXT_EXT:
            return _thumb_text(src, dst, ext)
    except Exception:
        return False
    return False


# ═══════════════════════ المعاينةُ الكاملة (عند الضغط) ═══════════════════════
#
#   make_preview(src) ⟵ {"kind": "pages", "pages": [dataURL…]}   PDF وPowerPoint
#                       {"kind": "html",  "html": "…"}           Word وExcel وCSV
#                       {"kind": "text",  "text": "…", "md": bool}
#                       {"kind": ""}                              لا معاينة
#
# الـHTML يُبنى هنا من الصفر وكلُّ نصٍّ فيه مُهرَّب — لا يمرّ شيءٌ من الملفّ
# وسماً. والصورُ data: فقط. وPDF صورٌ لا إطار: كروم أندرويد لا يعرض PDF
# داخل الصفحة (يُنزّله).
MAX_PAGES = 30
PAGE_PX = 900


def _esc(t):
    return (str(t or "").replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def _data_url(im, quality=80):
    import base64
    buf = io.BytesIO()
    im.convert("RGB").save(buf, "JPEG", quality=quality)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


def _pdf_pages(src):
    from PIL import Image
    pages = []
    try:
        import fitz
        with fitz.open(src) as doc:
            for i in range(min(MAX_PAGES, doc.page_count)):
                pg = doc[i]
                z = PAGE_PX / max(1.0, pg.rect.width)
                pix = pg.get_pixmap(matrix=fitz.Matrix(z, z), alpha=False)
                pages.append(_data_url(Image.frombytes(
                    "RGB", (pix.width, pix.height), pix.samples)))
        if pages:
            return pages
    except Exception:
        pass
    if shutil.which("pdftoppm"):
        import tempfile
        tmp = tempfile.mkdtemp(prefix="wv-pdf-")
        try:
            subprocess.run(["pdftoppm", "-f", "1", "-l", str(MAX_PAGES), "-jpeg",
                            "-scale-to-x", str(PAGE_PX), "-scale-to-y", "-1",
                            src, os.path.join(tmp, "p")],
                           capture_output=True, timeout=180)
            for fn in sorted(os.listdir(tmp),
                             key=lambda n: int(re.sub(r"\D", "", n) or 0)):
                with Image.open(os.path.join(tmp, fn)) as im:
                    pages.append(_data_url(im))
        except Exception:
            pass
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    return pages


def _pdf_text(src):
    try:
        from pypdf import PdfReader
        r = PdfReader(src)
        return "\n\n".join((p.extract_text() or "") for p in r.pages[:MAX_PAGES])
    except Exception:
        return ""


def _docx_html(src):
    import base64
    import docx
    d = docx.Document(src)
    out = []
    for el in d.element.body.iterchildren():
        tag = el.tag.split("}")[-1]
        if tag == "p":
            for b in el.findall(".//" + _A + "blip")[:3]:
                try:
                    part = d.part.related_parts[b.get(_R + "embed")]
                    ct = getattr(part, "content_type", "") or "image/png"
                    if ct.startswith("image/") and "svg" not in ct:
                        out.append('<img src="data:%s;base64,%s" alt="">' % (
                            ct, base64.b64encode(part.blob).decode("ascii")))
                except Exception:
                    pass
            parts = []
            for r in el.findall(_W + "r"):
                t = "".join(x.text or "" for x in r.iter(_W + "t"))
                if not t:
                    continue
                rp = r.find(_W + "rPr")
                h = _esc(t)
                if rp is not None and rp.find(_W + "b") is not None:
                    h = "<b>" + h + "</b>"
                if rp is not None and rp.find(_W + "i") is not None:
                    h = "<i>" + h + "</i>"
                parts.append(h)
            # روابطُ ونصٌّ داخل وسومٍ أخرى (hyperlink…) — بلا تنسيق
            if not parts:
                t = "".join(x.text or "" for x in el.iter(_W + "t"))
                if t:
                    parts.append(_esc(t))
            if not parts:
                continue
            style, jcv = "", ""
            ps = el.find(_W + "pPr")
            if ps is not None:
                st = ps.find(_W + "pStyle")
                style = (st.get(_W + "val") or "").lower() if st is not None else ""
                jc = ps.find(_W + "jc")
                jcv = (jc.get(_W + "val") or "") if jc is not None else ""
                if ps.find(_W + "numPr") is not None:
                    style = style or "list"
            align = ' style="text-align:center"' if jcv == "center" else ""
            html = "".join(parts)
            if "title" in style:
                out.append('<h1 dir="auto"%s>%s</h1>' % (align, html))
            elif re.search(r"heading\s*1$|^1$", style):
                out.append('<h2 dir="auto"%s>%s</h2>' % (align, html))
            elif "heading" in style:
                out.append('<h3 dir="auto"%s>%s</h3>' % (align, html))
            elif "list" in style:
                out.append('<p dir="auto" class="li">• %s</p>' % html)
            else:
                out.append('<p dir="auto"%s>%s</p>' % (align, html))
        elif tag == "tbl":
            rows, texts = [], []
            for tr in el.findall(_W + "tr"):
                cells = []
                for tc in tr.findall(_W + "tc"):
                    t = "".join(x.text or "" for x in tc.iter(_W + "t"))
                    texts.append(t)
                    cells.append('<td dir="auto">%s</td>' % _esc(t))
                rows.append("<tr>" + "".join(cells) + "</tr>")
            # جدولٌ عربيٌّ يبدأ من اليمين (dir=auto على الجدول لا يكفي)
            rtl = el.find(".//" + _W + "bidiVisual") is not None or \
                any(_is_ar(t) for t in texts)
            out.append('<table dir="%s">' % ("rtl" if rtl else "ltr")
                       + "".join(rows) + "</table>")
    return "\n".join(out)


def _xlsx_html(src):
    import openpyxl
    wb = openpyxl.load_workbook(src, read_only=True, data_only=True)
    out = []
    for ws in wb.worksheets[:6]:
        rows = []
        for r in ws.iter_rows(min_row=1, max_row=300, max_col=30, values_only=True):
            vals = ["" if v is None else str(v) for v in r]
            if any(v.strip() for v in vals):
                rows.append(vals)
        if not rows:
            continue
        # الأعمدةُ الفارغةُ كلُّها في الآخر لا تُعرض
        ncol = max((max((i + 1 for i, v in enumerate(r) if v.strip()), default=0)
                    for r in rows), default=0)
        rows = [r[:ncol] for r in rows]
        try:
            rtl = bool(ws.sheet_view.rightToLeft)
        except Exception:
            rtl = False
        rtl = rtl or any(_is_ar(v) for r in rows for v in r)
        out.append('<h3 dir="auto">%s</h3>' % _esc(ws.title))
        body = []
        for i, r in enumerate(rows):
            tagc = "th" if i == 0 else "td"
            body.append("<tr>" + "".join('<%s dir="auto">%s</%s>' % (tagc, _esc(v), tagc)
                                         for v in r) + "</tr>")
        out.append('<table dir="%s">' % ("rtl" if rtl else "ltr")
                   + "".join(body) + "</table>")
    wb.close()
    return "\n".join(out)


def _csv_html(src, ext):
    import csv
    with open(src, "rb") as fh:
        txt = fh.read(400000).decode("utf-8", "replace")
    rows = list(csv.reader(io.StringIO(txt), delimiter="\t" if ext == ".tsv" else ","))[:500]
    body = []
    for i, r in enumerate(rows):
        tagc = "th" if i == 0 else "td"
        body.append("<tr>" + "".join('<%s dir="auto">%s</%s>' % (tagc, _esc(v), tagc)
                                     for v in r) + "</tr>")
    return "<table>" + "".join(body) + "</table>"


def make_preview(src):
    """معاينةُ الملفّ كاملاً (عند الضغط عليه). لا يرفع."""
    ext = os.path.splitext(src)[1].lower()
    try:
        if ext == ".pdf":
            pages = _pdf_pages(src)
            if pages:
                return {"kind": "pages", "pages": pages}
            t = _pdf_text(src)
            return {"kind": "text", "text": t, "md": False} if t.strip() else {"kind": ""}
        if ext in (".pptx", ".pptm"):
            from pptx import Presentation
            prs = Presentation(src)
            pages = []
            for sl in list(prs.slides)[:MAX_PAGES]:
                im = _render_slide(prs, sl, PAGE_PX)
                if im is None:
                    from PIL import Image
                    im = Image.new("RGB", (PAGE_PX, int(PAGE_PX * 9 / 16)), (255, 255, 255))
                pages.append(_data_url(im))
            return {"kind": "pages", "pages": pages} if pages else {"kind": ""}
        if ext in (".docx", ".docm"):
            h = _docx_html(src)
            return {"kind": "html", "html": h} if h.strip() else {"kind": ""}
        if ext in (".xlsx", ".xlsm"):
            h = _xlsx_html(src)
            return {"kind": "html", "html": h} if h.strip() else {"kind": ""}
        if ext in (".csv", ".tsv"):
            return {"kind": "html", "html": _csv_html(src, ext)}
        if ext in TEXT_EXT:
            with open(src, "rb") as fh:
                t = fh.read(400000).decode("utf-8", "replace")
            return {"kind": "text", "text": t, "md": ext in (".md", ".markdown")}
    except Exception:
        return {"kind": ""}
    return {"kind": ""}
