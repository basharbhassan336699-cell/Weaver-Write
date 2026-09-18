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

    def __call__(self, text, timeout=300, cwd=None, fallback=True):
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
print(" 3) ONE WIRE, BOTH SURFACES")
print("=" * 70)
_w = open(os.path.join(_ROOT, "weaver.py"), encoding="utf-8").read()
chk("the terminal loads the very same _chat",
    "from web.server import _chat" in _w)
chk("  -> so the wire serves the terminal too, with no second change",
    "_load_chat()" in _w)

print()
print("=" * 70)
print(" RESULT: " + ("PASS" if ok else "FAIL"))
print("=" * 70)
sys.exit(0 if ok else 1)
