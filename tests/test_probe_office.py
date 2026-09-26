# -*- coding: utf-8 -*-
"""أداةُ القياس tools/probe_office.py، وإصلاحُ العربيّ المقلوب في الرسوم.

قِيس: matplotlib 3.11 (مبنيٌّ بـ libraqm) يشكّل العربيَّ ويرتّبه بنفسه، وكان
build_chart يشكّله مرّةً ثانية (arabic-reshaper + get_display) ⟵ «عنوان» يظهر
مقلوباً بحروفٍ منفصلة. الآن يُمرَّر كما هو حين يشكّل matplotlib بنفسه، ويبقى
التشكيلُ القديمُ كما كان حرفاً للإصدارات الأقدم (3.10 قِيس: صحيح).
"""
import os
import subprocess
import sys
import tempfile
import types

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)
SCRIPT = os.path.join(_ROOT, "tools", "probe_office.py")
_CHART = os.path.join(_ROOT, "capabilities", "skills", "chart_builder", "scripts")

P = F = 0


def ok(name, cond, extra=""):
    global P, F
    if cond:
        P += 1
        print(f"  ✓ {name}")
    else:
        F += 1
        print(f"  ✗ {name}" + (f"   — {extra}" if extra else ""))


def probe(*args, env_extra=None):
    env = dict(os.environ)
    env.update(env_extra or {})
    r = subprocess.run([sys.executable, SCRIPT, *args], capture_output=True,
                       text=True, timeout=600, cwd=_ROOT, env=env)
    return r.returncode, r.stdout + r.stderr


def _tree():
    out = set()
    for dp, dns, fns in os.walk(_ROOT):
        dns[:] = [d for d in dns if d not in (".git", "__pycache__", "node_modules",
                                              "runtime")]
        for fn in fns:
            fp = os.path.join(dp, fn)
            try:
                out.add((fp, os.path.getmtime(fp)))
            except OSError:
                pass
    return out


def _tmp_probe_dirs():
    t = tempfile.gettempdir()
    return {d for d in os.listdir(t) if d.startswith("weaver-office-")}


print("\n— الأداةُ تقيس ولا تكتب —")
before, tmp_before = _tree(), _tmp_probe_dirs()
code, out = probe()
ok("تعمل وتطبع الخلاصة", code == 0 and "══ الخلاصة ══" in out, out[-600:])
ok("لا تكتب شيئاً في المشروع (ولا config)", _tree() == before,
   sorted(p for p, _ in _tree() ^ before)[:5])
ok("ولا تترك مجلّداً مؤقّتاً", _tmp_probe_dirs() == tmp_before,
   _tmp_probe_dirs() - tmp_before)
for lib, line in (("docx", "Word عربيّ (build_docx)"),
                  ("pptx", "PowerPoint عربيّ (build_pptx)"),
                  ("openpyxl", "Excel عربيّ (build_xlsx)")):
    try:
        __import__(lib)
        ok("%s مثبَّت ⟵ «%s» يُبنى ويُتحقَّق منه" % (lib, line), "✓ " + line in out,
           [ln for ln in out.splitlines() if line in ln])
    except ImportError:
        pass
ok("الملفُّ المرفوع: يُقال بالدليل هل يُحفظ في مجلّد العمل",
   "الملفُّ المرفوع يُحفظ في مجلّد العمل" in out)
ok("المقارنةُ بأوبن كلاو تُقال", "مهاراتُ أوبن كلاو المضمَّنة" in out)

print("\n— مكتبةٌ ناقصة ⟵ «لم يُقَس» لا انهيار —")
blk = tempfile.mkdtemp()
for m in ("docx", "pptx"):
    open(os.path.join(blk, m + ".py"), "w").write(
        "raise ImportError('blocked for test')\n")
code, out2 = probe(env_extra={"PYTHONPATH": blk})
ok("تعمل حتى النهاية", code == 0 and "══ الخلاصة ══" in out2, out2[-400:])
ok("Word ⟵ «لم يُقَس — python-docx غيرُ مثبَّت»",
   "لم يُقَس — python-docx غيرُ مثبَّت" in out2)
ok("PowerPoint ⟵ «لم يُقَس — python-pptx غيرُ مثبَّت»",
   "لم يُقَس — python-pptx غيرُ مثبَّت" in out2)
ok("  ⟵ والمكتبةُ الناقصة ✗ في الخلاصة", "✗ python-docx (Word)" in out2)

print("\n— --keep ينسخ النماذجَ لتراها —")
keep = tempfile.mkdtemp()
code, out3 = probe("--keep", keep)
got = sorted(os.listdir(keep))
try:
    import docx  # noqa: F401
    ok("النماذجُ منسوخة", code == 0 and "word-ar.docx" in got, got)
except ImportError:
    ok("بلا مكتبات ⟵ لا يفشل", code == 0)

print("\n— build_chart: لا تشكيلَ ثانٍ للعربيّ —")
sys.path.insert(0, _CHART)
import build_chart as bc   # noqa: E402

AR = "عنوان"
_real_native = bc._native_shaping
_saved = {k: sys.modules.get(k) for k in ("arabic_reshaper", "bidi",
                                          "bidi.algorithm")}
try:
    fake_r = types.ModuleType("arabic_reshaper")
    fake_r.reshape = lambda s: "R(" + s + ")"
    fake_b = types.ModuleType("bidi")
    fake_ba = types.ModuleType("bidi.algorithm")
    fake_ba.get_display = lambda s: "D(" + s + ")"
    fake_b.algorithm = fake_ba
    sys.modules.update({"arabic_reshaper": fake_r, "bidi": fake_b,
                        "bidi.algorithm": fake_ba})
    bc._native_shaping = lambda: True
    ok("matplotlib يشكّل بنفسه ⟵ النصُّ كما هو",
       bc._reshape_ar([AR, "abc"]) == [AR, "abc"])
    bc._native_shaping = lambda: False
    ok("لا يشكّل (إصدارٌ أقدم) ⟵ التشكيلُ القديمُ كما كان حرفاً",
       bc._reshape_ar([AR, "abc"]) == ["D(R(" + AR + "))", "abc"])
finally:
    bc._native_shaping = _real_native
    for k, v in _saved.items():
        if v is None:
            sys.modules.pop(k, None)
        else:
            sys.modules[k] = v

_ft = types.ModuleType("matplotlib.ft2font")
_mpl = sys.modules.get("matplotlib")
_saved_ft = sys.modules.get("matplotlib.ft2font")
try:
    if _mpl is None:
        sys.modules["matplotlib"] = types.ModuleType("matplotlib")
    _ft.__libraqm_version__ = "0.10.5"
    sys.modules["matplotlib.ft2font"] = _ft
    sys.modules["matplotlib"].ft2font = _ft
    ok("__libraqm_version__ ⟵ يشكّل بنفسه", bc._native_shaping() is True)
    _ft.__libraqm_version__ = ""
    ok("بلا libraqm ⟵ لا", bc._native_shaping() is False)
finally:
    if _saved_ft is None:
        sys.modules.pop("matplotlib.ft2font", None)
    else:
        sys.modules["matplotlib.ft2font"] = _saved_ft
    if _mpl is None:
        sys.modules.pop("matplotlib", None)
    elif _saved_ft is not None:
        _mpl.ft2font = _saved_ft

print("\n" + "=" * 62)
print(f" RESULT: {'PASS' if F == 0 else 'FAIL'}   ({P}/{P + F})")
print("=" * 62)
sys.exit(1 if F else 0)
