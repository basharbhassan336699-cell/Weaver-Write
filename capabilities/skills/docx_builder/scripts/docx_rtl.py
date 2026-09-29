"""
docx_rtl.py — اتّجاهُ Word وخطوطُه كما يقرؤها Word فعلاً (working module)
=========================================================================
قِيس بالرسم (LibreOffice يحاكي Word في هذا) على فقرةٍ عربيّةٍ واحدةٍ بستّ
محاذاة، كلُّها مع <w:bidi/>:
    jc=right ⟵ يسار ✗     jc=end ⟵ يسار ✗
    بلا jc   ⟵ يمين ✓     jc=left · jc=both · jc=start ⟵ يمين ✓
وكذا التعداد: «•» مع jc=right يقع يساراً. في فقرةٍ من اليمين يقرأ Word قيمتَي
left/right بدايةً ونهاية — فـ«right» التي كتبتها أدواتُنا لكلِّ فقرةٍ عربيّة
كانت ترمي النصَّ يساراً. وهذا ما رآه المستخدمُ في ملفّاته.

وما يلزم غيرُها ليقرأ Word الملفَّ عربيّاً كاملاً:
  · حجمُ الخطِّ وعرضُه للعربيّ في szCs/bCs/iCs — python-docx يكتب sz/b/i فقط،
    فيبقى العربيُّ بالحجم الافتراضيّ.
  · <w:rtl/> على الـrun العربيّ، و<w:bidi/> على القسم (موضعُ رقم الصفحة
    والأعمدة)، ولغةُ التدقيق ar-SA.
  · ترتيبُ العناصر كما في مخطّط OOXML (كانت <w:bidi/> تُلحق في آخر pPr).
  · تضمينُ الخطّ نفسِه في الملفّ (embed) ليظهر على هاتفٍ لا خطَّ فيه.

لا يُغيّر نصّاً. فقرةٌ لاتينيّةٌ في مستندٍ عربيّ (مرجعٌ إنجليزيّ) تصير من
اليسار؛ وفقرةٌ عربيّةٌ في مستندٍ إنجليزيّ تصير من اليمين.
"""
from __future__ import annotations

import io
import re
import uuid
import zipfile

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_AR = re.compile(r"[؀-ۿݐ-ݿࢠ-ࣿﭐ-﷿ﹰ-﻿]")
_LAT = re.compile(r"[A-Za-zÀ-ɏ]")

# ترتيبُ العناصر في مخطّط OOXML (ما يُحتاج هنا)
_PPR = ("pStyle", "keepNext", "keepLines", "pageBreakBefore", "framePr",
        "widowControl", "numPr", "suppressLineNumbers", "pBdr", "shd", "tabs",
        "suppressAutoHyphens", "kinsoku", "wordWrap", "overflowPunct",
        "topLinePunct", "autoSpaceDE", "autoSpaceDN", "bidi", "adjustRightInd",
        "snapToGrid", "spacing", "ind", "contextualSpacing", "mirrorIndents",
        "suppressOverlap", "jc", "textDirection", "textAlignment",
        "textboxTightWrap", "outlineLvl", "divId", "cnfStyle", "rPr", "sectPr",
        "pPrChange")
_RPR = ("rStyle", "rFonts", "b", "bCs", "i", "iCs", "caps", "smallCaps", "strike",
        "dstrike", "outline", "shadow", "emboss", "imprint", "noProof",
        "snapToGrid", "vanish", "webHidden", "color", "spacing", "w", "kern",
        "position", "sz", "szCs", "highlight", "u", "effect", "bdr", "shd",
        "fitText", "vertAlign", "rtl", "cs", "em", "lang", "eastAsianLayout",
        "specVanish", "oMath")
_SECT = ("headerReference", "footerReference", "footnotePr", "endnotePr", "type",
         "pgSz", "pgMar", "paperSrc", "pgBorders", "lnNumType", "pgNumType", "cols",
         "formProt", "vAlign", "noEndnote", "titlePg", "textDirection", "bidi",
         "rtlGutter", "docGrid", "printerSettings", "sectPrChange")


def _el(tag, **attrs):
    from docx.oxml import OxmlElement
    e = OxmlElement("w:" + tag)
    for k, v in attrs.items():
        e.set(W + k, str(v))
    return e


def _local(e):
    t = e.tag if isinstance(e.tag, str) else ""
    return t.split("}", 1)[-1]


def _put(parent, child, order):
    """أدرِج `child` في موضعه من ترتيب المخطّط (أو انقله إليه إن وُجد)."""
    name = _local(child)
    if child.getparent() is parent:
        parent.remove(child)
    try:
        idx = order.index(name)
    except ValueError:
        parent.append(child)
        return child
    after = set(order[idx + 1:])
    for c in parent:
        if _local(c) in after:
            c.addprevious(child)
            return child
    parent.append(child)
    return child


def _get(parent, tag):
    return parent.find(W + tag)


def has_ar(text):
    return bool(_AR.search(text or ""))


def _p_text(p):
    return "".join(t.text or "" for t in p.iter(W + "t"))


def fix_paragraph(p, doc_rtl):
    """اتّجاهُ فقرةٍ واحدة (عنصر w:p) من نصّها. يعيد True إن صارت من اليمين."""
    text = _p_text(p)
    ar, lat = has_ar(text), bool(_LAT.search(text))
    pPr = p.find(W + "pPr")
    if pPr is None:
        pPr = _el("pPr")
        p.insert(0, pPr)
    bidi, jc = _get(pPr, "bidi"), _get(pPr, "jc")
    rtl = ar or (doc_rtl and not lat)
    if rtl:
        if bidi is None:
            bidi = _el("bidi")
        _put(pPr, bidi, _PPR)                  # وفي موضعه من المخطّط
        if jc is not None and jc.get(W + "val") in ("right", "end"):
            pPr.remove(jc)                     # right في فقرةٍ من اليمين = يسار
    elif bidi is not None and doc_rtl:
        pPr.remove(bidi)                       # لاتينيٌّ في مستندٍ عربيّ ⟵ LTR
        if jc is not None and jc.get(W + "val") in ("right", "end"):
            pPr.remove(jc)
    for r in p.iter(W + "r"):
        fix_run(r)
    return rtl


def fix_run(r):
    """<w:rtl/> للعربيّ، والحجمُ والعرضُ والميلُ في خانات العربيّ (Cs)."""
    rPr = r.find(W + "rPr")
    txt = "".join(t.text or "" for t in r.iter(W + "t"))
    if rPr is None:
        if not has_ar(txt):
            return
        rPr = _el("rPr")
        r.insert(0, rPr)
    for a, b in (("b", "bCs"), ("i", "iCs"), ("sz", "szCs")):
        src = _get(rPr, a)
        if src is not None and _get(rPr, b) is None:
            dup = _el(b)
            for k, v in src.attrib.items():
                dup.set(k, v)
            _put(rPr, dup, _RPR)
    if has_ar(txt) and _get(rPr, "rtl") is None:
        _put(rPr, _el("rtl"), _RPR)


def _parts(doc):
    """جسمُ المستند ورؤوسُه وتذييلاتُه — بلا إنشاء ما لم يوجد."""
    out = [doc.element.body]
    for sec in doc.sections:
        for name in ("header", "footer", "first_page_header", "first_page_footer",
                     "even_page_header", "even_page_footer"):
            try:
                hf = getattr(sec, name)
                if hf.is_linked_to_previous:
                    continue
                out.append(hf._element)
            except Exception:
                continue
    return out


def finalize_direction(doc, lang="ar", paragraphs=None):
    """اتّجاهُ المستند كلِّه (أو فقراتٍ بعينها: عناصرُ w:p). لا يرفع.

    lang: لغةُ المستند — "ar" ⟵ القسمُ من اليمين، ولغةُ التدقيق ar-SA."""
    doc_rtl = lang == "ar"
    try:
        if paragraphs is None:
            paras = [p for part in _parts(doc) for p in part.iter(W + "p")]
        else:
            paras = list(paragraphs)
        for p in paras:
            try:
                fix_paragraph(p, doc_rtl)
            except Exception:
                continue
        if paragraphs is None and doc_rtl:
            for sp in doc.element.body.iter(W + "sectPr"):
                if _get(sp, "bidi") is None:
                    _put(sp, _el("bidi"), _SECT)
            _defaults_lang(doc)
    except Exception:
        pass
    return doc


def _defaults_lang(doc):
    try:
        st = doc.styles.element
        dd = st.find(W + "docDefaults")
        if dd is None:
            return
        rpd = dd.find(W + "rPrDefault")
        if rpd is None:
            rpd = _el("rPrDefault")
            dd.insert(0, rpd)
        rPr = rpd.find(W + "rPr")
        if rPr is None:
            rPr = _el("rPr")
            rpd.append(rPr)
        lang = _get(rPr, "lang")
        if lang is None:
            lang = _put(rPr, _el("lang"), _RPR)
        lang.set(W + "bidi", "ar-SA")
    except Exception:
        pass


_THEME_ATTRS = ("asciiTheme", "hAnsiTheme", "cstheme", "eastAsiaTheme")


def _set_fonts(rPr, cs=None, latin=None):
    rf = _get(rPr, "rFonts")
    if rf is None:
        rf = _put(rPr, _el("rFonts"), _RPR)
    if cs:
        rf.set(W + "cs", cs)
        rf.attrib.pop(W + "cstheme", None)
    if latin:
        rf.set(W + "ascii", latin)
        rf.set(W + "hAnsi", latin)
        rf.attrib.pop(W + "asciiTheme", None)
        rf.attrib.pop(W + "hAnsiTheme", None)


def apply_fonts(doc, cs=None, latin=None, paragraphs=None):
    """الخطُّ على كلِّ نصٍّ (أو فقراتٍ بعينها): `cs` للعربيّ، `latin` للاتينيّ.
    والافتراضيُّ في المستند كذلك (ما يُكتب بعدُ في Word). لا يرفع."""
    if not (cs or latin):
        return doc
    try:
        if paragraphs is None:
            paras = [p for part in _parts(doc) for p in part.iter(W + "p")]
        else:
            paras = list(paragraphs)
        for p in paras:
            for r in p.iter(W + "r"):
                rPr = r.find(W + "rPr")
                if rPr is None:
                    rPr = _el("rPr")
                    r.insert(0, rPr)
                _set_fonts(rPr, cs, latin)
            pPr = p.find(W + "pPr")
            prp = pPr.find(W + "rPr") if pPr is not None else None
            if prp is not None:                 # علامةُ الفقرة
                _set_fonts(prp, cs, latin)
        if paragraphs is None:
            dd = doc.styles.element.find(W + "docDefaults")
            rpd = dd.find(W + "rPrDefault") if dd is not None else None
            rPr = rpd.find(W + "rPr") if rpd is not None else None
            if rPr is not None:
                _set_fonts(rPr, cs, latin)
    except Exception:
        pass
    return doc


# ─────────────── تضمينُ الخطّ في الملفّ (ECMA-376 §17.8.1) ───────────────
_ODTTF = "application/vnd.openxmlformats-officedocument.obfuscatedFont"
_FONT_REL = R_NS + "/font"
_SETTINGS_BEFORE = {"writeProtection", "view", "zoom", "removePersonalInformation",
                    "removeDateAndTime", "doNotDisplayPageBoundaries",
                    "displayBackgroundShape", "printPostScriptOverText",
                    "printFractionalCharacterWidth", "printFormsData"}


def obfuscate(data, guid):
    """أوّلُ ٣٢ بايتاً XOR بمفتاح الـGUID معكوساً — كما يفكّه Word وLibreOffice."""
    key = bytes.fromhex(str(guid).strip("{}").replace("-", ""))[::-1]
    b = bytearray(data)
    for i in range(min(32, len(b))):
        b[i] ^= key[i % 16]
    return bytes(b)


def embed_fonts(docx_path, fonts):
    """ضمّن ملفّاتِ الخطوط في المستند. fonts: [(الاسمُ في المستند، {"regular":
    مسار، "bold": …، "italic": …، "bolditalic": …})]. يعيد أسماءَ ما ضُمِّن.

    خطٌّ مُضمَّنٌ سلفاً بالاسم نفسِه لا يُعاد. ويُكتب embedTrueTypeFonts في
    الإعدادات ليحفظه Word عند الحفظ."""
    from lxml import etree
    fonts = [(n, f) for n, f in (fonts or []) if n and f and f.get("regular")]
    if not fonts:
        return []
    with zipfile.ZipFile(docx_path) as z:
        items = [(i, z.read(i.filename)) for i in z.infolist()]
    data = {i.filename: b for i, b in items}
    names = [i.filename for i, _ in items]
    ft_name = "word/fontTable.xml"
    if ft_name not in data:
        return []
    ft = etree.fromstring(data[ft_name])
    if ft.nsmap.get("r") != R_NS:
        # الجذرُ بلا r: ⟵ جذرٌ جديدٌ يحمله (lxml لا يضيف nsmap لعنصرٍ قائم)
        nsmap = dict(ft.nsmap)
        nsmap["r"] = R_NS
        nroot = etree.Element(ft.tag, nsmap=nsmap)
        for k, v in ft.attrib.items():
            nroot.set(k, v)
        for c in list(ft):
            nroot.append(c)
        ft = nroot
    rels_name = "word/_rels/fontTable.xml.rels"
    PR = "http://schemas.openxmlformats.org/package/2006/relationships"
    if rels_name in data:
        rels = etree.fromstring(data[rels_name])
    else:
        rels = etree.Element("{%s}Relationships" % PR, nsmap={None: PR})
    used_ids = {r.get("Id") for r in rels}
    n_font = sum(1 for n in names if n.startswith("word/fonts/")) + 1
    done, new_parts = [], {}
    for family, files in fonts:
        node = next((f for f in ft.findall(W + "font")
                     if f.get(W + "name") == family), None)
        if node is not None and node.find(W + "embedRegular") is not None:
            continue
        if node is None:
            node = etree.SubElement(ft, W + "font")
            node.set(W + "name", family)
            etree.SubElement(node, W + "charset").set(W + "val", "00")
            etree.SubElement(node, W + "family").set(W + "val", "auto")
            etree.SubElement(node, W + "pitch").set(W + "val", "variable")
        for style, tag in (("regular", "embedRegular"), ("bold", "embedBold"),
                           ("italic", "embedItalic"), ("bolditalic", "embedBoldItalic")):
            path = files.get(style)
            if not path:
                continue
            with open(path, "rb") as fh:
                raw = fh.read()
            guid = "{%s}" % str(uuid.uuid4()).upper()
            part = "fonts/weaver-font%d.odttf" % n_font
            n_font += 1
            rid = "rIdWvF%d" % n_font
            while rid in used_ids:
                n_font += 1
                rid = "rIdWvF%d" % n_font
            used_ids.add(rid)
            rel = etree.SubElement(rels, "{%s}Relationship" % PR)
            rel.set("Id", rid)
            rel.set("Type", _FONT_REL)
            rel.set("Target", part)
            new_parts["word/" + part] = obfuscate(raw, guid)
            e = etree.SubElement(node, W + tag)
            e.set("{%s}id" % R_NS, rid)
            e.set(W + "fontKey", guid)
        done.append(family)
    if not done:
        return []
    data[ft_name] = etree.tostring(ft, xml_declaration=True, encoding="UTF-8",
                                   standalone=True)
    data[rels_name] = etree.tostring(rels, xml_declaration=True, encoding="UTF-8",
                                     standalone=True)
    # نوعُ المحتوى
    ct = etree.fromstring(data["[Content_Types].xml"])
    CT = "http://schemas.openxmlformats.org/package/2006/content-types"
    if not any(d.get("Extension", "").lower() == "odttf"
               for d in ct.findall("{%s}Default" % CT)):
        d = etree.Element("{%s}Default" % CT)
        d.set("Extension", "odttf")
        d.set("ContentType", _ODTTF)
        ct.insert(0, d)
        data["[Content_Types].xml"] = etree.tostring(
            ct, xml_declaration=True, encoding="UTF-8", standalone=True)
    # الإعدادات: embedTrueTypeFonts
    sname = "word/settings.xml"
    if sname in data:
        st = etree.fromstring(data[sname])
        if st.find(W + "embedTrueTypeFonts") is None:
            e = etree.Element(W + "embedTrueTypeFonts")
            for c in st:
                if _local(c) not in _SETTINGS_BEFORE:
                    c.addprevious(e)
                    break
            else:
                st.append(e)
            data[sname] = etree.tostring(st, xml_declaration=True, encoding="UTF-8",
                                         standalone=True)
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for n in names:
            z.writestr(n, data[n])
        if rels_name not in names:
            z.writestr(rels_name, data[rels_name])
        for n, b in new_parts.items():
            z.writestr(n, b)
    with open(docx_path, "wb") as fh:
        fh.write(out.getvalue())
    return done
