"""
tools/probe_last_turn.py — ما سجّله المحرّكُ في آخر محادثة: نوبةً نوبة
======================================================================
قراءةٌ فقط: لا يكتب في الإعداد ولا ينادي النموذج. يأخذ أحدثَ جلسةٍ في
المحرّك، ويصدّر مسارَها (`sessions export-trajectory` — الطريقُ نفسُه الذي
تُبنى منه البطاقات)، ويطبع لكلِّ نوبة:

  • رسالةَ المستخدم (أوّلُها)
  • الأدواتِ التي تلتقطها البطاقات (`_tool_events`)
  • وأنواعَ الأحداث الخامَ في النوبة — فإن استعمل النموذجُ أداةً ولم تظهر
    بطاقتُها، بان هنا: حدثٌ موجودٌ بشكلٍ لا تلتقطه البطاقات.

    cd ~/weaver-write && python3 tools/probe_last_turn.py [عدد النوبات=3]
"""
import collections
import json
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


def _user_text(e):
    for k in ("text", "content", "message"):
        v = e.get(k) if isinstance(e, dict) else None
        if isinstance(v, str) and v.strip():
            return v
        if isinstance(v, dict):
            t = v.get("text") or v.get("content")
            if isinstance(t, str):
                return t
    d = e.get("data") if isinstance(e, dict) else None
    if isinstance(d, dict):
        return _user_text(d)
    return ""


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    n = int(argv[0]) if argv and argv[0].isdigit() else 3
    from pipeline import weaver_core as W
    if not W.available():
        print("✗ المحرّكُ غيرُ مركَّب")
        return 2
    c, o, e = W.run(["sessions", "list", "--json"], timeout=120)
    try:
        ss = (json.loads(o) or {}).get("sessions") or []
    except Exception:
        print("✗ تعذّر سردُ الجلسات: " + (e or o or "")[:200])
        return 2
    if not ss:
        print("✗ لا جلساتَ بعد — أرسل رسالةً من الواجهة ثمّ أعِد")
        return 2
    ss.sort(key=lambda s: -(s.get("updatedAt") or 0))
    key = ss[0].get("key") or ""
    print("الجلسة: " + key)
    os.makedirs(W.TRAJ_DIR, exist_ok=True)
    c, o, e = W.run(["sessions", "export-trajectory", "--session-key", key,
                     "--json", "--workspace", W.TRAJ_DIR], timeout=180)
    try:
        d = json.loads(o[o.find("{"):o.rfind("}") + 1])
        ev = os.path.join(d.get("outputDir") or "", "events.jsonl")
        events = [json.loads(ln) for ln in open(ev, encoding="utf-8",
                                                errors="replace") if ln.strip()]
    except Exception as x:
        print("✗ تعذّر التصدير: %s %s" % (type(x).__name__, (e or o)[:200]))
        return 2
    starts = [i for i, x in enumerate(events)
              if isinstance(x, dict) and x.get("type") == "user.message"]
    if not starts:
        starts = [0]
    for si, a in enumerate(starts[-n:]):
        idx = starts.index(a)
        b = starts[idx + 1] if idx + 1 < len(starts) else len(events)
        turn = events[a:b]
        calls = []
        for x in turn:
            try:
                calls.extend(W._tool_events(x))
            except Exception:
                pass
        calls = W._merge_calls(calls)
        kinds = collections.Counter(str(x.get("type")) for x in turn
                                    if isinstance(x, dict))
        print("\n══ نوبة: «%s»" % _user_text(events[a]).strip()[:70])
        print("  البطاقات تلتقط: " + (", ".join(
            "%s%s" % (cc.get("name"), (" (" + str((cc.get("request") or {})
                                             .get("path") or "")[:50] + ")")
                      if isinstance(cc.get("request"), dict)
                      and (cc.get("request") or {}).get("path") else "")
            for cc in calls) or "لا شيء"))
        print("  أنواعُ الأحداث: " + ", ".join(
            "%s×%d" % (k, v) for k, v in sorted(kinds.items())))
    return 0


if __name__ == "__main__":
    sys.exit(main())
