# -*- coding: utf-8 -*-
"""البوّابة: نوبةٌ بلا إقلاع — كما هو مسارُ أوبن كلاو العاديّ.

`agent exec` وصفُه بخطّ المحرّك «Run one **isolated** headless **embedded**
agent turn»: عمليةُ node جديدة، و٥٩ إضافةً تُحمَّل، و٥٤ أداةً تُبنى — في كلِّ
رسالة. مقيسٌ على خادمٍ سريع: ٨.٥٧ ث قبل أن يُنادى النموذجُ أصلاً.

ومسارُه العاديُّ هو `agent` — «Run an agent turn **via the Gateway**». مقيس:
١.٤١ ث. وتحلّ معها الذاكرةُ: `--session-id` يمنح استمرارَ المحادثة، وهو ما
يعجز عنه المعزولُ أبداً.

هذا الاختبار لا يحتاج محرّكاً مركَّباً: يرصد **الأمرَ الذي يُبنى**.
"""
import os
import sys

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


from pipeline import weaver_core as W   # noqa: E402

print("=" * 70)
print(" 1) مُعرِّفُ الجلسة — ثابتٌ ونظيف")
print("=" * 70)
chk("يُشتقّ من المفتاح", W._session_id("chat-42") == "weaver-chat-42")
chk("ثابتٌ لنفس المفتاح",
    W._session_id("abc") == W._session_id("abc"))
chk("يُنظَّف ممّا يُربك سطرَ الأوامر",
    all(c.isalnum() or c in "-_" for c in W._session_id("a b;rm -rf/ c")),
    W._session_id("a b;rm -rf/ c"))
chk("وفارغُه لا يُنتج مُعرِّفاً فارغاً",
    W._session_id("") == "weaver-default" and W._session_id(None))

print()
print("=" * 70)
print(" 2) الأمرُ المبنيّ: بوّابةٌ حيّة ⟶ agent -m")
print("=" * 70)
_real = (W.available, W.node_bin, W.run, W.gateway_on, W.gateway_start,
         W.model_id)
seen = {}
try:
    W.available = lambda: True
    W.node_bin = lambda: "/usr/bin/node"
    W.model_id = lambda: "openrouter/deepseek/deepseek-v4-flash"
    W.run = lambda args, timeout=180, input_text=None, cwd=None: (
        seen.update(args=list(args)) or (0, '{"final":"جواب"}', ""))

    W.gateway_on = lambda: True
    W.gateway_start = lambda wait=None: (True, "حيّة")
    r = W.ask("سؤال", timeout=120, fallback=False, session="chat-9")
    a = seen["args"]
    chk("يُنادى `agent -m` لا `agent exec`",
        a[:2] == ["agent", "-m"] and "exec" not in a, a)
    chk("ومعه مُعرِّفُ الجلسة — فتستمرّ المحادثة",
        "--session-id" in a and a[a.index("--session-id") + 1] == "weaver-chat-9", a)
    chk("ومُغلَّفُ JSON", "--json" in a)
    chk("والنموذجُ مُصرَّحٌ به (وإلّا سقط إلى openai وفشل بـauth)",
        "--model" in a, a)
    chk("والجوابُ يُقرأ من المُغلَّف", r["answer"] == "جواب", r)

    print()
    print("=" * 70)
    print(" 3) ولا بوّابة ⟶ اللقطةُ المعزولةُ كما كانت حرفاً")
    print("=" * 70)
    seen.clear()
    W.gateway_start = lambda wait=None: (False, "تعذّرت")
    W.ask("سؤال", timeout=120, fallback=False, session="chat-9")
    a = seen["args"]
    chk("يعود إلى `agent exec`", a[:2] == ["agent", "exec"], a)
    chk("وبلا مُعرِّفِ جلسةٍ (لا تقبله اللقطةُ المعزولة)",
        "--session-id" not in a, a)

    seen.clear()
    W.gateway_on = lambda: False
    W.ask("سؤال", timeout=120, fallback=False)
    chk("و`WEAVER_GATEWAY=0` تُطفئ البوّابةَ صراحةً",
        seen["args"][:2] == ["agent", "exec"], seen["args"])
finally:
    (W.available, W.node_bin, W.run, W.gateway_on, W.gateway_start,
     W.model_id) = _real

print()
print("=" * 70)
print(" 4) مُغلَّفُ البوّابة يُقرأ — وهو يُعشّش payloads تحت result")
print("=" * 70)
chk("result.payloads[].text",
    W._from_envelope('{"status":"ok","result":{"payloads":'
                     '[{"text":"جوابُ البوّابة"}]}}') == "جوابُ البوّابة")
chk("وpayloads العليا كما كانت",
    W._from_envelope('{"payloads":[{"text":"جوابٌ قديم"}]}') == "جوابٌ قديم")
chk("وfinal تعلو عليهما",
    W._from_envelope('{"final":"ن","payloads":[{"text":"م"}]}') == "ن")

print()
print("=" * 70)
print(" 5) الفحصُ الحيُّ لا يُقلع node")
print("=" * 70)
import time as _t                                          # noqa: E402
_t0 = _t.time()
_alive = W.gateway_health()
_dt = _t.time() - _t0
chk("gateway_health يعود في أقلّ من ثانيتين (اتّصالُ منفذٍ لا أمر)",
    _dt < 2.5, "%.3f ث" % _dt)
chk("ويعيد bool لا يرفع", isinstance(_alive, bool))
chk("والمنفذُ منفذُنا نحن", W.gateway_port() == W.OUR_PORT, W.gateway_port())

print()
print("=" * 70)
print(" 6) اختيارُ محرّك البحث — معالجُ أوبن كلاو نفسُه")
print("=" * 70)
# docs/cli/configure.md:74
#   «openclaw configure --section web picks a web-search provider and
#    configures its credentials.»
# ونحن لا نبني قائمةً من عندنا — نناديه. ويشترط طرفيّةً تفاعليّة
# (docs/cli/configure.md:40)، فـ`run()` العاديّةُ تلتقط الخرجَ وتقتلها،
# ولهذا `run_tty` تُورّث الطرفيّةَ كما هي.
chk("run_tty موجودة وتُورّث الطرفيّة (لا capture_output)",
    callable(W.run_tty))
import inspect as _i                                       # noqa: E402
_src = _i.getsource(W.run_tty)
# يُستثنى التوثيقُ الداخليّ: هو **يشرح** لماذا لا تصلح capture_output،
# فذكرُها فيه ليس استعمالاً لها. يُفحَص الكودُ وحده.
_code = _src.split('"""')[-1]
chk("  -> تستعمل subprocess.call لا capture_output",
    "subprocess.call" in _code and "capture_output" not in _code)
_src2 = _i.getsource(W.configure_web)
chk("configure_web تنادي `configure --section web`",
    '"configure"' in _src2 and '"--section"' in _src2 and '"web"' in _src2)
chk("  -> وتُعيد تشغيل البوّابة بعده (شرطُ التوثيق بعد تغيير الإضافات)",
    "gateway_stop" in _src2 and "gateway_start" in _src2)
_src3 = _i.getsource(W)
chk("والاحتياطُ المجّانيُّ بترتيب التوثيق: parallel-free قبل duckduckgo",
    W.WEB_SEARCH_FREE == ("parallel-free", "duckduckgo"), W.WEB_SEARCH_FREE)
chk("والإضافاتُ المُركَّبة تشمل المدفوعَ والمجّانيّ",
    set(W.WEB_SEARCH_PLUGINS) >= {"perplexity", "parallel", "duckduckgo"},
    W.WEB_SEARCH_PLUGINS)

print()
print("=" * 70)
print(" 7) اختيارُ المستخدمِ الصريحُ لا يُداس")
print("=" * 70)
# لو اختار مزوّداً بمعالج `configure --section web` ثمّ فشل نداءٌ واحدٌ
# لانقطاعِ شبكةٍ عابر، لكان تلقائيُّنا يبدّله بلا أن يخبره. فالتلقائيُّ
# لمن لم يختر فقط، ومن اختار يُقال له إنّ اختيارَه لا يعمل ويُترك له.
_r4 = (W.run, W.probe_search)
try:
    _calls = []

    def _run(args, timeout=180, input_text=None, cwd=None):
        _calls.append(list(args))
        if list(args)[:2] == ["config", "get"]:
            return 0, '"brave"', ""
        return 0, "", ""
    W.run = _run
    W.probe_search = lambda q="اختبار": {
        "providers": ["brave"], "configured": ["brave"], "chosen": "brave",
        "usable": True, "ok": False, "count": 0, "first": "",
        "error": "network hiccup"}
    chk("اختيارُه يُقرأ من الإعداد", W.chosen_provider() == "brave")
    _calls.clear()
    rows = W.enable_web_search()
    _sets = [c for c in _calls
             if c[:2] == ["config", "set"] and "provider" in " ".join(c)]
    chk("  -> ولا يُكتَب مزوّدٌ فوقه رغم فشل النداء", _sets == [], _sets)
    chk("  -> ويُقال له إنّ اختيارَه لا يعمل",
        any("لا يعمل" in str(r[0]) for r in rows), rows[-1:])

    W.probe_search = lambda q="اختبار": {
        "providers": [], "configured": [], "chosen": "", "usable": False,
        "ok": False, "count": 0, "first": "", "error": "no provider"}

    def _run2(args, timeout=180, input_text=None, cwd=None):
        _calls.append(list(args))
        if list(args)[:2] == ["config", "get"]:
            return 0, '""', ""
        return 0, "", ""
    W.run = _run2
    _calls.clear()
    W.enable_web_search()
    _sets = [c for c in _calls
             if c[:2] == ["config", "set"] and "provider" in " ".join(c)]
    chk("ومن لم يختر ⟶ يُعيَّن له المجّانيُّ الموثَّقُ أوّلاً",
        bool(_sets) and _sets[0][-1] == W.WEB_SEARCH_FREE[0], _sets[:1])
finally:
    (W.run, W.probe_search) = _r4

print()
print("=" * 70)
print(" RESULT: " + ("PASS" if _bad[0] == 0 else "FAIL")
      + "   (%d/%d)" % (_ok[0], _ok[0] + _bad[0]))
print("=" * 70)
sys.exit(1 if _bad[0] else 0)
