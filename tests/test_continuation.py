# -*- coding: utf-8 -*-
"""الإكمال وسقفُ الإخراج — مقابلُ `continuationRequired` عند أوبن كلاو.

العطبان اللذان رآهما المستخدم:
  ① الردُّ الطويل يُقطع في منتصف جملةٍ ولا يُكمل — سقفُ «medium» كان ٢٠٤٨،
     وأوبن كلاو يستعمل سقفَ النموذج نفسِه:
         config-provider-contract-BdOif1pq.mjs:233  maxTokens: model.maxTokens ?? 8192
  ② وحين عجز المحرّكُ ابتُلع العجزُ صامتاً وتولّى المسارُ المباشر، فظنّ
     المستخدمُ أنّه يُشغّل المحرّك وهو لا يُشغّله.
"""
import json
import os
import sys
import threading
import urllib.request

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

_ok, _bad = [0], [0]


def chk(label, cond, extra=""):
    if cond:
        _ok[0] += 1
        print("   OK  " + label)
    else:
        _bad[0] += 1
        print("   XX  " + label + ("   " + str(extra) if extra else ""))


from web import server as S          # noqa: E402
from pipeline import weaver_core as W  # noqa: E402

print("=" * 70)
print(" 1) سقفُ الإخراج كما عند أوبن كلاو، لا ٢٠٤٨")
print("=" * 70)
chk("medium صار ٨١٩٢ (افتراضيُّ أوبن كلاو)",
    S.EFFORT["medium"]["max_tokens"] == 8192,
    S.EFFORT["medium"]["max_tokens"])
chk("ويرتفع بارتفاع الجهد",
    S.EFFORT["low"]["max_tokens"] < S.EFFORT["medium"]["max_tokens"]
    < S.EFFORT["high"]["max_tokens"] < S.EFFORT["max"]["max_tokens"])

print()
print("=" * 70)
print(" 2) القطعُ عند السقف ⟶ يُستأنف ويُلصق")
print("=" * 70)


class _Resp:
    def __init__(self, d):
        self._d = json.dumps(d).encode()

    def read(self):
        return self._d

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _mk(parts):
    calls = []

    def _open(req, timeout=None):
        calls.append(json.loads(req.data.decode()))
        i = len(calls) - 1
        txt, fr = parts[min(i, len(parts) - 1)]
        return _Resp({"choices": [{"message": {"content": txt},
                                   "finish_reason": fr}]})
    return calls, _open


_realopen = urllib.request.urlopen
_realsettings = S.keysync.get_settings
try:
    S.keysync.get_settings = lambda: {
        "WEAVER_API_KEY": "k", "WEAVER_BASE_URL": "https://x/v1",
        "WEAVER_MODEL": "m", "WEAVER_PROVIDER": "p"}

    calls, op = _mk([("أوّل", "length"), (" ثانٍ", "length"), (" وخاتمة", "stop")])
    urllib.request.urlopen = op
    r = S._chat_direct("اكتب هيكلاً طويلاً", effort="medium")
    chk("الأجزاءُ الثلاثةُ التصقت", r["reply"] == "أوّل ثانٍ وخاتمة", r["reply"])
    chk("وجولتا إكمال", r.get("continued") == 2, r.get("continued"))
    chk("ولا يُعاد ما كُتب (يُمرَّر كـassistant لا يُكرَّر)",
        calls[1]["messages"][-2]["role"] == "assistant"
        and calls[1]["messages"][-2]["content"] == "أوّل")
    chk("والتوقّفُ عند stop لا يستأنف", len(calls) == 3, len(calls))

    calls, op = _mk([("تمّ", "stop")])
    urllib.request.urlopen = op
    r = S._chat_direct("سؤالٌ قصير", effort="medium")
    chk("وردٌّ مكتملٌ لا يُستأنف أصلاً",
        r["reply"] == "تمّ" and r.get("continued") == 0 and len(calls) == 1)

    calls, op = _mk([("لا ينتهي", "length")])
    urllib.request.urlopen = op
    os.environ["WEAVER_CONTINUE_ROUNDS"] = "3"
    r = S._chat_direct("س", effort="medium")
    chk("ولا تدور بلا نهاية — حدٌّ أقصى",
        r.get("continued") == 3 and len(calls) == 4, (r.get("continued"), len(calls)))
    os.environ.pop("WEAVER_CONTINUE_ROUNDS", None)
finally:
    urllib.request.urlopen = _realopen
    S.keysync.get_settings = _realsettings

print()
print("=" * 70)
print(" 3) عجزُ المحرّك يظهر بطاقةً، لا يُبتلع صامتاً")
print("=" * 70)
_r2 = (S._engine_ready, W.available, W.node_bin, W.ask, S._chat_direct)
try:
    S._engine_ready = lambda: True
    W.available = lambda: True
    W.node_bin = lambda: "/usr/bin/node"
    W.ask = lambda *a, **k: {"answer": "", "engine": "weaver-core",
                             "note": "gateway refused"}
    S._chat_direct = lambda *a, **k: {"reply": "جوابٌ مباشر"}
    srv = S._ReuseTCPServer(("127.0.0.1", 0), S.Handler)
    port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    req = urllib.request.Request(
        "http://127.0.0.1:%d/api/chat/stream" % port,
        data=json.dumps({"message": "سؤال", "history": []}).encode(),
        headers={"Content-Type": "application/json"})
    out = urllib.request.urlopen(req, timeout=60).read().decode()
    srv.shutdown()
    cards = [json.loads(l[6:])["tool"] for l in out.splitlines()
             if l.startswith("data: ") and '"t": "tool"' in l]
    chk("بطاقةٌ صدرت", len(cards) == 1, len(cards))
    chk("  -> حالتُها خطأ", bool(cards) and cards[0]["status"] == "err")
    chk("  -> وتحمل السببَ الحقيقيّ",
        bool(cards) and "gateway refused" in cards[0]["sub"], cards[:1])
    chk("  -> والمستخدمُ يبقى بجوابٍ لا بفراغ", "جوابٌ مباشر" in out)
finally:
    (S._engine_ready, W.available, W.node_bin, W.ask, S._chat_direct) = _r2

print()
print("=" * 70)
print(" 4) بطاقةٌ لكلِّ أداةٍ استدعاها الوكيل — لا «التفكير» وحده")
print("=" * 70)
# مُغلَّفُ --json يحمل الجوابَ فقط، فما استدعاه الوكيلُ من أدواتٍ لا يظهر فيه.
# ولهذا لم يكن المستخدمُ يرى إلّا «التفكير» بينما الوكيلُ يبحث ويقرأ.
# فتُقرأ من `sessions export-trajectory` عند المحرّك.
_r3 = (S._engine_ready, S._chat_via_engine, W.trajectory, W.LAST_LOG)
try:
    os.makedirs(os.path.dirname(W.LAST_LOG), exist_ok=True)
    with open(W.LAST_LOG, "w", encoding="utf-8") as _f:
        _f.write("# args: agent -m ابحث --json\n# exit: 0\n\n"
                 "--- stdout ---\n{\"ok\": true, \"final\": \"تمّ\"}\n")
    S._engine_ready = lambda: True
    S._chat_via_engine = (
        lambda m, h=None, t=120, c=None, mem=None, att=None, session=None:
        {"reply": "الطقسُ صحو", "engine": "weaver-core", "model": "m"})
    W.trajectory = lambda session, agent="main", timeout=90: [
        {"name": "web_search", "request": {"query": "طقس صنعاء"},
         "response": "١٢ نتيجة", "status": "ok"},
        {"name": "web_fetch", "request": {"url": "https://w/x"},
         "response": "<html>", "status": "ok"},
        {"name": "write", "request": {"file_path": "/tmp/o.md"},
         "response": "كُتب", "status": "err"}]
    srv = S._ReuseTCPServer(("127.0.0.1", 0), S.Handler)
    port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    req = urllib.request.Request(
        "http://127.0.0.1:%d/api/chat/stream" % port,
        data=json.dumps({"message": "ابحث", "history": [], "chatId": "c1"}).encode(),
        headers={"Content-Type": "application/json"})
    out = urllib.request.urlopen(req, timeout=60).read().decode()
    srv.shutdown()
    cards = [json.loads(l[6:])["tool"] for l in out.splitlines()
             if l.startswith("data: ") and '"t": "tool"' in l]
    names = [c["title"] for c in cards]
    chk("أربعُ بطاقات: ثلاثُ أدواتٍ ونوبة", len(cards) == 4, names)
    chk("  -> web_search فيها", "web_search" in names, names)
    chk("  -> web_fetch فيها", "web_fetch" in names, names)
    chk("  -> write فيها", "write" in names, names)
    chk("  -> وسطرٌ فرعيٌّ من الوسيط المهمّ",
        any(c.get("sub") == "طقس صنعاء" for c in cards), cards[:1])
    chk("  -> وحالةُ الخطأ تُنقَل",
        any(c["status"] == "err" for c in cards))
    chk("  -> والمدخلاتُ والمخرجاتُ محمولةٌ معها",
        all(c["request"] and c["response"] for c in cards[:3]))
finally:
    (S._engine_ready, S._chat_via_engine, W.trajectory, W.LAST_LOG) = _r3

print()
print("=" * 70)
print(" RESULT: " + ("PASS" if _bad[0] == 0 else "FAIL")
      + "   (%d/%d)" % (_ok[0], _ok[0] + _bad[0]))
print("=" * 70)
sys.exit(1 if _bad[0] else 0)
