# -*- coding: utf-8 -*-
"""الحلقة: النموذج ينظر إلى ما عاد، ويقرّر أن يعيد — أو يقف.

هذا هو الجذر، وهو سطرٌ واحدٌ في أوبن كلاو:

    openclaw/dist/agent-core-B_87jlHI.mjs:541
        while (true) {
          let hasMoreToolCalls = true;
          while (hasMoreToolCalls || pendingMessages.length > 0) {
            ...
            hasMoreToolCalls = streamed.continuationRequired
                 || (executedToolBatch !== void 0 && !executedToolBatch.terminate);

الحلقةُ لا تقف إلا حين يتوقّف **النموذجُ** عن طلب أداة. لا عدّادَ خطوات، ولا
خطّةً مكتوبة. ولذلك عاد أوبن كلاو بتسعةٍ: بحث، فرأى ثلاثة، فبحث بكلماتٍ أخرى،
ففتح الصفحات، فوقف عند تسعة.

وويفر رايت أنبوبٌ يجري مرّةً واحدة: بحثٌ ثمّ فرزٌ ثمّ انتهى — وما عاد، عاد،
لأن النموذجَ لا يرى النتيجةَ ليقرّر أن يعيد. وكلُّ إصلاحٍ قبل هذا كان تكرارةً
واحدةً مكتوبةً باليد، لأن البنية لا تملك حلقةً تضعها فيها.

وأوبن كلاو يحمل مع حلقته حارساً (`criticalToolLoopSeen`: «the same tool+params
combination has been called excessively») — فهنا النصفان: النموذجُ يقول متى
يقف، والكودُ يرفض استعلاماً مكرَّراً وجولةً لم تُضِف شيئاً."""
import sys, os, json, inspect
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
for k in list(os.environ):
    if k.startswith("WEAVER_"):
        os.environ.pop(k)
from pipeline.orchestrator import WeaverOrchestrator as W
ok = True


def chk(label, good, detail=""):
    global ok
    ok &= bool(good)
    print(f"   {'✅' if good else '❌'} {label}" + (f" — {detail}" if detail else ""))


print("═" * 70)
print(" ١) النموذجُ يُعرَض عليه ما عاد، ويُسأل: نقف أم نعيد؟")
print("═" * 70)


class _M:
    def __init__(self, reply):
        self.reply, self.prompt, self.calls = reply, "", 0

    def __call__(self, prompt, **kw):
        self.calls += 1
        self.prompt = prompt
        return self.reply


HAVE = [{"title": "أثر النوم على التحصيل", "lang_eff": "ar"},
        {"title": "Sleep and grades", "lang_eff": "en"}]
o = W.__new__(W)
o.system_main = None
o.llm_fn = _M(json.dumps({"done": False, "door": "scholar",
                          "query": "جودة النوم لدى الطلبة",
                          "why": "المتحصَّل واحدٌ من تسعة"}, ensure_ascii=False))
v = o._search_verdict({}, "ar", 9, HAVE, "ar", {"استعلامٌ قديم"})
chk("رأى المطلوبَ والمتحصَّل", "9" in o.llm_fn.prompt and "أثر النوم" in o.llm_fn.prompt)
chk("ورأى ما جُرِّب كي لا يعيده", "استعلامٌ قديم" in o.llm_fn.prompt)
chk("ورأى البابين", "scholar" in o.llm_fn.prompt and "api" in o.llm_fn.prompt)
chk(f"وقرّر: نعيد عبر {v.get('door')}",
    v == {"done": False, "door": "scholar", "query": "جودة النوم لدى الطلبة",
          "why": "المتحصَّل واحدٌ من تسعة"}, str(v))

o2 = W.__new__(W); o2.system_main = None
o2.llm_fn = _M(json.dumps({"done": True, "why": "لا مزيدَ في هذا الموضوع"},
                          ensure_ascii=False))
chk("وحين يقول «كفى» ⟶ done",
    o2._search_verdict({}, "ar", 9, HAVE, "ar", set())["done"] is True)

o3 = W.__new__(W); o3.system_main = None
o3.llm_fn = _M(json.dumps({"done": False, "door": "لا شيء", "query": "س"}))
chk("وبابٌ مخترَعٌ يُردّ إلى api",
    o3._search_verdict({}, "ar", 9, HAVE, "ar", set())["door"] == "api")

print("\n" + "═" * 70)
print(" ٢) وكلُّ تعذّرٍ ⟶ None، فتقف الحلقة ولا تنهار")
print("═" * 70)


class _Broken:
    def __call__(self, p, **k):
        raise ConnectionError("403")


for name, fn in (("بلا نموذج", None), ("نموذجٌ يرفض", _Broken()),
                 ("ردٌّ غيرُ صالح", _M("ليس JSON"))):
    ox = W.__new__(W); ox.system_main = None; ox.llm_fn = fn
    chk(f"{name} ⟶ None", ox._search_verdict({}, "ar", 9, HAVE, "ar", set()) is None)

print("\n" + "═" * 70)
print(" ٣) والحلقةُ موصولةٌ في طبقة البحث، بحارسَي أوبن كلاو")
print("═" * 70)
_src = inspect.getsource(W._academic_search)
chk("حلقةٌ لا خطوةٌ واحدة", "while self.llm_fn and _rounds < _max_r" in _src)
chk("والنموذجُ هو من يوقفها", "_v.get(\"done\")" in _src)
chk("وحارسُ التكرار: لا يُعاد استعلامٌ جُرِّب",
    "_q3 in _tried" in _src and "openclaw's repeat guard" in _src)
chk("وحارسُ الجمود: جولةٌ بلا إضافةٍ تُنهيها",
    "a round that added nothing ends it" in _src)
chk("والبابان كلاهما في متناولها",
    "_scholar_harvest(" in _src and "_top_up_language(" in _src)
chk("والنموذجُ يختار البابَ لا الكود", '_v.get("door") == "scholar"' in _src)
chk("وسقفٌ أعلى قابلٌ للضبط",
    "WEAVER_SEARCH_ROUNDS" in _src and W._MAX_SEARCH_ROUNDS >= 2)
chk("وكلُّ جولةٍ تُسجَّل للمستخدم", "جولات البحث" in _src)
chk("وسببُ التوقّف يُسجَّل", "قرار إعادة البحث" in _src)
chk("ولا تُشغَّل بلا نموذج", "while self.llm_fn" in _src)

print("\n" + "═" * 70)
print(" ٤) ولا نداءَ مكرَّرٌ: الاستعلامُ الذي كتبه النموذج يُمرَّر لا يُعاد طلبه")
print("═" * 70)
o4 = W.__new__(W)
o4.system_main = None
o4.llm_fn = _M(json.dumps({"queries": ["لن يُستعمل"]}))
o4.searched = []
o4._scholarly_search = lambda q, l, n, **k: (o4.searched.append(q)
                                             or [{"title": "بحثٌ عربيّ",
                                                  "doi": "10.1/z"}])
o4._judge_relevance = lambda rs, *a, **k: (list(rs), [])
out = o4._top_up_language([], {}, "ar", 3, "ن", "ar",
                          queries=["استعلامُ الحلقة"])
chk("استُعمل استعلامُ الحلقة", o4.searched and o4.searched[0] == "استعلامُ الحلقة")
chk("ولم يُنادَ النموذجُ ثانيةً لصياغته", o4.llm_fn.calls == 0)
chk("وعاد بالنتيجة", len(out) == 1)

print("\n" + "═" * 70)
print(" النتيجة: " + ("PASS ✅" if ok else "FAIL ❌"))
print("═" * 70)
sys.exit(0 if ok else 1)
