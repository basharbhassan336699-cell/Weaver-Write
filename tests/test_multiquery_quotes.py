# -*- coding: utf-8 -*-
"""استعلامٌ لكل جانب · وحدُّ الاقتباس من مصدرٍ مجلوب."""
import sys, os, json, asyncio, inspect
# THE TESTS ONLY RAN ON THE MACHINE THEY WERE WRITTEN ON. The repository
# root was hardcoded as an absolute path, so on any other checkout the insert
# pointed at a directory that does not exist and every file died on
# "No module named 'pipeline'" before running a single check. The root is
# where this file lives, one directory up — the way tests/smoke_pipeline.py
# already computes it — so the suite runs from any clone on any device.
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
for k in list(os.environ):
    if k.startswith("WEAVER_"): os.environ.pop(k)
from pipeline.orchestrator import WeaverOrchestrator as W
wr = W._wr()
ok = True

print("═"*66); print(" ١) استعلامٌ منفصلٌ لكل جانب، بعددٍ محجَّم"); print("═"*66)
print("  تحجيم الاستدعاءات:")
for n, want in [(1, 1), (2, 4), (3, 6), (6, 12)]:
    g = wr.scale_calls(n); ok &= (g == want)
    print(f"   {n} جانب ⟶ {g} استدعاء  {'✅' if g == want else '❌ '+str(want)}")

calls = []
_i = [0]
def _fake(cls, q, l, lim, timeout=14, wide=False):
    calls.append(q); _i[0] += 1
    return [{"title": f"ورقة {_i[0]}", "doi": f"10.1/{_i[0]}",
             "url": f"http://x/{_i[0]}", "content": "", "lang": "ar",
             "venue": "v", "year": "2020", "authors": []}]
W._scholarly_search = classmethod(_fake)
W._crossref_record = classmethod(lambda c, d, timeout=15: None)
def model(p, **k):
    if "facets" in p:
        return json.dumps({"query": "الإعجاز العلمي والأخلاقي", "refs_lang": "ar",
                           "facets": ["الإعجاز العلمي", "الإعجاز الأخلاقي"],
                           "note": ""}, ensure_ascii=False)
    if '"keep"' in p: return '{"keep":[1,2,3],"drop":[]}'
    return ""
class M:
    def set_status(s, n, t): pass
    def add_reference(s, t, source_key=None): pass
class T:
    def __init__(s, d, c): s.description, s.task_card = d, c
o = W.__new__(W); o.llm_fn = model; o.system_main = "s"
async def nofetch(u): return None
o._extract_full = nofetch
card = {"topic": "الإعجاز العلمي والأخلاقي", "language": "ar",
        "reference_count": 9}
asyncio.run(o._academic_search(T("اكتب 9 مراجع", card), M()))
print(f"\n  استعلامات نُفِّذت: {len(calls)}")
for c in calls: print(f"   · {c}")
g1 = (len(calls) == 3 and calls[1] == "الإعجاز العلمي"
      and calls[2] == "الإعجاز الأخلاقي")
ok &= g1
print(f"  ⟵ المدمج ثم جانبٌ جانب: {'✅' if g1 else '❌'}")
d = (card.get("decisions") or {}).get("استعلامات الجوانب")
ok &= bool(d)
print(f"  القرار مسجَّل: {d}  {'✅' if d else '❌'}")

print("\n  الإيقاف والحدود:")
# استعلام لغة الطلب آليةٌ مستقلّة ببوّابتها الخاصة: إطفاء استعلامات
# الجوانب لا يُطفئها، وهو المقصود — لغة المستخدم مطلبٌ قائمٌ بذاته.
os.environ["WEAVER_MULTI_QUERY"] = "0"; calls.clear()
asyncio.run(o._academic_search(T("اكتب", {"topic": "أ ب", "language": "ar",
                                          "reference_count": 9}), M()))
_no_facets = not any(c in ("الإعجاز العلمي", "الإعجاز الأخلاقي") for c in calls)
ok &= _no_facets
print(f"   WEAVER_MULTI_QUERY=0 ⟶ {len(calls)} استعلام، بلا جوانب "
      f"{'✅' if _no_facets else '❌'} {calls}")
os.environ["WEAVER_LANG_QUERY"] = "0"; calls.clear()
asyncio.run(o._academic_search(T("اكتب", {"topic": "أ ب", "language": "ar",
                                          "reference_count": 9}), M()))
ok &= (len(calls) == 1)
print(f"   وبإطفاء الاثنتين      ⟶ {len(calls)} استعلام "
      f"{'✅' if len(calls)==1 else '❌'}")
os.environ.pop("WEAVER_LANG_QUERY"); os.environ.pop("WEAVER_MULTI_QUERY")
def model1(p, **k):
    if "facets" in p:
        return json.dumps({"query": "س", "refs_lang": "ar",
                           "facets": ["جانبٌ واحد"], "note": ""},
                          ensure_ascii=False)
    return '{"keep":[1],"drop":[]}'
o.llm_fn = model1; calls.clear()
asyncio.run(o._academic_search(T("اكتب", {"topic": "س", "language": "ar",
                                          "reference_count": 9}), M()))
ok &= (len(calls) == 1)
print(f"   جانبٌ واحد ⟶ {len(calls)} استعلام (لا تبديد) {'✅' if len(calls)==1 else '❌'}")

print("\n" + "═"*66); print(" ٢) حدّ الاقتباس من مصدرٍ مجلوب"); print("═"*66)
used = set()
long_t = " ".join(f"كلمة{i}" for i in range(40))
a = wr.quote_guard(long_t, "s1", used)
b = wr.quote_guard("اقتباسٌ ثانٍ من المصدر نفسه", "s1", used)
c = wr.quote_guard("من مصدرٍ آخر", "s2", used)
ok &= bool(len(a.split()) <= 16 and b == "" and c)
print(f"   الأول من s1 : {len(a.split())} كلمة (حدّ {wr.MAX_QUOTE_WORDS}) ✅")
print(f"   الثاني من s1: {b!r} ← اقتباسٌ واحدٌ لكل مصدر ✅")
print(f"   من s2       : {c!r} ✅")

print("\n  التدقيق على المسوّدة:")
SRC = [{"key": "s1", "url": "http://a", "content":
        "تشير الدراسات الحديثة إلى أن التعرض المطول للشاشات قبل النوم يؤخر "
        "إفراز الميلاتونين ويقلل من كفاءة النوم العميق لدى المراهقين بنسبة "
        "تصل إلى ثلاثين بالمئة في المتوسط"}]
COPIED = ("تشير الدراسات الحديثة إلى أن التعرض المطول للشاشات قبل النوم يؤخر "
          "إفراز الميلاتونين ويقلل من كفاءة النوم العميق لدى المراهقين")
PARA = "يؤثّر ضوء الشاشة ليلاً في هرمون النوم، فيقلّ عمقه لدى الصغار."
for nm, draft, want in [("نسخٌ حرفيّ طويل", COPIED, True),
                        ("إعادة صياغة", PARA, False)]:
    n = W._verbatim_overlap(draft, SRC)
    g = (bool(n) == want)
    ok &= g
    print(f"   {nm:18s} ⟶ أطول تطابق {n} كلمة  {'✅' if g else '❌'}")

print("\n  تعليمة إعادة الصياغة تصل الكاتب:")
for nm, card, sec, want in [
  ("بمصادر، بلا متطلّبات", {"sources": [{"k": 1}]}, "المبحث", True),
  ("بلا مصادر",            {},                      "المبحث", False),
  ("قائمة المراجع",        {"sources": [{"k": 1}]}, "قائمة المراجع", False)]:
    d = W._requirements_directive(card, sec, "ar")
    g = (("أعِد صياغته" in d) is want)
    ok &= g
    print(f"   {nm:22s} ⟶ {'فيها' if 'أعِد صياغته' in d else 'لا'}  {'✅' if g else '❌'}")
d_en = W._requirements_directive({"sources": [{"k": 1}]}, "Chapter", "en")
ok &= ("Reword" in d_en)
print(f"   بالإنجليزية            ⟶ {'✅' if 'Reword' in d_en else '❌'}")

print("\n  ووصلُ التدقيق في طبقة ٦.٦:")
a = inspect.getsource(W)
g = ("_verbatim_overlap(_draft" in a and "حدّ الاقتباس" in a)
ok &= g
print(f"   المسوّدة تُقاس ضدّ كل مصدرٍ مجلوب: {'✅' if g else '❌'}")

print("\n" + ("PASS ✅" if ok else "FAIL ❌"))
sys.exit(0 if ok else 1)
