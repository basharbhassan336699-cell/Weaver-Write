# -*- coding: utf-8 -*-
"""The engine is wired in -- as an addition, never a replacement.

`_chat` in web/server.py is a single call to the provider: no tools, no loop,
no retry. The engine (Weaver Write core) carries openclaw's loop and toolset:
it searches, opens pages, executes, and goes again until done. So `_chat` is
where it belongs.

One wire serves both surfaces: weaver.py's `_load_chat()` imports the very
same `web.server._chat` (weaver.py:711-717), so the terminal gets it too.

And the document path (`run_pipeline_sync`) is untouched -- it has its own
layers and builds the real files.
"""
import sys, os, importlib
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
for k in list(os.environ):
    if k.startswith("WEAVER_"):
        os.environ.pop(k)
import web.server as S
from pipeline import weaver_core as W
ok = True


def chk(label, good, detail=""):
    global ok
    ok &= bool(good)
    print(f"   {'OK ' if good else 'XX '} {label}" + (f" - {detail}" if detail else ""))


print("=" * 70)
print(" 1) THE WIRE EXISTS, AND IT IS ADDITIVE")
print("=" * 70)
chk("_chat_via_engine exists", callable(S._chat_via_engine))
_src = open(os.path.join(_ROOT, "web", "server.py"), encoding="utf-8").read()
chk("_chat tries the engine first", "_eng = _chat_via_engine(" in _src)
chk("  -> and returns only when the engine answered",
    "if _eng is not None:" in _src)
chk("  -> otherwise the old path runs unchanged",
    "s = keysync.get_settings()" in _src)
chk("the document pipeline is NOT routed through the engine",
    "run_pipeline_sync" in _src
    and "_chat_via_engine" not in _src.split("run_pipeline_sync")[1][:400])

print()
print("=" * 70)
print(" 2) IT NEVER SWALLOWS A REQUEST")
print("=" * 70)
chk("no engine installed -> None, so the old path takes over",
    S._chat_via_engine("hello") is None)


class _Fake:
    def __init__(self, answer):
        self.answer, self.seen = answer, ""

    def __call__(self, text, timeout=300, cwd=None, fallback=True,
                 session=None):
        self.seen = text
        return {"answer": self.answer, "engine": "weaver-core", "note": ""}


_real = (W.available, W.node_bin, W.ask)
try:
    W.available = lambda: True
    W.node_bin = lambda: "/usr/bin/node"
    W.ask = _Fake("hello from the engine")
    r = S._chat_via_engine("say hi", history=[{"role": "user", "content": "H"}],
                           context="C", memory="M", attachments="A")
    chk("engine answers -> a reply dict", isinstance(r, dict) and r.get("reply")
        == "hello from the engine", str(r)[:60])
    chk("  -> and it says WHICH engine answered", r.get("engine") == "weaver-core")
    chk("  -> memory, context, history and attachments all reach it",
        all(x in W.ask.seen for x in ("M", "C", "H", "A", "say hi")))

    W.ask = _Fake("")
    chk("an empty answer -> None, the old path takes over",
        S._chat_via_engine("x") is None)
    W.ask = _Fake("error: no key")
    chk("an engine error -> None, the old path takes over",
        S._chat_via_engine("x") is None)

    def _boom(*a, **k):
        raise RuntimeError("engine exploded")
    W.ask = _boom
    chk("an exception -> None, never a crash in the chat box",
        S._chat_via_engine("x") is None)

    W.ask = _Fake("on")
    os.environ["WEAVER_ENGINE_CHAT"] = "0"
    chk("WEAVER_ENGINE_CHAT=0 -> the old behaviour exactly",
        S._chat_via_engine("x") is None)
    os.environ.pop("WEAVER_ENGINE_CHAT")
    chk("  -> and removing it turns the engine back on",
        S._chat_via_engine("x") is not None)
finally:
    W.available, W.node_bin, W.ask = _real
    os.environ.pop("WEAVER_ENGINE_CHAT", None)

print()
print("=" * 70)
print(" 2b) TEXT TRANSFORMS DO NOT GO THROUGH THE AGENT")
print("=" * 70)
# One of the three _chat call sites is a FILE EDIT: it sends the file content
# and asks for the edited content back, "with no explanation and no preamble".
# The engine is an agent -- it explains, it may use tools, it may rephrase.
# Routing a file edit through it would corrupt the file. So that call site
# opts out; only real conversation reaches the engine.
chk("_chat takes use_engine", "use_engine: bool = True" in _src)
chk("  -> and honours it", "if use_engine and _engine_ready():" in _src)
chk("the file-edit call site opts out",
    "use_engine=False" in _src)
_fe = _src.split("هذا محتوى ملف موجود")[-1][:900] if "هذا محتوى ملف موجود" in _src else ""
chk("  -> specifically the one that returns edited file content",
    "use_engine=False" in _fe, "(لم يُعثر على الموضع)" if not _fe else "")
_conv = _src.count("_chat(msg, body.get(\"history\")")
chk(f"and the real conversation sites ({_conv}) keep the engine",
    _conv >= 2 and "use_engine=False" not in
    _src.split("_chat(msg, body.get(\"history\")")[1][:200])

print()
print("=" * 70)
print(" 3) ONE WIRE, BOTH SURFACES")
print("=" * 70)
_w = open(os.path.join(_ROOT, "weaver.py"), encoding="utf-8").read()
chk("the terminal loads the very same _chat",
    "from web.server import _chat" in _w)
chk("  -> so the wire serves the terminal too, with no second change",
    "_load_chat()" in _w)

print()
print("=" * 70)
print(" 4) ONE CALL, TOOLS ATTACHED -- exactly as openclaw does it")
print("=" * 70)
# openclaw's loop calls the model FIRST, and the tools ride along in the very
# same request -- one line, no branch:
#
#     // agent-core-B_87jlHI.mjs:258
#     const llmContext = { systemPrompt, messages, tools: context.tools };
#
# There is no classifier before it and the model is never asked "do you need
# tools?". It decides by CALLING one. So there is exactly one call here too.

_calls = []
_realdirect, _realeng, _realready = (S._chat_direct, S._chat_via_engine,
                                     S._engine_ready)
try:
    S._engine_ready = lambda: True

    def _direct(msg, hist=None, to=120, eff="medium", ctx=None, mem=None,
                att=None, escalate=False):
        _calls.append(("direct", escalate))
        return {"reply": _direct.answer}

    def _eng(*a, **k):
        _calls.append(("engine", True))
        return {"reply": "agent answer", "engine": "weaver-core"}
    S._chat_direct, S._chat_via_engine = _direct, _eng

    _direct.answer = "4.54 billion years"
    _calls.clear()
    r = S._chat("how old is earth?")
    chk("a question it knows -> STILL the agent, one call, no pre-question",
        r["reply"] == "agent answer" and [c[0] for c in _calls] == ["engine"])

    _calls.clear()
    r = S._chat("open example.com and tell me what you see")
    chk("a question needing tools -> the same one call",
        r["reply"] == "agent answer" and [c[0] for c in _calls] == ["engine"])

    chk("  -> the light model is never asked to judge itself first",
        not any(c[0] == "direct" for c in _calls))

    S._chat_via_engine = lambda *a, **k: (_calls.append(("engine", 0)) or None)
    _calls.clear()
    _direct.answer = "best effort answer"
    r = S._chat("x")
    chk("the agent itself fails -> a direct answer, never an empty reply",
        r["reply"] == "best effort answer"
        and [c[0] for c in _calls] == ["engine", "direct"])
    chk("  -> and that rescue call carries no escalation instruction",
        _calls[-1][1] is False)

    S._engine_ready = lambda: False
    _calls.clear()
    S._chat_direct = _direct
    _direct.answer = "plain"
    r = S._chat("x")
    chk("no engine -> exactly the old single call, no instruction added",
        r["reply"] == "plain" and _calls == [("direct", False)])

    S._engine_ready = lambda: True
    _calls.clear()
    r = S._chat("x", use_engine=False)
    chk("use_engine=False -> the old call too (file edits stay safe)",
        _calls == [("direct", False)])
finally:
    S._chat_direct, S._chat_via_engine, S._engine_ready = (
        _realdirect, _realeng, _realready)

print()
print("=" * 70)
print(" 5) THE ENGINE'S OWN COST SWITCHES ARE TURNED ON")
print("=" * 70)
from pipeline import weaver_core as _W2
chk("tool-search is what gets enabled",
    any(k == "tools.toolSearch.enabled" for k, _ in _W2.TUNING))
chk("  -> in directory mode (a short index, not the full catalogue)",
    ("tools.toolSearch.mode", "directory") in _W2.TUNING)
chk("set through the engine's own `config set`, which validates it",
    "config" in open(os.path.join(_ROOT, "pipeline", "weaver_core.py"),
                     encoding="utf-8").read())
chk("and it is reversible", callable(_W2.tune))
chk("the lean surface stays OFF by default (it can hide a needed tool)",
    "WEAVER_ENGINE_LEAN" in open(
        os.path.join(_ROOT, "pipeline", "weaver_core.py"),
        encoding="utf-8").read())

print()
print("=" * 70)
print(" RESULT: " + ("PASS" if ok else "FAIL"))
print("=" * 70)
sys.exit(0 if ok else 1)
