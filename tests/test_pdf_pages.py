# -*- coding: utf-8 -*-
"""قارئُ PDF صفحةً صفحة (pipeline/pdf_pages.py) — عربيٌّ وإنجليزيّ، من رابطٍ
أو ملفّ، وOCR حين تفشل القراءة.

الملفّاتُ في engines/weaver-core/probes/pdf/:
  pages.pdf          ٣ صفحات إنجليزيّة، في كلٍّ علامتُها
  ar_text_pdfjs.pdf  عربيٌّ حقيقيّ (من اختبارات pdf.js) — pypdf يقلب ترتيبَ كلماته
  ar_broken_map.pdf  عربيٌّ خريطةُ حروفه تالفة — القارئان يُخرجان رموزاً
  ar_scanned.pdf     صورٌ بلا نصّ — لا يُقرأ إلا بـOCR

ما يحتاج برنامجاً غيرَ موجودٍ يُتخطّى ويُقال ذلك — ولا يُحسب نجاحاً.
"""
import http.server
import os
import shutil
import sys
import tempfile
import threading
import types

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

from pipeline import pdf_pages as PP   # noqa: E402

P = F = S = 0
FX = os.path.join(_ROOT, "engines", "weaver-core", "probes", "pdf")


def ok(name, cond, extra=""):
    global P, F
    if cond:
        P += 1
        print(f"  ✓ {name}")
    else:
        F += 1
        print(f"  ✗ {name}" + (f"   — {extra}" if extra else ""))


def skip(name, why):
    global S
    S += 1
    print(f"  – {name}   (تُخطّي: {why})")


HAS_PTT = bool(shutil.which("pdftotext"))
HAS_OCR = bool(PP.ocr_langs() and "ara" in PP.ocr_langs()
               and shutil.which("pdftoppm"))

print("\n— التنظيف —")
ok("أشكالُ العرض العربيّة ⟵ حروف", PP.clean("ﺍﻟﻌﺮﺑﻴﺔ") == "العربية")
ok("ولا ⟵ لا", PP.clean("ﻻ") == "لا")
ok("علاماتُ الاتّجاه الخفيّة تُحذف",
   PP.clean("‫نص‬‏") == "نص")
ok("ولا يُمسّ غيرُها (ﬁ · ² · ١٢)", PP.clean("ﬁ x² ١٢") == "ﬁ x² ١٢")

print("\n— الحكمُ على شكل النصّ —")
_AR = ("تواجه الجامعات العربية تحديات كبيرة في التحول الرقمي وتمويل البحث "
       "العلمي وتدريب الكوادر")
ok("عربيٌّ سليم ⟵ صالح", PP.quality(_AR)[0])
ok("إنجليزيٌّ سليم ⟵ صالح",
   PP.quality("The results show a significant improvement in accuracy.")[0])
ok("فارغ ⟵ غيرُ صالح", not PP.quality("  \n 12 ")[0])
ok("رموزٌ لا كلمات (خرجُ خريطةٍ تالفة) ⟵ غيرُ صالح",
   not PP.quality("ژܳﺃ ۰݁ ܐܒܓ ܕܗܘ ܙܚܛ ܝܟܠ ܡܢܣ ܥܦܨ ܩܪܫ ܬ")[0])
ok("حروفٌ مفكَّكة «ا ل ك ت ا ب» ⟵ غيرُ صالح",
   not PP.quality("ا ت ك ا ل ب ن ج ت ا ل ع ر ب ي ة س ر")[0])
ok("قليلُ العربيّ وأغلبُه حرفٌ واحد وسط إنجليزيّ ⟵ غيرُ صالح",
   not PP.quality("English mixed text here and more words ا آ ا")[0])
ok("حروفٌ مقلوبة (كلماتٌ تبدأ بـة) ⟵ غيرُ صالح",
   not PP.quality(" ".join(w[::-1] for w in _AR.split()))[0])

print("\n— أرقامُ الصفحات —")
ok("«3-5,1,9» في ملفٍّ من ٦", PP.parse_pages("3-5,1,9", 6) == [1, 3, 4, 5])
ok("فاصلةٌ عربيّة ومدى معكوس", PP.parse_pages("٥-3،2".replace("٥", "5"), 9)
   == [2, 3, 4, 5])
ok("arxiv abs ⟵ pdf", PP._arxiv_pdf("https://arxiv.org/abs/1706.03762v7")
   == "https://arxiv.org/pdf/1706.03762v7")
ok("citation_pdf_url نسبيّ ⟵ مطلق", PP._pdf_link_in_html(
    '<meta content="/a/b.pdf" name="citation_pdf_url">',
    "https://j.org/x/y") == "https://j.org/a/b.pdf")

print("\n— قراءةُ الملفّات —")
r = PP.read_pdf(os.path.join(FX, "pages.pdf"))
ok("إنجليزيّ: ٣ صفحات، كلٌّ بعلامتها", r["ok"] and [
    ("alpha", "bravo", "charlie")[i] in p["text"] for i, p in
    enumerate(r["pages"])] == [True] * 3, str(r)[:200])
ok("  ⟵ بلا OCR", all(p["method"] != "ocr" for p in r["pages"]))
r = PP.read_pdf(os.path.join(FX, "pages.pdf"), pages="2-3,9")
ok("--pages 2-3,9 ⟵ ص. ٢ و٣ فقط", [p["page"] for p in r["pages"]] == [2, 3])
if HAS_PTT:
    r = PP.read_pdf(os.path.join(FX, "ar_text_pdfjs.pdf"))
    ok("عربيٌّ حقيقيّ ⟵ بترتيبه الصحيح (لا «العربية الخطوط انواع»)",
       r["pages"][0]["text"].startswith("انواع الخطوط العربية")
       and r["pages"][0]["method"] == "pdftotext", r["pages"][0]["text"][:60])
else:
    skip("عربيٌّ حقيقيّ بترتيبه", "pdftotext غيرُ مثبَّت")

if HAS_OCR:
    for name in ("ar_broken_map.pdf", "ar_scanned.pdf"):
        r = PP.read_pdf(os.path.join(FX, name))
        txt = [p["text"] for p in r["pages"]]
        ok("%s ⟵ كلُّ صفحةٍ بـOCR وبنصِّها" % name,
           all(p["method"] == "ocr" for p in r["pages"])
           and "الجامعات العربية" in txt[0] and "الدراسة" in txt[1]
           and "English mixed text" in txt[2], str(txt)[:300])
        ok("  ⟵ والصفحةُ موسومة: تحقّق من الأرقام",
           all("تحقّق من الأرقام" in p["note"] for p in r["pages"]))
    _left = set(os.listdir(tempfile.gettempdir()))
    ok("  ⟵ ولا يبقى مجلّدُ OCR مؤقّت",
       not any(n.startswith("weaver_ocr_") for n in _left))
else:
    skip("OCR عربيّ", "tesseract/ara/pdftoppm غيرُ مثبَّت")

r = PP.read_pdf(os.path.join(FX, "ar_broken_map.pdf"), ocr="off")
ok("--ocr off ⟵ لا يُختلَق نصّ: تُعلَن «تعذّرت القراءة»",
   all(p["note"].startswith("تعذّرت") for p in r["pages"]), str(r)[:300])
ok("ملفٌّ ليس PDF ⟵ خطأٌ مقروء", not PP.read_pdf(__file__)["ok"])

# pypdf قد يرفع PanicException من Rust (BaseException) عند استيراده.
class _Panic(BaseException):
    pass


_fake = types.ModuleType("pypdf")


def _boom(*a, **k):
    raise _Panic("Python API call failed")


_fake.PdfReader = _boom
_real_pypdf = sys.modules.get("pypdf")
sys.modules["pypdf"] = _fake
try:
    ok("pypdf ينهار (BaseException) ⟵ لا ينهار القارئ",
       PP._pypdf_reader(os.path.join(FX, "pages.pdf")) is None)
finally:
    if _real_pypdf is None:
        sys.modules.pop("pypdf", None)
    else:
        sys.modules["pypdf"] = _real_pypdf

print("\n— أين الاقتباس؟ —")
r = PP.read_pdf(os.path.join(FX, "pages.pdf"))
ok("في ص. ٢", PP.find(r, "PAGE  TWO\nmarker") == [2])
ok("غيرُ موجود ⟵ []", PP.find(r, "not in this file") == [])
_rr = {"pages": [{"page": 4, "text": "أظهرت الدراسةُ أنّ"},
                 {"page": 5, "text": "نسبةَ المشاركة بلغت"}]}
ok("عابرٌ لصفحتين، وبلا اعتبارٍ للتشكيل ⟵ يبدأ في ص. ٤",
   PP.find(_rr, "أن نسبة المشاركة") == [4])

print("\n— من رابطٍ مباشرةً —")
_DOC = open(os.path.join(FX, "pages.pdf"), "rb").read()


class H(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        from urllib.parse import unquote
        p = unquote(self.path)
        if p in ("/doc.pdf", "/ملف-عربي.pdf", "/big.pdf"):
            self.send_response(200)
            self.send_header("Content-Type", "application/pdf")
            self.end_headers()
            self.wfile.write(_DOC if p != "/big.pdf" else _DOC + b"0" * 5000)
        elif p == "/article":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(b'<html><head><meta name="citation_pdf_url" '
                             b'content="/doc.pdf"></head><body>x</body></html>')
        elif p == "/plain":
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(b"<!doctype html><html><body>no pdf</body></html>")
        else:
            self.send_response(404)
            self.end_headers()


srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
threading.Thread(target=srv.serve_forever, daemon=True).start()
base = "http://127.0.0.1:%d" % srv.server_address[1]
_os_proxy = {k: os.environ.pop(k) for k in list(os.environ)
             if k.lower() in ("http_proxy", "https_proxy", "all_proxy")}
os.environ["no_proxy"] = "127.0.0.1"
try:
    path, final, err = PP.download(base + "/doc.pdf")
    ok("رابطُ ملفّ ⟵ يُنزَّل ويُقرأ", path and PP.read_pdf(path)["read"] == 3,
       err)
    if path:
        os.remove(path)
    path, final, err = PP.download(base + "/article")
    ok("صفحةُ مقال ⟵ يتبع citation_pdf_url إلى الملفّ",
       path and final.endswith("/doc.pdf"), err)
    if path:
        os.remove(path)
    path, final, err = PP.download(base + "/plain")
    ok("صفحةُ ويب بلا ملفّ ⟵ يقول ذلك", not path and "صفحةُ ويب" in err, err)
    path, final, err = PP.download(base + "/nothing")
    ok("404 ⟵ «الموقعُ رفض»", not path and "404" in err, err)
    path, final, err = PP.download(base + "/ملف-عربي.pdf")
    ok("رابطٌ بحروفٍ عربيّة ⟵ يعمل", bool(path), err)
    if path:
        os.remove(path)
    _mb = PP.MAX_BYTES
    PP.MAX_BYTES = 3000
    path, final, err = PP.download(base + "/big.pdf")
    PP.MAX_BYTES = _mb
    ok("أكبرُ من الحدّ ⟵ يُرفض ولا يبقى ملفٌّ مؤقّت",
       not path and "أكبرُ من" in err, err)

    import io
    from contextlib import redirect_stdout, redirect_stderr
    _before = {n for n in os.listdir(tempfile.gettempdir())
               if n.startswith("weaver_pdf_")}
    out, errb = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(errb):
        rc = PP.main([base + "/article"])
    ok("الأمرُ كاملاً من رابط ⟵ «=== ص. 2 ===» ورمز 0",
       rc == 0 and "=== ص. 2 ===" in out.getvalue()
       and "WEAVER PAGE TWO" in out.getvalue(), out.getvalue()[:200])
    _after = {n for n in os.listdir(tempfile.gettempdir())
              if n.startswith("weaver_pdf_")}
    ok("  ⟵ والملفُّ المؤقّتُ حُذف بعد القراءة", _after <= _before)
    tmpo = os.path.join(tempfile.mkdtemp(), "o.txt")
    with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
        rc = PP.main([os.path.join(FX, "pages.pdf"), "--out", tmpo])
    ok("--out يكتب الملفّ", rc == 0 and "=== ص. 3 ===" in open(
        tmpo, encoding="utf-8").read())
    with redirect_stdout(io.StringIO()) as o2, redirect_stderr(io.StringIO()):
        rc = PP.main([os.path.join(FX, "pages.pdf"), "--find", "marker bravo"])
    ok("--find ⟵ «في ص. 2» ورمز 0", rc == 0 and "ص. 2" in o2.getvalue())
finally:
    srv.shutdown()
    os.environ.update(_os_proxy)

print("\n" + "=" * 62)
print(f" RESULT: {'PASS' if F == 0 else 'FAIL'}   ({P}/{P + F})"
      + (f"   · تُخطّي {S}" if S else ""))
print("=" * 62)
sys.exit(1 if F else 0)
