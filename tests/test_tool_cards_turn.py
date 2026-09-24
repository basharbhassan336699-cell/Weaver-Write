# -*- coding: utf-8 -*-
"""بطاقاتُ الأدوات: لا تضيع، ولا تتكرّر، ولا تنتقل من نوبةٍ إلى أخرى.

ثلاثةُ أعطالٍ قيست على هاتف المستخدم وهنا:
  ① ضياع: تصديرُ مسار النوبة ٣١ ثانيةً على الهاتف، والمجرى مفتوحٌ ينتظره
     بعد الجواب — فإن انقطع ضاعت البطاقاتُ كلُّها وبقي «التفكير» وحدَه.
  ② تكرار: المحرّكُ يسجّل كلَّ نداءٍ مرّتين (transcript وruntime) ونتيجتَه
     مرّتين؛ فنداءٌ واحدٌ لـexec صار ثلاثَ بطاقات، والهاتف: ٢٧ صفّاً.
  ③ انتقال: التصديرُ يُخرج المحادثةَ كلَّها — فرسالةٌ ثانيةٌ بلا أداةٍ عُرضت
     لها أدواتُ الأولى.

والأحداثُ هنا بشكلها الحقيقيّ، منقولةٌ من events.jsonl صدّره المحرّك.
"""
import json
import os
import sys
import tempfile

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

from pipeline import weaver_core as W   # noqa: E402

P = F = 0


def ok(name, cond, extra=""):
    global P, F
    if cond:
        P += 1
        print(f"  ✓ {name}")
    else:
        F += 1
        print(f"  ✗ {name}" + (f"   — {extra}" if extra else ""))


def _turn(ts_user, calls):
    """أحداثُ نوبةٍ بشكل المحرّك: رسالةُ مستخدم، ثمّ لكلّ نداءٍ ٤ صفوف."""
    ev = [{"type": "session.started", "source": "runtime", "ts": ts_user},
          {"type": "user.message", "source": "transcript", "ts": ts_user}]
    for cid, name, args, text in calls:
        ev += [
            {"type": "assistant.message", "source": "transcript", "ts": ts_user,
             "data": {"message": {"role": "assistant", "content": [
                 {"type": "toolCall", "id": cid, "name": name,
                  "arguments": args}]}}},
            {"type": "tool.call", "source": "transcript", "ts": ts_user,
             "data": {"toolCallId": cid, "name": name, "arguments": args}},
            {"type": "tool.call", "source": "runtime", "ts": ts_user,
             "data": {"toolCallId": cid, "name": name, "args": args}},
            {"type": "tool.result", "source": "runtime", "ts": ts_user,
             "data": {"toolCallId": cid, "name": name, "success": True,
                      "result": {"content": [{"type": "text", "text": text}]}}},
            {"type": "tool.result", "source": "transcript", "ts": ts_user,
             "data": {"message": {"role": "toolResult", "toolCallId": cid,
                                  "toolName": name, "isError": False,
                                  "content": [{"type": "text",
                                               "text": text}]}}}]
    ev.append({"type": "model.completed", "source": "runtime", "ts": ts_user})
    return ev


T1 = "2026-09-24T16:53:20.133Z"
T2 = "2026-09-24T16:53:27.217Z"       # بعد الأولى بسبع ثوانٍ فقط
EVENTS = (_turn(T1, [("call_1", "exec", {"command": "echo hi"}, "hi"),
                     ("call_2", "web_fetch", {"url": "https://x"}, "<html>")])
          + _turn(T2, []))

print("\n— ② التكرار: نداءٌ واحدٌ ⟵ بطاقةٌ واحدةٌ بطلبه ونتيجته —")
raw = []
for e in EVENTS:
    raw.extend(W._tool_events(e))
ok("الأحداثُ الخام فيها تكرار (هكذا يسجّلها المحرّك)", len(raw) > 2, len(raw))
m = W._merge_calls(raw)
ok("بعد الدمج: نداءان فقط", [c["name"] for c in m] == ["exec", "web_fetch"],
   [c["name"] for c in m])
ok("  ⟵ وكلٌّ بطلبه ونتيجته معاً",
   all(c["request"] is not None and c["response"] is not None for c in m))
ok("  ⟵ ما لا معرّفَ له يبقى كما هو",
   W._merge_calls([{"name": "a"}, {"name": "a"}]) == [{"name": "a"},
                                                      {"name": "a"}])
ok("  ⟵ والخطأُ في أيّ صفٍّ يُنقَل",
   W._merge_calls([{"name": "x", "id": "1", "status": "ok", "request": 1,
                    "response": None},
                   {"name": "x", "id": "1", "status": "err", "request": None,
                    "response": 2}])[0]["status"] == "err")

print("\n— ③ النوبة: لا تنتقل بطاقاتُ رسالةٍ إلى أخرى —")
_tmp = tempfile.mkdtemp()
with open(os.path.join(_tmp, "events.jsonl"), "w", encoding="utf-8") as fh:
    for e in EVENTS:
        fh.write(json.dumps(e, ensure_ascii=False) + "\n")
_real_run = W.run
W.run = lambda args, **k: (0, json.dumps({"ok": True, "outputDir": _tmp}), "")
try:
    from datetime import datetime
    ms = lambda t: datetime.fromisoformat(t.replace("Z", "+00:00")).timestamp() * 1000
    r = W.trajectory_turn("c1", since_ms=ms(T1) - 50)
    ok("الأولى ⟵ exec وweb_fetch", r["ok"] and [c["name"] for c in r["calls"]]
       == ["exec", "web_fetch"], r)
    r = W.trajectory_turn("c1", since_ms=ms(T2) - 50)
    ok("الثانيةُ (بعد ٧ ث) ⟵ لا شيء — لا أدواتُ الأولى", r["ok"]
       and r["calls"] == [], r["calls"])
    r = W.trajectory_turn("c1")
    ok("بلا لحظة ⟵ النوبةُ الأخيرة", r["ok"] and r["calls"] == [])
    ok("والقديمة (trajectory) كما كانت: المحادثةُ كلُّها، مدموجة",
       [c["name"] for c in W.trajectory("c1")] == ["exec", "web_fetch"])
    W.run = lambda args, **k: (1, "", "Error: timeout")
    r = W.trajectory_turn("c1")
    ok("تصديرٌ فاشل ⟵ ok=False (لا «لا أدوات» كاذب)", r["ok"] is False
       and r["error"], r)
finally:
    W.run = _real_run

print("\n— ① الضياع: البطاقاتُ مستقلّةٌ عن مجرى الجواب —")
_srv = open(os.path.join(_ROOT, "web", "server.py"), encoding="utf-8").read()
_i = _srv.index('_ev = {"t": "reply", "reply": reply}')
_blk = _srv[_i:_i + 2500]
ok("المجرى لا ينتظر التصدير بعد الجواب",
   "_engine_trajectory_cards" not in _blk)
ok("  ⟵ والبطاقةُ الثابتةُ تُرسَل فوراً", 'sse({"t": "tool", "tool": _tc})' in _blk)
ok("طلبٌ مستقلّ /api/chat/tools", '"/api/chat/tools"' in _srv
   and "_engine_turn_cards" in _srv)
_html = open(os.path.join(_ROOT, "web", "index.html"), encoding="utf-8").read()
ok("الصفحةُ تطلبها بعد المجرى", "wvLoadTurnTools(currentChatId, amsg" in _html)
ok("  ⟵ وتحفظ «معلّقة» قبلها", "amsg.toolsPending = { since: sentAt" in _html)
ok("  ⟵ وتُعيد الطلبَ عند فتح المحادثة", "if (m.toolsPending && typeof "
   "wvLoadTurnTools" in _html)
ok("  ⟵ وتحفظ في المحادثة الصحيحة ولو انتقل المستخدم",
   "async function wvPersistMsg(chatId, msg, since)" in _html)
ok("  ⟵ وتكفّ بعد ثلاث فتحاتٍ فاشلة", "tries >= 3" in _html)

print("\n" + "=" * 62)
print(f" RESULT: {'PASS' if F == 0 else 'FAIL'}   ({P}/{P + F})")
print("=" * 62)
sys.exit(1 if F else 0)
