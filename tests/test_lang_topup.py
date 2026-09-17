# -*- coding: utf-8 -*-
"""طبقةُ البحث: النقصُ بلغةٍ يُستدرَك بالبحث، لا يُعلَن ويُطبع.

«أريدك ٩ مراجع عربية» عادت بواحدٍ عربيٍّ في البِركة، فسجّل النظامُ «١ من ٨»
سجلاً أميناً… ثم طبع القائمةَ كما هي. الترتيبُ لا يخلق ما لم يُوجَد، وإعلانُ
النقص ليس جواباً عنه.

وسببُ ضياع تلك الأدبيات سببان اثنان، كلاهما مقيسٌ لا مُخمَّن:
  ١) العدُّ كان يقرأ حقلَ `language` في الفهرس، والفهارسُ تتركه فارغاً أكثرَ
     ممّا تملؤه — فعملٌ عنوانُه عربيٌّ كان يُعَدُّ غيرَ عربيّ ويُرتَّب آخِراً.
  ٢) الاستعلامُ كان مكتوباً بكلمات اللغة الأخرى، والأدبياتُ العربية مفهرسةٌ
     بالمصطلحات التي تستعملها هي؛ ولا قائمةَ عباراتٍ في هذا الملف تحمل تلك
     المصطلحات لكلّ موضوع — فالنموذجُ هو الذي يصوغها، كما في الكتالوج.

هذه الاختبارات تثبت الأمرين، وتثبت أن كلَّ تعذّرٍ يُسجَّل ولا ينهار."""
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
print(" ١) لغةُ المرجع تُقرأ من الفهرس، فإن سكت فمن خطّ عنوانه")
print("═" * 70)
chk("الفهرسُ يقول en ⟶ en مهما كان العنوان",
    W._source_lang({"lang": "en", "title": "أثر النوم على التحصيل"}) == "en")
chk("وسكت الفهرسُ وعنوانُه عربيّ ⟶ ar",
    W._source_lang({"title": "أثر النوم على التحصيل الدراسي"}) == "ar")
chk("وسكت وعنوانُه لاتينيّ ⟶ en",
    W._source_lang({"title": "Sleep and academic achievement"}) == "en")
chk("ولا عنوانَ ولا فهرس ⟶ لا ادّعاء", W._source_lang({"title": "2024 —"}) == "")
chk("وسجلٌّ فارغ لا ينهار", W._source_lang(None) == "")
chk("والرابطُ لا يُحسب حروفاً لاتينية",
    W._source_lang({"title": "النوم https://example.com/sleep-study"}) == "ar")

print("\n" + "═" * 70)
print(" ٢) وهويةُ المرجع معرّفُه وعنوانُه معاً — فلا يدخل مرّتين")
print("═" * 70)
a = {"title": "Solar Energy:  A Viable Pathway", "doi": "10.1/ABC"}
b = {"title": "solar energy: a viable pathway", "doi": "10.2/xyz"}
chk("عملٌ واحدٌ تحت معرّفين ⟶ يلتقيان بالعنوان",
    bool(W._source_keys(a) & W._source_keys(b)))
chk("والمعرّفُ نفسُه يلتقي",
    bool(W._source_keys({"title": "X", "doi": "10.1/abc"})
         & W._source_keys({"title": "Y", "doi": "10.1/ABC/"})))
chk("وبلا عنوانٍ لا هويةَ تُدّعى", W._source_keys({"doi": "10.1/q"}) == set())


class _Mem:
    def set_status(self, *a, **k):
        pass


class _Model:
    """نموذجٌ يصوغ استعلاماتٍ بالمصطلحات التي تستعملها تلك الأدبيات."""

    def __init__(self, reply):
        self.reply, self.prompt, self.calls = reply, "", 0

    def __call__(self, prompt, **kw):
        self.calls += 1
        self.prompt = prompt
        return self.reply


def _orch(model, found, judge="all"):
    o = W.__new__(W)
    o.llm_fn = model
    o.system_main = None
    o.searched = []

    def _search(q, lg, lim, **kw):
        o.searched.append((q, lg))
        return list(found)
    o._scholarly_search = _search
    if judge == "all":
        o._judge_relevance = lambda rs, *a, **k: (list(rs), [])
    elif judge == "silent":
        o._judge_relevance = lambda rs, *a, **k: (None, None)
    else:
        o._judge_relevance = lambda rs, *a, **k: (list(rs)[:1], list(rs)[1:])
    return o


AR1 = {"title": "أثر النوم على التحصيل الدراسي", "doi": "10.9/ar1"}
AR2 = {"title": "جودة النوم لدى طلبة الجامعة", "doi": "10.9/ar2"}
EN1 = {"title": "Sleep quality among students", "doi": "10.9/en1",
       "lang": "en"}
HELD = [{"title": "Sleep and grades", "doi": "10.9/en0", "lang": "en"}]

print("\n" + "═" * 70)
print(" ٣) النموذجُ يرى الفجوة ويصوغ الاستعلام — والكودُ ينفّذ ويعُدّ")
print("═" * 70)
m = _Model(json.dumps({"queries": ["جودة النوم والتحصيل الدراسي",
                                   "الحرمان من النوم لدى الطلبة"]},
                      ensure_ascii=False))
o = _orch(m, [AR1, AR2, EN1])
card = {}
out = o._top_up_language(list(HELD), card, "ar", 8, "أثر النوم", "ar", _Mem())
chk("النموذجُ رأى حجمَ النقص", "8" in m.prompt or "٨" in m.prompt)
chk("ورأى الموضوع", "أثر النوم" in m.prompt)
chk("ورأى ما بأيدينا كي لا يعيده", "Sleep and grades" in m.prompt)
chk(f"واستُعمل استعلاماه: {o.searched}",
    [q for q, _ in o.searched] == ["جودة النوم والتحصيل الدراسي",
                                   "الحرمان من النوم لدى الطلبة"])
chk(f"وعاد بالعربيّ وحده ({len(out)})",
    len(out) == 2 and all("أثر" in x["title"] or "جودة" in x["title"]
                          for x in out))
chk("والإنجليزيُّ لم يُحشَ في نقصٍ عربيّ",
    all(x.get("doi") != "10.9/en1" for x in out))
chk("ولغةُ الجديد مثبتةٌ كي يراها العدّ",
    all(x.get("lang") == "ar" for x in out))
chk("ولا تكرارَ بين الاستعلامين", len({x["doi"] for x in out}) == len(out))
_d = (card.get("decisions") or {}).get("استدراك لغة المراجع") or {}
chk(f"والقرارُ مسجَّلٌ باسم النموذج: {_d.get('value')}",
    _d.get("by") == "model" and "+2" in str(_d.get("value")))

print("\n" + "═" * 70)
print(" ٤) ولا يُعاد ما هو بأيدينا أصلاً")
print("═" * 70)
o = _orch(_Model(json.dumps({"queries": ["ق"], "x": 1})), [AR1, AR2])
chk("استعلامٌ أقصرُ من ثلاثة أحرف يُرفض ⟶ لا بحث",
    o._top_up_language([], {}, "ar", 3, "ن", "ar") == [] and not o.searched)
o = _orch(_Model(json.dumps({"queries": ["النوم والتحصيل"]},
                            ensure_ascii=False)), [AR1, AR2])
_held = [dict(AR1, doi="10.9/OTHER")]          # العملُ نفسُه تحت معرّفٍ آخر
out = o._top_up_language(_held, {}, "ar", 5, "ن", "ar")
chk(f"العملُ المُقتنى تحت DOI آخرَ لا يدخل ثانيةً ({len(out)})",
    len(out) == 1 and out[0]["doi"] == "10.9/ar2")

print("\n" + "═" * 70)
print(" ٥) وما يُستدرَك يمرّ على الحَكَم نفسِه — لا باب خلفيّ")
print("═" * 70)
o = _orch(_Model(json.dumps({"queries": ["النوم"]}, ensure_ascii=False)),
          [AR1, AR2], judge="half")
card = {}
out = o._top_up_language([], card, "ar", 5, "ن", "ar")
chk(f"الحَكَمُ استبعد ما لا يخصّ الموضوع ({len(out)})", len(out) == 1)
chk("والفرزُ مسجَّل",
    "فرز استدراك اللغة" in (card.get("decisions") or {}))
o = _orch(_Model(json.dumps({"queries": ["النوم"]}, ensure_ascii=False)),
          [AR1, AR2], judge="silent")
card = {}
out = o._top_up_language([], card, "ar", 5, "ن", "ar")
chk("وصمتَ الحَكَمُ ⟶ تُسحب الإضافةُ ولا تُدخَل بلا حكم", out == [])
_notes = card.get("skipped_steps") or []
chk("ويُقال لماذا",
    any("لم يحكم النموذج" in str(n) for n in _notes), str(_notes))
chk("ومرّةً واحدةً لا روايتين لحدثٍ واحد",
    not any("لم تُعِد" in str(n) for n in _notes), str(_notes))

print("\n" + "═" * 70)
print(" ٦) وكلُّ تعذّرٍ يُقال، ولا ينهار شيء")
print("═" * 70)


class _Broken:
    def __call__(self, prompt, **kw):
        raise ConnectionError("403 Forbidden")


o = _orch(_Broken(), [AR1])
card = {}
chk("نموذجٌ يرفض بـ403 ⟶ [] لا انهيار",
    o._top_up_language([], card, "ar", 5, "ن", "ar") == [])
chk("والسببُ مسجَّل",
    any("ConnectionError" in str(n) for n in (card.get("skipped_steps") or [])),
    str(card.get("skipped_steps"))[:120])
o = _orch(_Model("ليس JSON إطلاقاً"), [AR1])
chk("وردٌّ غيرُ صالح ⟶ []", o._top_up_language([], {}, "ar", 5, "ن", "ar") == [])
o = _orch(None, [AR1])
card = {}
chk("وبلا نموذجٍ ⟶ [] ولا بحث",
    o._top_up_language([], card, "ar", 5, "ن", "ar") == [] and not o.searched)
chk("ويُقال إنّه بلا نموذج",
    any("نموذج" in str(n) for n in (card.get("skipped_steps") or [])))
o = _orch(_Model(json.dumps({"queries": ["النوم"]}, ensure_ascii=False)), [])
card = {}
chk("والقواعدُ لم تُعِد جديداً ⟶ يُعلَن ولا يُسَدُّ بلغةٍ أخرى",
    o._top_up_language([], card, "ar", 5, "ن", "ar") == []
    and any("لم تُعِد" in str(n) for n in (card.get("skipped_steps") or [])))
o = _orch(_Model(json.dumps({"queries": ["النوم"]}, ensure_ascii=False)), [AR1])
chk("ولغةٌ فارغة ⟶ لا شيء", o._top_up_language([], {}, "", 5, "ن", "ar") == [])

print("\n" + "═" * 70)
print(" ٧) ويُطفأ بمفتاحٍ واحد — توافقٌ كامل مع ما كان")
print("═" * 70)
os.environ["WEAVER_LANG_TOPUP"] = "0"
o = _orch(_Model(json.dumps({"queries": ["النوم"]}, ensure_ascii=False)), [AR1])
chk("WEAVER_LANG_TOPUP=0 ⟶ السلوكُ القديم بحرفه",
    o._top_up_language([], {}, "ar", 5, "ن", "ar") == []
    and not o.searched and o.llm_fn.calls == 0)
os.environ.pop("WEAVER_LANG_TOPUP")

print("\n" + "═" * 70)
print(" ٨) والمسارُ يستدعيه فعلاً، ويُصحّح سجلَّه بعد الاستدراك")
print("═" * 70)
_src = inspect.getsource(W._academic_search)
chk("مُستدعىً في طبقة البحث", "self._top_up_language(" in _src)
chk("ولغةُ ما لم يفهرسه الفهرسُ تُقرأ قبل العدّ",
    "self._source_lang(" in _src and "لغة المراجع غير المفهرسة" in _src)
chk("والسجلُّ يُعاد بعد نموّ البِركة", "_say_langs(results)" in _src
    and _src.count("_say_langs(results)") >= 2)
chk("واللغتان معاً: لكلٍّ حصّتُها", "_share" in _src and "for _wl in _plan" in _src)
chk("والتعذّرُ لا يُسقط البحثَ كلَّه", "except Exception as _tue" in _src)

print("\n" + "═" * 70)
print(" النتيجة: " + ("PASS ✅" if ok else "FAIL ❌"))
print("═" * 70)
sys.exit(0 if ok else 1)
