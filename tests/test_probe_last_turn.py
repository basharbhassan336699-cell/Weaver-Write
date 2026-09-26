# -*- coding: utf-8 -*-
"""tools/probe_last_turn.py — يطبع لكلِّ نوبةٍ ما تلتقطه البطاقات والأحداثَ
الخام (محاكاةٌ بشكل أحداث المحرّك، بلا نموذج). قراءةٌ فقط."""
import io
import json
import os
import sys
import tempfile
from contextlib import redirect_stdout

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)
sys.path.insert(0, os.path.join(_ROOT, "tests"))
from pipeline import weaver_core as W   # noqa: E402
sys.path.insert(0, os.path.join(_ROOT, "tools"))
import probe_last_turn as PL            # noqa: E402

P = F = 0


def ok(name, cond, extra=""):
    global P, F
    if cond:
        P += 1
        print(f"  ✓ {name}")
    else:
        F += 1
        print(f"  ✗ {name}" + (f"   — {extra}" if extra else ""))


def turn(text, calls):
    ev = [{"type": "user.message", "source": "transcript", "ts": 1,
           "data": {"text": text}}]
    for cid, name, args in calls:
        ev += [{"type": "tool.call", "source": "runtime", "ts": 1,
                "data": {"toolCallId": cid, "name": name, "args": args}},
               {"type": "tool.result", "source": "runtime", "ts": 1,
                "data": {"toolCallId": cid, "name": name, "success": True,
                         "result": {"content": [{"type": "text",
                                                 "text": "ok"}]}}}]
    return ev


out_dir = tempfile.mkdtemp()
events = (turn("ابحث عن الأخبار", [("c1", "web_search", {"query": "ai"})])
          + turn("اكتب مستنداً واحفظه md",
                 [("c2", "write", {"path": "التعليم.md", "content": "x"})])
          + [{"type": "custom.thing", "ts": 1}])
with open(os.path.join(out_dir, "events.jsonl"), "w", encoding="utf-8") as fh:
    fh.write("\n".join(json.dumps(e, ensure_ascii=False) for e in events))
_calls = []
_real = {n: getattr(W, n) for n in ("available", "run")}
try:
    W.available = lambda: True

    def _run(args, timeout=180, **k):
        _calls.append(args)
        if args[:2] == ["sessions", "list"]:
            return 0, json.dumps({"sessions": [
                {"key": "agent:main:explicit:old", "updatedAt": 1},
                {"key": "agent:main:explicit:new", "updatedAt": 5}]}), ""
        if args[:2] == ["sessions", "export-trajectory"]:
            return 0, json.dumps({"ok": True, "outputDir": out_dir}), ""
        return 1, "", "?"
    W.run = _run
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = PL.main([])
    out = buf.getvalue()
    ok("أحدثُ جلسة", "agent:main:explicit:new" in out and rc == 0, out[:200])
    ok("نوبتان بنصِّ رسالتيهما", "ابحث عن الأخبار" in out
       and "اكتب مستنداً" in out, out)
    ok("  ⟵ web_search في الأولى", "web_search" in out.split("اكتب")[0])
    ok("  ⟵ write بمساره في الثانية", "write (التعليم.md)" in out, out)
    ok("  ⟵ والأحداثُ الخامُ معدودة (ومنها غيرُ المعروف)",
       "custom.thing×1" in out and "tool.call×1" in out, out)
    ok("قراءةٌ فقط: لا config set/patch",
       not any(a[:2] in (["config", "set"], ["config", "patch"])
               for a in _calls))
    # --find: المحادثةُ التي فيها العبارة، لا الأحدث.
    old_dir = tempfile.mkdtemp()
    with open(os.path.join(old_dir, "events.jsonl"), "w",
              encoding="utf-8") as fh:
        fh.write("\n".join(json.dumps(e, ensure_ascii=False) for e in turn(
            "اكتب مستنداً عن التعليم الإلكتروني", [("c9", "write",
                                                     {"path": "t.md"})])))

    def _run2(args, timeout=180, **k):
        if args[:2] == ["sessions", "list"]:
            return 0, json.dumps({"sessions": [
                {"key": "agent:main:explicit:doc", "updatedAt": 1},
                {"key": "agent:main:explicit:new", "updatedAt": 5}]}), ""
        if args[:2] == ["sessions", "export-trajectory"]:
            d = old_dir if args[3].endswith(":doc") else out_dir
            return 0, json.dumps({"ok": True, "outputDir": d}), ""
        return 1, "", "?"
    W.run = _run2
    with redirect_stdout(io.StringIO()) as b3:
        rc = PL.main(["--find", "التعليم الإلكتروني"])
    ok("--find ⟵ المحادثةُ التي فيها العبارة لا الأحدث",
       rc == 0 and "explicit:doc" in b3.getvalue()
       and "write (t.md)" in b3.getvalue(), b3.getvalue())
    with redirect_stdout(io.StringIO()) as b4:
        rc = PL.main(["--find", "لا توجد هذه العبارة"])
    ok("--find بلا تطابق ⟵ يقول ذلك", rc == 2 and "لا محادثةَ" in
       b4.getvalue())
    W.run = lambda a, timeout=180, **k: (0, json.dumps({"sessions": []}), "")
    with redirect_stdout(io.StringIO()) as b2:
        rc = PL.main([])
    ok("بلا جلسات ⟵ يقول ذلك", rc == 2 and "لا جلساتَ" in b2.getvalue())
finally:
    for n, f in _real.items():
        setattr(W, n, f)

print("\n" + "=" * 62)
print(f" RESULT: {'PASS' if F == 0 else 'FAIL'}   ({P}/{P + F})")
print("=" * 62)
sys.exit(1 if F else 0)
