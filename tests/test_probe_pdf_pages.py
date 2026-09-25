# -*- coding: utf-8 -*-
"""أداةُ القياس tools/probe_pdf_pages.py: تعمل بلا مكتبات وبلا محرّك، ولا
تكتب شيئاً، وقسمُ المحرّك يقرأ جوابَ البوّابة كما هو (محاكاة)."""
import io
import json
import os
import runpy
import sys
from contextlib import redirect_stdout

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)
from pipeline import weaver_core as W   # noqa: E402

P = F = 0
SCRIPT = os.path.join(_ROOT, "tools", "probe_pdf_pages.py")
FIX = os.path.join(_ROOT, "engines", "weaver-core", "probes", "pdf",
                   "pages.pdf")


def ok(name, cond, extra=""):
    global P, F
    if cond:
        P += 1
        print(f"  ✓ {name}")
    else:
        F += 1
        print(f"  ✗ {name}" + (f"   — {extra}" if extra else ""))


def run_probe():
    buf = io.StringIO()
    with redirect_stdout(buf):
        runpy.run_path(SCRIPT, run_name="__main__")
    return buf.getvalue()


ok("ملفُّ الاختبار موجود (٣ صفحات)", os.path.isfile(FIX)
   and open(FIX, "rb").read().count(b"/Type /Page ") == 3)
_before = sorted(os.listdir(os.path.join(_ROOT, "config")))

_real = {n: getattr(W, n) for n in ("available", "model_ref", "run",
                                    "gateway_health")}
_calls = []
try:
    W.available = lambda: False
    out = run_probe()
    ok("بلا محرّك ⟵ «لم يُقَس» لا حكم", "لم يُقَس" in out
       and "المحرّكُ غيرُ مركَّب" in out)
    ok("والخلاصةُ تُطبع", "══ الخلاصة ══" in out)

    W.available = lambda: True
    W.model_ref = lambda: "weaver/deepseek-v4-pro"
    W.gateway_health = lambda timeout=2: True

    def _run(args, timeout=180, **kw):
        _calls.append(args)
        if args[:2] == ["config", "get"]:
            return 0, "null\n", ""
        if args[:3] == ["gateway", "call", "tools.catalog"]:
            return 0, json.dumps({"groups": [{"tools": [
                {"name": "pdf"}, {"name": "exec"}]}]}), ""
        if args[:2] == ["sessions", "list"]:
            return 0, json.dumps({"sessions": [
                {"key": "agent:main:explicit:old", "updatedAt": 1},
                {"key": "agent:main:explicit:new", "updatedAt": 9}]}), ""
        if args[:3] == ["gateway", "call", "tools.effective"]:
            return 0, json.dumps({"tools": [{"name": "exec"},
                                            {"name": "web_fetch"}]}), ""
        return 1, "", "?"
    W.run = _run
    out = run_probe()
    ok("DeepSeek ⟵ لا قراءةَ PDF أصليّة", "✗ لا" in out)
    ok("pdfModel/imageModel غيرُ مضبوطَين", out.count("غيرُ مضبوط") == 2)
    ok("catalog: مُدرَجة", "أداةُ pdf مُدرَجة" in out)
    ok("effective: غيرُ ظاهرة ⟵ هو الحكم", "✗ غيرُ ظاهرة" in out, out[-400:])
    eff = [a for a in _calls if a[:3] == ["gateway", "call", "tools.effective"]]
    ok("tools.effective بأحدث جلسةٍ حقيقيّة (لا مفتاحٌ مختلَق)",
       eff and json.loads(eff[0][4])["sessionKey"]
       == "agent:main:explicit:new")

    # بلا جلسات ⟵ لا tools.effective، والحكمُ من الفهرس معلَنٌ كذلك.
    _calls.clear()
    _r0 = W.run
    W.run = lambda a, timeout=180, **k: ((0, json.dumps({"sessions": []}), "")
                                        if a[:2] == ["sessions", "list"]
                                        else _r0(a, timeout))
    out = run_probe()
    ok("بلا جلسة ⟵ يقول ذلك، والحكمُ من الفهرس",
       "لا جلسةَ بعد" in out and "✓ ظاهرةٌ للنموذج" in out, out[-500:])
    # والبوّابةُ تخرج بالرمز 0 ومعها ok:false ⟵ خطأٌ لا «غيرُ مُدرَجة».
    W.run = lambda a, timeout=180, **k: ((0, json.dumps({"ok": False, "error": {
        "message": "gateway tools.catalog requires credentials"}}), "")
        if a[:2] == ["gateway", "call"] else _r0(a, timeout))
    out = run_probe()
    ok("ok:false ⟵ «تعذّر» بالسبب، لا حكمٌ كاذب",
       "tools.catalog تعذّر: gateway tools.catalog requires credentials" in out
       and "؟ لم يُقَس" in out, out[-500:])
    W.run = _r0
    ok("لا أمرَ كتابة (config set/patch) ولا تثبيت",
       not any(a[:2] in (["config", "set"], ["config", "patch"])
               for a in _calls))

    W.gateway_health = lambda timeout=2: False
    out = run_probe()
    ok("بوّابةٌ مطفأة ⟵ يقول ذلك ولا يحكم", "البوّابةُ مطفأة" in out
       and "؟ لم يُقَس" in out)
finally:
    for n, f in _real.items():
        setattr(W, n, f)
ok("لم يُكتب شيءٌ في config/", sorted(os.listdir(
    os.path.join(_ROOT, "config"))) == _before)

print("\n" + "=" * 62)
print(f" RESULT: {'PASS' if F == 0 else 'FAIL'}   ({P}/{P + F})")
print("=" * 62)
sys.exit(1 if F else 0)
