# -*- coding: utf-8 -*-
"""وورد: التصميمُ الحرّ (docx_free.py) — للنشرات والكتيّبات والتقارير المصمَّمة.

شرطُ المستخدم: «لا يطعن في كونه سيكتب بالعربيّ من اليمين أو بالإنجليزيّ من اليسار».
فهنا: الفقراتُ بـdocx_rtl (المقيسة)، والجداولُ في العربيّ bidiVisual، والمحاذاةُ
البصريّة تُكتب منطقيّاً (في فقرةٍ من اليمين jc=right يظهر يساراً — قِيس بالرسم).
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OFFICE = os.path.join(_ROOT, "pipeline", "office.py")
from docx import Document   # noqa: E402

P = F = 0
W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def ok(name, cond, extra=""):
    global P, F
    if cond:
        P += 1
        print(f"  ✓ {name}")
    else:
        F += 1
        print(f"  ✗ {name}" + (f"   — {extra}" if extra else ""))


T = tempfile.mkdtemp(prefix="weaver-test-docxfree-")


def cli(*a):
    r = subprocess.run([sys.executable, OFFICE] + [str(x) for x in a],
                       capture_output=True, text=True, timeout=300)
    return r.returncode, r.stdout + r.stderr


def J(name, obj):
    p = os.path.join(T, name)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    json.dump(obj, open(p, "w", encoding="utf-8"), ensure_ascii=False)
    return p


def para(doc, text):
    for p in doc.element.body.iter(W + "p"):
        if "".join(t.text or "" for t in p.iter(W + "t")).strip() == text:
            return p
    return None


def jc(p):
    pPr = p.find(W + "pPr")
    j = pPr.find(W + "jc") if pPr is not None else None
    return None if j is None else j.get(W + "val")


def bidi(p):
    pPr = p.find(W + "pPr")
    return pPr is not None and pPr.find(W + "bidi") is not None


AR = {"design": "free", "title": "دليل", "font": "Cairo", "page": {"margins": 0.75},
      "blocks": [
          {"type": "hero", "bg": "#0F5132", "title": "دليلُ القراءة", "subtitle": "نشرة",
           "bleed": 0.75},
          {"type": "heading", "text": "لماذا نقرأ؟", "rule": "#F4C95D"},
          {"type": "text", "text": "فقرةٌ إلى اليسار", "align": "left"},
          {"type": "text", "text": "فقرةٌ إلى اليمين", "align": "right"},
          {"type": "text", "text": "فقرةٌ في الوسط", "align": "center"},
          {"type": "text", "text": "English line on the right", "align": "right"},
          {"type": "cards", "items": [{"title": "البطاقة الأولى", "text": "شرح"},
                                      {"title": "البطاقة الثانية", "text": "شرح"}]},
          {"type": "columns", "columns": [[{"type": "heading", "text": "العمود الأول",
                                            "before": 0}],
                                          [{"type": "image", "height": 1.5}]]},
          {"type": "callout", "title": "نصيحة", "text": "اقرأ كلّ يوم", "bg": "#FFF8E1",
           "accent": "#F4C95D"},
          {"type": "page_break"},
          {"type": "table", "headers": ["اليوم", "الكتاب"], "rows": [["السبت", "كليلة"]]}]}

print("\n— العربيّ: من اليمين —")
out = os.path.join(T, "ar.docx")
rc, o = cli("build", J("ar.json", AR), "--out", out)
ok("build ⟵ ✓ Word AR (free design) · RTL", rc == 0 and "AR (free design)" in o
   and "RTL" in o, o)
d = Document(out)
for txt in ("دليلُ القراءة", "لماذا نقرأ؟", "البطاقة الأولى", "العمود الأول", "نصيحة"):
    p = para(d, txt)
    ok("«%s»: فقرةٌ من اليمين (bidi)" % txt, p is not None and bidi(p))
ok("align right في العربيّ ⟵ بلا jc (يظهر يميناً)", jc(para(d, "فقرةٌ إلى اليمين"))
   is None)
ok("align left في العربيّ ⟵ jc=right (يظهر يساراً — مقيس)",
   jc(para(d, "فقرةٌ إلى اليسار")) == "right")
ok("align center ⟵ center", jc(para(d, "فقرةٌ في الوسط")) == "center")
pe = para(d, "English line on the right")
ok("سطرٌ إنجليزيٌّ في مستندٍ عربيّ ⟵ من اليسار (بلا bidi) وalign right ⟵ jc=right",
   pe is not None and not bidi(pe) and jc(pe) == "right")
tbls = list(d.element.body.iter(W + "tbl"))
ok("كلُّ الجداول في العربيّ bidiVisual (البطاقةُ الأولى يميناً)", tbls and all(
    t.find(W + "tblPr").find(W + "bidiVisual") is not None for t in tbls))
first_cells = [tc for t in tbls for tc in t.iter(W + "tc")]
ok("لا خليّةَ تبدأ بفقرةٍ فارغةٍ قبل محتواها", not any(
    len([k for k in tc if k.tag in (W + "p", W + "tbl")]) > 1
    and [k for k in tc if k.tag in (W + "p", W + "tbl")][0].tag == W + "p"
    and not "".join(t.text or "" for t in
                    [k for k in tc if k.tag in (W + "p", W + "tbl")][0].iter(W + "t"))
    .strip() and not list([k for k in tc if k.tag in (W + "p", W + "tbl")][0]
                          .iter(W + "drawing"))
    for tc in first_cells))
hero = tbls[0].find(W + "tblPr").find(W + "tblInd")
ok("شريطُ الغلاف من حافّة الورقة (tblInd سالب)", hero is not None
   and int(hero.get(W + "w")) < 0)
ok("الصناديقُ لا تنقسم بين صفحتين (cantSplit)", all(
    tr.find(W + "trPr") is not None and tr.find(W + "trPr").find(W + "cantSplit")
    is not None for tr in tbls[0].iter(W + "tr")))
ok("الخطُّ مضمَّنٌ في الملفّ", "embedded" in o)

try:
    import PIL  # noqa: F401
    pdir = os.path.join(T, ".ar-preview")
    ok("معاينةٌ في مجلّدٍ مخفيّ: صفحتان (page_break) وصورةٌ جامعة",
       os.path.isfile(os.path.join(pdir, "page-p01.png"))
       and os.path.isfile(os.path.join(pdir, "page-p02.png"))
       and os.path.isfile(os.path.join(pdir, "page-overview.png")), o)
    ok("  ⟵ وتباينٌ ضعيف (أصفرُ على أصفر) ⟵ تنبيه", "low contrast" in o, o)
except ImportError:
    print("  ⓘ Pillow غيرُ مثبَّت — تُخطّى المعاينة")

print("\n— الإنجليزيّ: من اليسار —")
EN = {"design": "free", "title": "Guide", "blocks": [
    {"type": "hero", "bg": "#1E1B4B", "title": "Deep Work Guide"},
    {"type": "stats", "items": [{"value": "90 min", "label": "focus"},
                                {"value": "3", "label": "priorities"}]},
    {"type": "text", "text": "Plan the night before."}]}
out2 = os.path.join(T, "en.docx")
rc, o2 = cli("build", J("en.json", EN), "--out", out2)
d2 = Document(out2)
ok("build ⟵ ✓ Word EN · LTR", rc == 0 and "EN (free design)" in o2 and "LTR" in o2, o2)
ok("الفقراتُ من اليسار (بلا bidi)", not any(bidi(p) for p in d2.element.body.iter(
    W + "p") if "".join(t.text or "" for t in p.iter(W + "t")).strip()))
ok("ولا bidiVisual في جداوله", not any(t.find(W + "tblPr").find(W + "bidiVisual")
                                        is not None for t in d2.element.body.iter(
                                            W + "tbl")))

print("\n— كتلٌ في ملفّات (حدُّ طول الردّ) والقالبُ الأكاديميُّ كما هو —")
J("blocks/b1.json", AR["blocks"][:3])
J("blocks/b2.json", {"blocks": AR["blocks"][3:6]})
sp = dict(AR, blocks=["blocks/b1.json", "blocks/b2.json"])
rc, o3 = cli("build", J("split.json", sp), "--out", os.path.join(T, "split.docx"))
ok("مواصفةٌ تجمع ملفَّي كتل ⟵ ٦ كتل", rc == 0 and "6 blocks" in o3, o3)
rc, o4 = cli("build", J("acad.json", {"title": "بحث", "sections": [
    {"heading": "المقدّمة", "body": "نصّ"}]}), "--out", os.path.join(T, "acad.docx"))
ok("بلا design ⟵ القالبُ الأكاديميّ كما كان", rc == 0 and "free design" not in o4
   and "Word AR:" in o4, o4)

shutil.rmtree(T, ignore_errors=True)
print("\n" + "=" * 62)
print(f" RESULT: {'PASS' if F == 0 else 'FAIL'}   ({P}/{P + F})")
print("=" * 62)
sys.exit(1 if F else 0)
