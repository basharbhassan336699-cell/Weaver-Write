# -*- coding: utf-8 -*-
"""البابُ السابع: صفحةُ بحثٍ علميّ يقرأها النموذج.

أوبن كلاو طُلب منه تسعةُ مراجعَ عربيةٍ فأتى بتسعةٍ حقيقية — وكلُّها من
Google Scholar ومن مستودعاتِ جامعاتٍ عربية (الخليل، بغداد، بابل، الكويت،
بنك المعرفة المصري). وقال عن مسارِ OpenAlex عنده حرفياً: «٢٠ مرجعاً
بالإنجليزية أساساً».

فالنقصُ لم يكن في النموذج ولا في صياغة الاستعلام: هذا النظامُ يطرق ستّة
أبواب، والأدبُ العربيُّ خلف بابٍ سابع. وأوبن كلاو لم يستعمل واجهةَ برمجةٍ
لذلك الباب — فتح **صفحةَ نتائج** وترك النموذجَ يقرؤها. والنصفان موجودان هنا
أصلاً: `_extract_full` تمرّ على UniWeb (curl_impersonate: بصمةُ متصفّحٍ
حقيقيّ تتجاوز حجبَ الآليّات)، والنموذجُ يقرأ. لم يكونا موصولين بالمسار
الأكاديميّ قطّ."""
import sys, os, json, asyncio, inspect
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


PAGE = ("نتائج البحث\n"
        "الإعجاز العلمي في القرآن الكريم والحديث الشريف - ح ترتوري - 2002\n"
        "dspace.hebron.edu\n"
        "الهدايات الأخلاقية ودلالاتها من خلال القرآن الكريم - ن الثويني - "
        "مجلة الزهراء - 2024 - zjac.journals.ekb.eg\n") + ("ـ" * 300)

WORKS = {"works": [
    {"title": "الإعجاز العلمي في القرآن الكريم والحديث الشريف",
     "authors": ["حسام الدين ترتوري"], "year": "2002",
     "venue": "جامعة القدس", "url": "https://dspace.hebron.edu/x/104"},
    {"title": "الهدايات الأخلاقية ودلالاتها من خلال القرآن الكريم",
     "authors": ["نوف الثويني"], "year": "2024",
     "venue": "مجلة الزهراء", "url": "https://zjac.journals.ekb.eg/a.html"},
    {"title": "Scientific miracles in the Quran", "authors": ["X"],
     "year": "2020", "venue": "J. Studies", "url": "https://x.org/1"},
]}


def _orch(page, reply):
    o = W.__new__(W)
    o.system_main = None
    o.seen_url = ""

    async def _ex(url):
        o.seen_url = url
        return page
    o._extract_full = _ex
    o.llm_fn = (lambda prompt, **kw: (setattr(o, "saw", prompt) or reply)) \
        if reply is not None else None
    return o


run = asyncio.get_event_loop().run_until_complete

print("═" * 70)
print(" ١) يفتح صفحةَ بحثٍ علميّ مقيَّدةً باللغة المطلوبة")
print("═" * 70)
o = _orch(PAGE, json.dumps(WORKS, ensure_ascii=False))
card = {}
out = run(o._scholar_harvest("الإعجاز العلمي في القرآن", "ar", 9, card, "ar"))
chk("العنوانُ المفتوح محرّكُ مراجعَ علميّ", "scholar.google" in o.seen_url)
chk("وفيه نصُّ الطلب", "%D8%A7" in o.seen_url or "الإعجاز" in o.seen_url)
chk("ومقيَّدٌ بالعربية (lr=lang_ar)", "lang_ar" in o.seen_url, o.seen_url[:90])
chk("والنموذجُ رأى نصَّ الصفحة", "ترتوري" in getattr(o, "saw", ""))

print("\n" + "═" * 70)
print(" ٢) والنموذجُ يستخرج، والكودُ لا يحلّل HTML")
print("═" * 70)
chk(f"عادت {len(out)} أعمالٍ عربية", len(out) == 2, str([x['title'][:24] for x in out]))
chk("والإنجليزيُّ لم يدخل نقصاً عربياً",
    all("Scientific" not in x["title"] for x in out))
chk("والحقولُ كاملة", all(x.get("authors") and x.get("year")
                          and x.get("venue") and x.get("url") for x in out))
chk("ومصدرُها مُعلَن", all(x["source"] == "scholar" for x in out))
chk("وتُقبل في قائمة المراجع (مصدرٌ مفهرَس)",
    len(W._bib_sources(out, {}, "ar")[0]) == 2)
chk("والقرارُ مسجَّلٌ باسم النموذج",
    (card.get("decisions") or {}).get("بحث في محرّك المراجع العلمي", {})
    .get("by") == "model")

print("\n" + "═" * 70)
print(" ٣) وبابٌ مغلقٌ يُقال — لا يُقال «لم أجد»")
print("═" * 70)
o2 = _orch("", json.dumps(WORKS))
card2 = {}
chk("صفحةٌ محجوبة ⟶ []", run(o2._scholar_harvest("س", "ar", 9, card2, "ar")) == [])
chk("ويُقال إنّها لم تُفتح",
    any("لم تُفتح" in n["reason"] for n in (card2.get("skipped_steps") or [])),
    str(card2.get("skipped_steps"))[:110])
o3 = _orch(PAGE, "ليس JSON")
card3 = {}
chk("وردٌّ غيرُ صالح ⟶ [] ويُقال",
    run(o3._scholar_harvest("س", "ar", 9, card3, "ar")) == []
    and bool(card3.get("skipped_steps")))
o4 = _orch(PAGE, None)
chk("وبلا نموذجٍ ⟶ [] ولا فتحَ صفحة",
    run(o4._scholar_harvest("س", "ar", 9, {}, "ar")) == [] and not o4.seen_url)

print("\n" + "═" * 70)
print(" ٤) ويُطفأ بمفتاح، ويُستدعى في المسار")
print("═" * 70)
os.environ["WEAVER_SCHOLAR"] = "0"
o5 = _orch(PAGE, json.dumps(WORKS))
chk("WEAVER_SCHOLAR=0 ⟶ لا شيء إطلاقاً",
    run(o5._scholar_harvest("س", "ar", 9, {}, "ar")) == [] and not o5.seen_url)
os.environ.pop("WEAVER_SCHOLAR")
_src = inspect.getsource(W._academic_search)
chk("مُستدعىً في طبقة البحث", "self._scholar_harvest(" in _src)
# لم يعد يُفتح بشرطٍ مكتوبٍ في الكود: صار داخل الحلقة، لا تدور إلا وثمّة
# نقصٌ قائم (`_owed`)، والنموذجُ هو الذي يسمّي البابَ في كلّ جولة.
chk("ولا يُفتح إلا وثمّة نقصٌ قائم", "if not _owed:" in _src)
chk("والنموذجُ هو من يسمّي البابَ", '_v.get("door") == "scholar"' in _src)
chk("ولا يُكرَّر ما بأيدينا", "_seen_k" in _src)

print("\n" + "═" * 70)
print(" النتيجة: " + ("PASS ✅" if ok else "FAIL ❌"))
print("═" * 70)
sys.exit(0 if ok else 1)
