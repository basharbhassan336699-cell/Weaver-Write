"""
tools/probe_pdf_pages.py — الخطوة ٠ لتوثيق رقم الصفحة: قياسٌ لا بناء
====================================================================
فحصٌ للقراءة فقط: لا يكتب في الإعداد، ولا يثبّت شيئاً، ولا ينادي النموذج.
يجيب بالدليل عن سؤالين قبل أن نبني أيَّ شيء:

  ١ أيقرأ هاتفُك ملفَّ PDF **صفحةً صفحة** ويعرف رقمَ كلِّ صفحة؟
     ⟵ يجرّب كلَّ قارئٍ مثبَّت على ملفٍّ معروف من ٣ صفحات
       (engines/weaver-core/probes/pdf/pages.pdf): في الصفحة N علامتُها N.
     ⟵ ويجرّب قارئَ المشروع نفسَه (capabilities/tools/tool_pdf.py).
  ٢ أيرى النموذجُ في المحرّك أداةَ `pdf`؟
     ⟵ يسأل البوّابةَ نفسَها (tools.catalog · tools.effective) لا النموذج.
       وثائقُ المحرّك (docs/tools/pdf.md): الأداةُ لا تُسجَّل إلا إن وُجد
       نموذجٌ يقرأ PDF (أنثروبيك/غوغل أصلاً، أو نموذجُ صور).

وما لم يُقَس يُقال «لم يُقَس» — لا يُفترض.

التشغيل:
    cd ~/weaver-write && python3 tools/probe_pdf_pages.py
"""
import asyncio
import json
import os
import shutil
import subprocess
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

FIXTURE = os.path.join(_ROOT, "engines", "weaver-core", "probes", "pdf",
                       "pages.pdf")
MARKS = ("alpha", "bravo", "charlie")        # علامةُ الصفحة ١ و٢ و٣
_VENDORED = os.path.join(_ROOT, "engines", "office-core", "vendored")

verdict = {}


def say(s=""):
    print(s, flush=True)


def _import(name, vendored=False):
    """(الوحدة أو None، الإصدار أو سببُ الفشل)."""
    added = False
    if vendored and _VENDORED not in sys.path:
        sys.path.insert(0, _VENDORED)
        added = True
    try:
        m = __import__(name)
        return m, str(getattr(m, "__version__", getattr(m, "VersionBind", "")) or "✓")
    except BaseException as e:      # pypdf قد يرفع PanicException (من Rust)
        return None, "%s: %s" % (type(e).__name__, str(e)[:80])
    finally:
        if added:
            try:
                sys.path.remove(_VENDORED)
            except ValueError:
                pass


def _pages_ok(texts):
    """أفي الصفحة N علامتُها N وحدها؟"""
    if len(texts) != len(MARKS):
        return False, "عددُ الصفحات %d لا %d" % (len(texts), len(MARKS))
    for i, (t, m) in enumerate(zip(texts, MARKS), 1):
        low = (t or "").lower()
        if m not in low:
            return False, "الصفحة %d بلا علامتها" % i
        if any(o in low for o in MARKS if o != m):
            return False, "الصفحة %d فيها علامةُ صفحةٍ أخرى" % i
    return True, "كلُّ صفحةٍ برقمها الصحيح"


# ── ١ المكتبات والبرامج ─────────────────────────────────────────────────
say("\n══ ١) المكتبات والبرامج ══")
libs = {}
for label, mod, vend in (("PyMuPDF (pymupdf)", "pymupdf", False),
                         ("PyMuPDF (fitz)", "fitz", False),
                         ("pymupdf4llm", "pymupdf4llm", False),
                         ("pdfplumber", "pdfplumber", False),
                         ("pdfplumber (مضمَّن في المشروع)", "pdfplumber", True),
                         ("pdfminer.six", "pdfminer", False),
                         ("pypdf", "pypdf", False),
                         ("pytesseract", "pytesseract", False),
                         ("pdf2image", "pdf2image", False),
                         ("paper-qa", "paperqa", False)):
    m, info = _import(mod, vend)
    libs[label] = m
    say("  %s %-32s %s" % ("✓" if m else "✗", label, info if m else "غيرُ مثبَّت"))

for b in ("tesseract", "pdftoppm", "pdftotext"):
    p = shutil.which(b)
    say("  %s %-32s %s" % ("✓" if p else "✗", b + " (برنامج)", p or "غيرُ موجود"))
if shutil.which("tesseract"):
    try:
        out = subprocess.run(["tesseract", "--list-langs"], capture_output=True,
                             text=True, timeout=30)
        langs = (out.stdout + out.stderr).split()
        has_ara = "ara" in langs
        say("    ⟵ لغةُ OCR العربيّة (ara): %s" % ("✓ موجودة" if has_ara
                                               else "✗ غيرُ موجودة"))
        verdict["ocr_ar"] = has_ara
    except Exception as e:
        say("    ⟵ تعذّر سردُ اللغات: %s" % e)
else:
    verdict["ocr_ar"] = False

# ── ٢ قراءةٌ فعليّة صفحةً صفحة ─────────────────────────────────────────
say("\n══ ٢) قراءةُ ملفٍّ من ٣ صفحات — صفحةً صفحة ══")
if not os.path.isfile(FIXTURE):
    say("  ✗ ملفُّ الاختبار غيرُ موجود: " + FIXTURE)
readers = []


def _try(label, fn):
    try:
        texts = fn()
        ok, why = _pages_ok(texts)
    except BaseException as e:
        ok, why = False, "%s: %s" % (type(e).__name__, str(e)[:100])
    say("  %s %-32s %s" % ("✓" if ok else "✗", label, why))
    if ok:
        readers.append(label)


if os.path.isfile(FIXTURE):
    mu = libs.get("PyMuPDF (pymupdf)") or libs.get("PyMuPDF (fitz)")
    if mu:
        _try("PyMuPDF", lambda: [pg.get_text() for pg in mu.open(FIXTURE)])
    if libs.get("pymupdf4llm"):
        _try("pymupdf4llm", lambda: [c.get("text", "") for c in
             libs["pymupdf4llm"].to_markdown(FIXTURE, page_chunks=True)])
    pl = libs.get("pdfplumber") or libs.get("pdfplumber (مضمَّن في المشروع)")
    if pl:
        def _pl():
            with pl.open(FIXTURE) as d:
                return [pg.extract_text() or "" for pg in d.pages]
        _try("pdfplumber", _pl)
    if libs.get("pypdf"):
        _try("pypdf", lambda: [pg.extract_text() or "" for pg in
             libs["pypdf"].PdfReader(FIXTURE).pages])
    if shutil.which("pdftotext"):
        def _ptt():
            out = subprocess.run(["pdftotext", "-layout", FIXTURE, "-"],
                                 capture_output=True, text=True, timeout=60)
            return out.stdout.split("\f")[:len(MARKS)]
        _try("pdftotext", _ptt)

    # قارئُ المشروع نفسُه — هو ما ستعتمد عليه الخطوةُ ١ (لا نعيد بناءه).
    try:
        from capabilities.tools.tool_pdf import PdfTool
        r = asyncio.run(PdfTool().run({"action": "read", "path": FIXTURE}))
        if r.ok:
            texts = [p.get("text", "") for p in (r.data or {}).get("pages", [])]
            ok, why = _pages_ok(texts)
        else:
            ok, why = False, str(r.error)[:120]
    except Exception as e:
        ok, why = False, "%s: %s" % (type(e).__name__, str(e)[:100])
    say("  %s %-32s %s" % ("✓" if ok else "✗", "قارئُ المشروع (tool_pdf)", why))
    verdict["project_reader"] = ok
verdict["readers"] = readers

# ── ٣ PaperQA برقم الصفحة ───────────────────────────────────────────────
say("\n══ ٣) PaperQA (استشهادٌ برقم الصفحة — الطريقُ القديم) ══")
_pq = os.path.join(_ROOT, "engines", "paperqa-core")
if _pq not in sys.path:
    sys.path.insert(0, _pq)
try:
    from paperqa_pages import PagedPaperQA  # noqa: F401
    import paperqa  # noqa: F401
    say("  ✓ paperqa_pages + paper-qa قابلان للاستيراد")
    verdict["paperqa"] = True
except Exception as e:
    say("  ✗ غيرُ قابلٍ للعمل: %s: %s" % (type(e).__name__, str(e)[:100]))
    verdict["paperqa"] = False

# ── ٤ أداةُ pdf في المحرّك ──────────────────────────────────────────────
say("\n══ ٤) أداةُ `pdf` في المحرّك — كما تراها البوّابة ══")
verdict["engine_pdf"] = None
try:
    from pipeline import weaver_core as W
    if not W.available():
        say("  ✗ المحرّكُ غيرُ مركَّب — لم يُقَس")
    else:
        ref = W.model_ref() or ""
        prov = ref.split("/", 1)[0] if "/" in ref else ""
        say("  نموذجُك: %s" % (ref or "؟"))
        say("  قراءةُ PDF أصلاً (أنثروبيك/غوغل فقط): %s"
            % ("✓ نعم" if prov in ("anthropic", "google") else "✗ لا"))
        for path in ("agents.defaults.pdfModel", "agents.defaults.imageModel"):
            c, o, _e = W.run(["config", "get", path], timeout=120)
            v = (o or "").strip()
            say("  %s = %s" % (path, v if (c == 0 and v and v not in
                                            ("null", "undefined")) else "غيرُ مضبوط"))
        if not W.gateway_health():
            say("  ✗ البوّابةُ مطفأة — شغّل الواجهة (weaver serve) ثمّ أعِد. لم يُقَس")
        else:
            def _call(method, params):
                c, o, e = W.run(["gateway", "call", method, "--params",
                                 json.dumps(params), "--json",
                                 "--timeout", "60000"], timeout=180)
                if c != 0:
                    return None, (e or o or "").strip()[:200]
                try:
                    d = json.loads(o)
                except Exception:
                    return None, "خرجٌ غيرُ JSON: " + (o or "")[:120]
                # البوّابةُ قد تخرج بالرمز 0 ومعها {"ok": false, "error": …}
                if isinstance(d, dict) and d.get("ok") is False:
                    er = d.get("error") or {}
                    return None, str(er.get("message") or er)[:200]
                return d, ""

            def _has_pdf(obj):
                s = json.dumps(obj, ensure_ascii=False)
                return ('"name": "pdf"' in s) or ('"id": "pdf"' in s)

            cat, err = _call("tools.catalog", {})
            if cat is None:
                say("  ؟ tools.catalog تعذّر: " + err)
            else:
                verdict["engine_pdf"] = _has_pdf(cat)      # إن لم يُقَس الأدقّ
                say("  %s tools.catalog (فهرسُ أدوات الوكيل): أداةُ pdf %s" % (
                    "✓" if _has_pdf(cat) else "✗",
                    "مُدرَجة" if _has_pdf(cat) else "غيرُ مُدرَجة"))
            # tools.effective يشترط جلسةً موجودة (مقيس: «unknown session key»)
            # ⟵ أحدثُ جلسةٍ حقيقيّةٍ من محادثاتك، لا مفتاحٌ مختلَق.
            key = ""
            c, o, _e = W.run(["sessions", "list", "--json"], timeout=120)
            try:
                ss = (json.loads(o) or {}).get("sessions") or []
                ss.sort(key=lambda s: -(s.get("updatedAt") or 0))
                key = (ss[0].get("key") or "") if ss else ""
            except Exception:
                key = ""
            if not key:
                say("  ؟ tools.effective: لا جلسةَ بعد — أرسل رسالةً من الواجهة"
                    " ثمّ أعِد (الحكمُ أعلاه من الفهرس)")
            else:
                eff, err = _call("tools.effective", {"sessionKey": key})
                if eff is None:
                    say("  ؟ tools.effective تعذّر: " + err)
                else:
                    has = _has_pdf(eff)
                    verdict["engine_pdf"] = has
                    say("  %s tools.effective (ما يراه النموذجُ فعلاً): أداةُ pdf %s"
                        % ("✓" if has else "✗", "ظاهرة" if has else "غيرُ ظاهرة"))
except Exception as e:
    say("  ✗ %s: %s — لم يُقَس" % (type(e).__name__, str(e)[:160]))

# ── الخلاصة ─────────────────────────────────────────────────────────────
say("\n══ الخلاصة ══")
say("  قراءةُ الصفحات برقمها: " + ("✓ ممكنة — " + "، ".join(readers)
                                   if readers else "✗ لا قارئَ يعمل"))
say("  قارئُ المشروع (tool_pdf): " + ("✓ يعمل" if verdict.get("project_reader")
                                     else "✗ لا يعمل"))
say("  OCR عربيّ للملفّات الممسوحة: " + ("✓ ممكن" if verdict.get("ocr_ar")
                                         else "✗ غيرُ ممكن"))
say("  PaperQA برقم الصفحة: " + ("✓ يعمل" if verdict.get("paperqa")
                                 else "✗ لا يعمل"))
_e = verdict.get("engine_pdf")
say("  أداةُ pdf في المحرّك: " + ("✓ ظاهرةٌ للنموذج" if _e is True
                                  else "✗ غيرُ ظاهرة" if _e is False
                                  else "؟ لم يُقَس"))
say("\n  انسخ هذا الخرجَ كلَّه وأرسله.")
