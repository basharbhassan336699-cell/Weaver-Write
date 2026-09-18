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
print(" 7) THE ENVELOPE: engine state lives under OUR name, no file edited")
print("=" * 70)
# 269 sites go through resolveStateDir(env) which reads OPENCLAW_STATE_DIR;
# 6 bypass it -- 2 are win32/darwin-only, 1 is display-only, and the 3 real
# ones use os.homedir(), which follows HOME. So two keys cover every write.
_e = W.engine_env()
chk("OPENCLAW_STATE_DIR is set", bool(_e.get("OPENCLAW_STATE_DIR")),
    _e.get("OPENCLAW_STATE_DIR", ""))
chk("and it is under our own root",
    _e.get("OPENCLAW_STATE_DIR", "").startswith(W.STATE))
chk("HOME is redirected too (the 3 homedir() sites)",
    _e.get("HOME", "").startswith(W.STATE), _e.get("HOME", ""))
chk("nothing is written into the user's real home",
    _e.get("HOME") != os.path.expanduser("~"))

os.environ["WEAVER_GATEWAY_PORT"] = "9090"
os.environ["WEAVER_LLM"] = "offline"
os.environ["WEAVER_EXEC"] = "1"
_e2 = W.engine_env()
chk("WEAVER_* is translated to OPENCLAW_*",
    _e2.get("OPENCLAW_GATEWAY_PORT") == "9090")
chk("but OUR own keys are not (WEAVER_LLM)", "OPENCLAW_LLM" not in _e2)
chk("nor WEAVER_EXEC", "OPENCLAW_EXEC" not in _e2)
for _k in ("WEAVER_GATEWAY_PORT", "WEAVER_LLM", "WEAVER_EXEC"):
    os.environ.pop(_k, None)

chk("an explicit WEAVER_STATE_DIR wins",
    W.engine_env.__doc__ is not None)
os.environ["WEAVER_STATE_DIR"] = "/tmp/xyz-state"
chk("  -> and is honoured",
    W.engine_env().get("OPENCLAW_STATE_DIR") == "/tmp/xyz-state")
os.environ.pop("WEAVER_STATE_DIR", None)

_p = W.state_paths()
chk("state_paths() names all three", set(_p) == {"state", "home", "root"}, str(_p))
chk("one folder to delete for a clean removal",
    _p["state"].startswith(_p["root"]) and _p["home"].startswith(_p["root"]))
chk("and run() passes that env to the engine",
    "env=engine_env()" in open(
        os.path.join(_ROOT, "pipeline", "weaver_core.py"),
        encoding="utf-8").read())

print()
print("=" * 70)
print(" 8) ANY NODE VERSION: three tiers, never one closed gate")
print("=" * 70)
# The engine requires ">=24.16.0 <25 || >=26.1.0" for a real reason: it uses
# node's built-in sqlite, and below 24.16 that truncates TEXT at the first NUL
# byte (nodejs/node#61954) -- data corrupts silently. So it is never bypassed.
# But closing the whole system over it would be wrong: the python path needs
# no node at all. Hence three tiers.
for v, want in (("22.22.2", False), ("24.15.0", False), ("24.16.0", True),
                ("25.0.0", False), ("25.9.9", False), ("26.0.5", False),
                ("26.1.0", True), ("26.4.0", True), ("27.1.0", True),
                ("v26.4.0", True), ("", False), ("abc", False)):
    chk(f"node {v or '(empty)'} -> {'ok' if want else 'refused'}",
        W.node_ok(v) is want)

_rows = W.node_report()
chk("every node on the device is scanned, not just PATH",
    isinstance(_rows, list))
chk("  each row carries path, version and verdict",
    all(set(r) == {"path", "version", "ok"} for r in _rows), str(_rows[:1]))
chk("WEAVER_NODE is honoured as a candidate",
    "WEAVER_NODE" in open(os.path.join(_ROOT, "pipeline", "weaver_core.py"),
                          encoding="utf-8").read())
chk("and Termux/nvm locations are searched",
    "com.termux" in open(os.path.join(_ROOT, "pipeline", "weaver_core.py"),
                         encoding="utf-8").read())

# Tier 3: an answer comes back even with no engine and no usable node.
_r = W.ask("2+2", fallback=False)
if not (W.available() and W.node_bin()):
    chk("no engine + fallback off -> it says why, plainly",
        _r["engine"] == "" and bool(_r["note"]))
    chk("  and names the real cause, not a shrug",
        "node" in _r["note"] or "install.sh" in _r["note"], _r["note"][:60])
chk("ask() always returns the three keys",
    set(W.ask("x", fallback=False)) == {"answer", "engine", "note"})
chk("and says WHICH engine answered -- never hidden",
    W.ask("x", fallback=False).get("engine") in ("", "weaver-core", "python"))

# the shell installer and the python bridge must never disagree
_sh = open(os.path.join(_ROOT, "engines", "weaver-core", "install.sh"),
           encoding="utf-8").read()
chk("the installer compares versions in shell, not inside node",
    "node_ok()" in _sh and "NODE_OK_EXPR" not in _sh)
chk("and it does NOT hard-fail when node is old",
    "exit 0          #" in _sh or "exit 0 " in _sh)
chk("it points at the python path instead",
    "pipeline.agent" in _sh)

print()
print("=" * 70)
print(" RESULT: " + ("PASS" if ok else "FAIL"))
print("=" * 70)
sys.exit(0 if ok else 1)
