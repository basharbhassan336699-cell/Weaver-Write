# -*- coding: utf-8 -*-
"""لا شيءَ يسبق النموذج — كما في أوبن كلاو حرفاً.

في أوبن كلاو أوّلُ شيءٍ داخل الحلقة نداءُ النموذج، والأدواتُ في نفس النداء،
سطرٌ واحدٌ بلا تفرّع:

    // agent-core-B_87jlHI.mjs:258
    const llmContext = { systemPrompt, messages, tools: context.tools };

لا مصنِّفَ قبله، ولا بحثَ يُشغَّل نيابةً عنه، ولا سياقَ يُحقن في رسالته، ولا
قائمةَ مصادرَ تُلحق بردّه. والنموذجُ يبحث إن أراد — بأداته، داخل الحلقة.

وكان في مسار الويب أربعُ محطّاتٍ تسبقه:

  ① quick_live_context_ex  بحثٌ قبل النموذج، تقرّره قائمةُ ٢١ كلمةً في
                           `_is_recency_query` لا النموذج
  ② _recall_memory         ذاكرةٌ تُحقن في الرسالة
  ③ _web_intent            نداءُ نموذجٍ كاملٌ للتصنيف، في كلّ رسالة
  ④ _sources_md            قائمةُ مصادرَ يُلحقها الخادمُ بالردّ

هذا الاختبار يُشغّل **خادمَ الويب الحقيقيّ** ويُرسل إليه طلباً عبر HTTP، ثمّ
يرصد أيَّ محطّةٍ جرت. فهو يختبر السلوك، لا شكلَ الكود.
"""
import json
import os
import sys
import threading
import urllib.request

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

_ok = [0]
_bad = [0]


def chk(label, cond, extra=""):
    if cond:
        _ok[0] += 1
        print("   OK  " + label)
    else:
        _bad[0] += 1
        print("   XX  " + label + ("   " + str(extra) if extra else ""))


from web import server as S            # noqa: E402
import pipeline.orchestrator as O      # noqa: E402

seen = []
_real = {}


def _install(engine_on):
    """يستبدل كلَّ محطّةٍ برصّادٍ يسجّل مرورَها."""
    S._engine_ready = lambda: engine_on
    S._chat_via_engine = (
        lambda m, h=None, t=120, c=None, mem=None, att=None, session=None:
        seen.append(("engine", c, mem)) or {"reply": "جوابُ المحرّك",
                                            "engine": "weaver-core"})
    S._chat_direct = (lambda *a, **k:
                      seen.append(("direct",)) or {"reply": "جوابٌ مباشر"})
    O.quick_live_context_ex = (
        lambda *a, **k: seen.append(("presearch",))
        or ("سياق", [{"title": "t", "url": "http://u"}]))
    S._recall_memory = lambda *a, **k: seen.append(("memory",)) or "ذاكرة"
    S._web_intent = lambda m: seen.append(("classify",)) or None


_srv = S._ReuseTCPServer(("127.0.0.1", 0), S.Handler)
_port = _srv.server_address[1]
threading.Thread(target=_srv.serve_forever, daemon=True).start()


def ask(path, msg):
    seen.clear()
    req = urllib.request.Request(
        "http://127.0.0.1:%d%s" % (_port, path),
        data=json.dumps({"message": msg, "history": []}).encode(),
        headers={"Content-Type": "application/json"})
    body = urllib.request.urlopen(req, timeout=60).read().decode()
    return body, [x[0] for x in seen]


try:
    print("=" * 70)
    print(" 1) المحرّكُ حاضر ⟶ لا شيءَ يسبقه")
    print("=" * 70)
    _install(True)
    for path in ("/api/chat", "/api/chat/stream"):
        out, names = ask(path, "أبحث لي عن آخر الأخبار لهذا اليوم؟")
        chk(path + ": المحرّكُ وحده جرى", names == ["engine"], names)
        chk(path + ": لا بحثَ قبل النموذج", "presearch" not in names)
        chk(path + ": لا ذاكرةَ مُحقَنة", "memory" not in names)
        chk(path + ": لا تصنيفَ مسبق", "classify" not in names)
        chk(path + ": لا قائمةَ مصادرَ مُلحقة", "المصادر" not in out)
        chk(path + ": وردُّ المحرّك هو ما يصل", "جوابُ المحرّك" in out)
        _eng = [x for x in seen if x[0] == "engine"]
        chk(path + ": نُودي برسالةٍ عاريةٍ بلا حقن",
            bool(_eng) and not (_eng[0][1] or "") and not (_eng[0][2] or ""),
            _eng[:1])

    print()
    print("=" * 70)
    print(" 2) ولا محرّكَ ⟶ القديمُ كما كان حرفاً")
    print("=" * 70)
    _install(False)
    for path in ("/api/chat", "/api/chat/stream"):
        out, names = ask(path, "كم سعر البيتكوين الآن؟")
        chk(path + ": البحثُ السابقُ ما زال يجري", "presearch" in names, names)
        chk(path + ": والذاكرةُ تُحقن", "memory" in names)
        chk(path + ": والتصنيفُ يُنادى", "classify" in names)
        chk(path + ": والمصادرُ تُلحق", "المصادر" in out)
        chk(path + ": والنداءُ المباشرُ هو المجيب", "direct" in names)
finally:
    _srv.shutdown()

print()
print("=" * 70)
print(" RESULT: " + ("PASS" if _bad[0] == 0 else "FAIL")
      + "   (%d/%d)" % (_ok[0], _ok[0] + _bad[0]))
print("=" * 70)
sys.exit(1 if _bad[0] else 0)
