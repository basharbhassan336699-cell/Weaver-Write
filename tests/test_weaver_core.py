# -*- coding: utf-8 -*-
"""محرّك Weaver Write: إعادةُ التسمية والجسر.

المحرّكُ هو حزمةُ openclaw بعينها (MIT) مُعادةَ التسمية. والخطرُ كلُّه في
إعادة التسمية: الكلمةُ تظهر ٦٢٩٣ مرّةً، وليست كلُّها علامةً — منها أسماءُ
حزمٍ يحلُّها node، ومُعرِّفاتٌ في الكود، ومتغيّراتُ بيئة. تبديلُ واحدٍ منها
يعني انهيارَ كلِّ شيء. وهذه الاختباراتُ تُثبت الحدَّ في الاتجاهين."""
import sys, os, importlib.util
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
for k in list(os.environ):
    if k.startswith("WEAVER_"):
        os.environ.pop(k)
_spec = importlib.util.spec_from_file_location(
    "rebrand", os.path.join(_ROOT, "engines", "weaver-core", "rebrand.py"))
R = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(R)
from pipeline import weaver_core as W
ok = True

ESC = chr(27)


def chk(label, good, detail=""):
    global ok
    ok &= bool(good)
    print(f"   {'OK ' if good else 'XX '} {label}" + (f" - {detail}" if detail else ""))


print("=" * 70)
print(" 1) THE VISIBLE BRAND IS REPLACED")
print("=" * 70)
for src, want in (
        ('"OpenClaw 2026.9.4"', '"Weaver Write 2026.9.4"'),
        ("# OpenClaw Installer", "# Weaver Write Installer"),
        ("one OpenClaw.", "one Weaver Write."),
        ("(OpenClaw)", "(Weaver Write)")):
    chk(src[:34], R.rebrand_text(src) == want, R.rebrand_text(src)[:40])

print()
print("=" * 70)
print(" 2) AND A TEXT ESCAPE DOES NOT LET IT SLIP -- this is what --help hit")
print("=" * 70)
chk(r"\nOpenClaw  (precomputed help text)",
    R.rebrand_text(r"\nOpenClaw 2026") == r"\nWeaver Write 2026")
chk(r"\tOpenClaw", R.rebrand_text(r"\tOpenClaw x") == r"\tWeaver Write x")
chk("an ANSI colour code ending in m",
    R.rebrand_text(ESC + "[1mOpenClaw" + ESC + "[0m")
    == ESC + "[1mWeaver Write" + ESC + "[0m")

print()
print("=" * 70)
print(" 3) AND WHAT THE RUNTIME RESOLVES IS NEVER TOUCHED -- the fatal line")
print("=" * 70)
for s in ("@openclaw/ai", "@openclaw/agent-core", "import '@openclaw/fs-safe'",
          "isSupportedOpenClawNodeVersion", "inspectOpenClawAgentDatabaseOwner",
          "OpenClawAbortableWrapper", "OPENCLAW_AGENT_DIR",
          "process.env.OPENCLAW_CONTAINER", "~/.openclaw/config",
          "openclaw.json", "openclaw.sqlite", "openclaw.plugin"):
    chk(s, R.rebrand_text(s) == s, R.rebrand_text(s))

print()
print("=" * 70)
print(" 4) LICENCE AND NOTICES PROTECTED BY NAME -- the MIT condition")
print("=" * 70)
chk("LICENSE excluded", "LICENSE" in R.SKIP_FILES)
chk("THIRD_PARTY_NOTICES.md excluded", "THIRD_PARTY_NOTICES.md" in R.SKIP_FILES)
chk("node_modules untouched", "node_modules" in R.SKIP_DIRS)
_notice = os.path.join(_ROOT, "engines", "weaver-core", "NOTICE.md")
chk("an attribution notice exists", os.path.isfile(_notice))
_n = open(_notice, encoding="utf-8").read() if os.path.isfile(_notice) else ""
chk("naming source, licence and copyright holder",
    "openclaw" in _n and "MIT" in _n and "OpenClaw Foundation" in _n)

print()
print("=" * 70)
print(" 5) AND THE EXTENSIONS COVER WHAT USED TO SLIP")
print("=" * 70)
for e in (".mjs", ".js", ".json", ".md", ".sh", ".html", ".webmanifest"):
    chk(e, e in R.EXT)

print()
print("=" * 70)
print(" 6) AND THE BRIDGE TELLS THE TRUTH WHEN THE ENGINE IS ABSENT")
print("=" * 70)
chk("available() never raises", isinstance(W.available(), bool))
if not W.available():
    chk("absence is stated with its cause",
        "install.sh" in W.why_unavailable() or "nodejs" in W.why_unavailable(),
        W.why_unavailable()[:70])
    c, o, e = W.run(["--version"])
    chk("a call with no engine returns 127, not a crash", c == 127 and bool(e))
    chk('version() returns ""', W.version() == "")
else:
    chk("installed -> reports the new name",
        "Weaver Write" in W.version(), W.version())
chk("the python path stays and does not depend on it",
    __import__("pipeline.agent", fromlist=["ask"]) is not None)

print()
print("=" * 70)
print(" RESULT: " + ("PASS" if ok else "FAIL"))
print("=" * 70)
sys.exit(0 if ok else 1)
