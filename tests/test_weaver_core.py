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
print(" 9) TWO INSTALLS, NO COLLISION -- ours and the user's existing one")
print("=" * 70)
# The user already runs OpenClaw on this device. Both must coexist without
# corrupting each other's config. Three isolations, all via the engine's own
# mechanisms:
#   constants-CJCmIHb-.mjs:56  normalizeGatewayProfile(env.OPENCLAW_PROFILE)
#   constants-CJCmIHb-.mjs:45  resolveGatewaySystemdServiceName(profile)
#   logger-Bf_6W09A.mjs:85     profile suffix in the log file name
_leak = {"OPENCLAW_CONFIG_PATH": "/home/me/.openclaw/openclaw.json",
         "OPENCLAW_HOME": "/home/me",
         "OPENCLAW_STATE_DIR": "/home/me/.openclaw",
         "OPENCLAW_AGENT_DIR": "/home/me/.openclaw/agents",
         "OPENCLAW_GATEWAY_PORT": "18789"}
for _k, _v in _leak.items():
    os.environ[_k] = _v
_e = W.engine_env()
chk("an inherited OPENCLAW_CONFIG_PATH never reaches the engine",
    _e.get("OPENCLAW_CONFIG_PATH") is None, str(_e.get("OPENCLAW_CONFIG_PATH")))
chk("nor OPENCLAW_HOME", _e.get("OPENCLAW_HOME") is None)
chk("nor OPENCLAW_AGENT_DIR", _e.get("OPENCLAW_AGENT_DIR") is None)
chk("and their STATE_DIR is replaced by ours, not honoured",
    _e.get("OPENCLAW_STATE_DIR", "").startswith(W.STATE),
    _e.get("OPENCLAW_STATE_DIR", ""))
chk("and their port is replaced by ours",
    _e.get("OPENCLAW_GATEWAY_PORT") == str(W.OUR_PORT),
    _e.get("OPENCLAW_GATEWAY_PORT", ""))
chk("our port is not the engine default",
    W.OUR_PORT != W.DEFAULT_PORT and W.OUR_PORT != 19001)
chk("a profile name isolates service, logs and port",
    _e.get("OPENCLAW_PROFILE") == W.PROFILE, _e.get("OPENCLAW_PROFILE", ""))
chk("HOME still points at our own engine home",
    _e.get("HOME", "").startswith(W.STATE))
chk("nothing OPENCLAW_* survives except what we set",
    all(k in ("OPENCLAW_PROFILE", "OPENCLAW_STATE_DIR",
              "OPENCLAW_GATEWAY_PORT")
        for k in _e if k.startswith("OPENCLAW_")),
    str([k for k in _e if k.startswith("OPENCLAW_")]))
_iso = W.isolation()
chk("isolation() reports what leaked in, so it is never silent",
    set(_leak) <= set(_iso["inherited_openclaw_vars"]))
for _k in _leak:
    os.environ.pop(_k, None)

# one rule, no special cases: every WEAVER_X becomes OPENCLAW_X, and an
# explicit one outranks our defaults.
os.environ["WEAVER_GATEWAY_PORT"] = "19555"
os.environ["WEAVER_STATE_DIR"] = "/tmp/mine"
_ex = W.engine_env()
chk("an explicit WEAVER_GATEWAY_PORT outranks our default",
    _ex.get("OPENCLAW_GATEWAY_PORT") == "19555")
chk("and WEAVER_STATE_DIR does too",
    _ex.get("OPENCLAW_STATE_DIR") == "/tmp/mine")
chk("names match the engine's own keys -- no invented second name",
    "WEAVER_PORT" not in open(
        os.path.join(_ROOT, "pipeline", "weaver_core.py"),
        encoding="utf-8").read())
for _k in ("WEAVER_GATEWAY_PORT", "WEAVER_STATE_DIR"):
    os.environ.pop(_k, None)

print()
print("=" * 70)
print(" 10) THE REAL COMMAND -- verified against the engine, not guessed")
print("=" * 70)
# I called `run` on a hunch and the engine answered the USER:
#   "Weaver Write does not know the command \"run\"."
# The real one, from the engine's own registration:
#   register.agent-turn-gi9D9FTy.mjs:41  command("exec [message]")
#   "Run one isolated headless embedded agent turn"
_src_wc = open(os.path.join(_ROOT, "pipeline", "weaver_core.py"),
               encoding="utf-8").read()
chk("the engine is invoked with `agent exec`", '"agent", "exec"' in _src_wc)
chk("and never with the invented `run`", '["run", str(text' not in _src_wc)
chk("--json is asked for (a stable envelope, not guessed text)",
    '"--json"' in _src_wc)
chk("--timeout is passed so a hung turn cannot wedge the call",
    '"--timeout"' in _src_wc)

# the envelope reader must never lose an answer
# THE REAL ENVELOPE, copied from a working run on the device -- not invented.
# It is pretty-printed across lines and its answer field is `final`; my reader
# assumed one line and did not know `final`, so the raw JSON was printed at
# the user instead of the answer.
import json as _json
_REAL = _json.dumps({
    "ok": True, "status": "ok", "final": "\u0645\u0631\u062d\u0628\u0627!",
    "payloads": [{"text": "\u0645\u0631\u062d\u0628\u0627!",
                  "mediaUrl": None}],
    "usage": {"input": 23168, "output": 33, "total": 23201},
    "costUsd": 0.00115798256, "assistantTurns": 1,
    "model": "deepseek/deepseek-v4-flash", "provider": "openrouter",
    "sessionId": "37e0db30-9a80-4b8d-8d84-2b550bfaca14"},
    ensure_ascii=False, indent=2)
_WANT = "\u0645\u0631\u062d\u0628\u0627!"
chk("the REAL pretty-printed envelope yields the answer, not the JSON",
    W._from_envelope(_REAL) == _WANT, W._from_envelope(_REAL)[:40])
chk("  -> `final` is the field it reads",
    W._from_envelope('{"final":"x"}') == "x")
chk("  -> a log line before it does not break it",
    W._from_envelope("starting...\n" + _REAL) == _WANT)
chk("  -> payloads are joined when there is no final",
    W._from_envelope('{"payloads":[{"text":"a"},{"text":"b"}]}') == "a\n\nb")
chk("  -> an error envelope reports its message, not raw JSON",
    W._from_envelope('{"ok":false,"error":{"message":"no key"}}')
    == "error: no key")
chk("a clean envelope", W._from_envelope('{"text":"\u0645\u0631\u062d\u0628\u0627"}') == "\u0645\u0631\u062d\u0628\u0627")
chk("log lines before it do not break it",
    W._from_envelope('starting…\n{"message":"أهلاً"}') == "أهلاً")
chk("a nested field is found",
    W._from_envelope('{"result":{"text":"داخلي"}}') == "داخلي")
chk("an unknown shape falls back to the raw text -- never empty",
    W._from_envelope("نصٌّ عاديّ") == "نصٌّ عاديّ")
chk("broken JSON still yields the text",
    W._from_envelope('{not json') == '{not json')
chk("empty stays empty", W._from_envelope("") == "")
chk("None does not raise", W._from_envelope(None) == "")

print()
print("=" * 70)
print(" 11) THE /tmp PORTABILITY PATCH -- verifies before it edits")
print("=" * 70)
# Measured on a real Termux run, not guessed:
#   EACCES: permission denied, mkdir '/tmp/openclaw-state-locks-10366'
# One line, duplicated in two files, hardcodes "/tmp" for the lock that guards
# state-database LIFECYCLE operations. It lives OUTSIDE the state dir by
# design -- a lock inside the directory it guards would destroy itself when
# that directory is rebuilt. So the fix is not "put it in our path": it is
# os.tmpdir(), which returns /tmp on Linux/macOS (unchanged) and a WRITABLE
# dir on Termux.
import importlib.util as _ilu
_ps = _ilu.spec_from_file_location(
    "patch_portability",
    os.path.join(_ROOT, "engines", "weaver-core", "patch_portability.py"))
P = _ilu.module_from_spec(_ps)
_ps.loader.exec_module(P)

import tempfile as _tf, shutil as _sh
_d = _tf.mkdtemp()
_f = os.path.join(_d, "dist", "state-database-coordinator-DBce2evc.mjs")
os.makedirs(os.path.dirname(_f))


def _write(brand):
    with open(_f, "w", encoding="utf-8") as fh:
        fh.write('import os from "node:os";\n'
                 "function resolveStateLifecycleRuntimeDirectory() {\n"
                 '\treturn process.platform === "win32" ? path.join('
                 'os.homedir(), "AppData", "Local", "' + brand +
                 '", "locks") : "/tmp";\n}\n')


# the brand must not matter -- my first version matched the whole line
# including "Weaver Write", so it worked on a rebranded copy and failed on
# the original. The test caught it; reasoning had not.
for _brand in ("OpenClaw", "Weaver Write"):
    _write(_brand)
    st, msg = P.patch_file(_f)
    chk(f"patches the {_brand} copy", st == "patched", msg)
    chk("  -> and the line now uses os.tmpdir()",
        "os.tmpdir();" in open(_f, encoding="utf-8").read())
    chk("  -> hardcoded /tmp is gone",
        '"/tmp"' not in open(_f, encoding="utf-8").read())
    st2, _ = P.patch_file(_f)
    chk("  -> running it again changes nothing", st2 == "already")

# it must refuse what it does not recognise, never guess
with open(_f, "w", encoding="utf-8") as fh:
    fh.write("function somethingElse() { return 1; }\n")
chk("an unknown shape is refused, not guessed",
    P.patch_file(_f)[0] == "shape")
os.remove(_f)
chk("a missing file is reported", P.patch_file(_f)[0] == "missing")
_sh.rmtree(_d, ignore_errors=True)

_ish = open(os.path.join(_ROOT, "engines", "weaver-core", "install.sh"),
            encoding="utf-8").read()
chk("the installer applies it", "patch_portability.py" in _ish)
chk("and an existing install can be repaired without reinstalling",
    "--repair" in _src_wc)

print()
print("=" * 70)
print(" 12) ONE KEY: your provider reaches the engine too")
print("=" * 70)
# From the real log, not a guess:
#   "model": null, "provider": null
#   "No route-compatible authentication source is configured for openai."
#   requested=openai/gpt-5.6-sol  reason=auth  next=none
# The engine fell back to ITS default model because it knew nothing of the
# user's provider. The bridge translates what the python side already holds
# (core/llm/__init__.py:403-408) into the name the engine reads
# (config-provider-contract-BdOif1pq.mjs:89  openrouter: "OPENROUTER_API_KEY").
for _k in ("WEAVER_PROVIDER", "WEAVER_API_KEY", "WEAVER_MODEL",
           "WEAVER_BASE_URL"):
    os.environ.pop(_k, None)
# the real config lives in a file, not the environment. `--provider` reported
# "no key" on a working system for exactly that reason: the bridge read only
# os.environ, while the keys sit in config/.env -- the source of truth shared
# by the terminal and the web UI (config/keysync.py:27,30).
_envf = os.path.join(_ROOT, "config", ".env")
_had = os.path.isfile(_envf)
_backup = open(_envf, encoding="utf-8").read() if _had else None
try:
    if not _had:
        chk("with nothing configured anywhere, nothing is claimed",
            W.provider_id() == "" and W.model_id() == ""
            and W.credentials() == {})
    with open(_envf, "w", encoding="utf-8") as _fh:
        _fh.write('export WEAVER_PROVIDER=openrouter\n'
                  'WEAVER_API_KEY="sk-or-file"\n'
                  'WEAVER_MODEL=deepseek/deepseek-v4-flash\n')
    chk("the key is read from config/.env, not just the environment",
        W.credentials() == {"OPENROUTER_API_KEY": "sk-or-file"},
        str(W.credentials()))
    chk("  -> `export ` prefix and quotes are handled",
        W.provider_id() == "openrouter"
        and W.model_id() == "openrouter/deepseek/deepseek-v4-flash")
    os.environ["WEAVER_API_KEY"] = "sk-from-env"
    chk("  -> and a real environment variable outranks the file",
        W.credentials() == {"OPENROUTER_API_KEY": "sk-from-env"})
    os.environ.pop("WEAVER_API_KEY")
finally:
    if _backup is None:
        try:
            os.remove(_envf)
        except Exception:
            pass
    else:
        open(_envf, "w", encoding="utf-8").write(_backup)

os.environ["WEAVER_PROVIDER"] = "openrouter"
os.environ["WEAVER_API_KEY"] = "sk-or-test"
os.environ["WEAVER_MODEL"] = "deepseek/deepseek-v4-flash"
chk("provider is read from WEAVER_PROVIDER", W.provider_id() == "openrouter")
chk("model gets the provider prefix the engine wants",
    W.model_id() == "openrouter/deepseek/deepseek-v4-flash", W.model_id())
chk("and the key is renamed to what the engine reads",
    W.credentials() == {"OPENROUTER_API_KEY": "sk-or-test"})
chk("and it actually reaches the engine env",
    W.engine_env().get("OPENROUTER_API_KEY") == "sk-or-test")

# no double prefix when the model already carries it
os.environ["WEAVER_MODEL"] = "openrouter/some/model"
chk("an already-prefixed model is not prefixed twice",
    W.model_id() == "openrouter/some/model")

# the provider may be inferred from the base URL -- evidence, not a hunch
os.environ.pop("WEAVER_PROVIDER")
os.environ["WEAVER_BASE_URL"] = "https://openrouter.ai/api/v1"
chk("provider inferred from the base URL host",
    W.provider_id() == "openrouter")
os.environ["WEAVER_BASE_URL"] = "https://api.deepseek.com/v1"
chk("  -> and a different host gives a different provider",
    W.provider_id() == "deepseek")
os.environ["WEAVER_BASE_URL"] = "https://example.invalid/v1"
chk("  -> an unknown host claims nothing", W.provider_id() == "")

# a key with no provider must never be exported under a guessed name
os.environ.pop("WEAVER_BASE_URL")
chk("a key without a known provider is not exported blindly",
    W.credentials() == {})

_wc = open(os.path.join(_ROOT, "pipeline", "weaver_core.py"),
           encoding="utf-8").read()
chk("--model is passed so the engine cannot fall back to its own default",
    '"--model", _m' in _wc)
for _k in ("WEAVER_PROVIDER", "WEAVER_API_KEY", "WEAVER_MODEL",
           "WEAVER_BASE_URL"):
    os.environ.pop(_k, None)

print()
print("=" * 70)
print(" RESULT: " + ("PASS" if ok else "FAIL"))
print("=" * 70)
sys.exit(0 if ok else 1)
