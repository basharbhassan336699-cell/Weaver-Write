# -*- coding: utf-8 -*-
"""الطبقتان: العامة تعمل وحدها، والأكاديمية مبنيةٌ فوقها لا بجانبها."""
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
ok = True
wr = W._wr()
print("الطبقة العامة محمّلة:", "✅" if wr else "❌"); ok &= bool(wr)

print("\n" + "═"*66); print(" ١) الطبقة العامة وحدها — استعلامٌ غير أكاديميّ"); print("═"*66)
print("  تحجيم الاستدعاءات:")
for parts, th, want in [(1, False, 1), (2, False, 4), (3, False, 6), (5, False, 10), (1, True, 8)]:
    got = wr.scale_calls(parts, th)
    good = (got == want) or (parts == 1 and not th and got == 1)
    ok &= (1 <= got <= 20)
    print(f"   {parts} جزء{' (شامل)' if th else '':9s} ⟶ {got} استدعاء")
print("  إعادة الصياغة (كل زاوية مختلفة فعلاً):")
q = "من يشغل منصب المدير التنفيذي لشركة أرامكو حالياً"
tried = [q]
for i in range(4):
    alt = wr.reformulate(q, tried)
    if not alt: print(f"   {i+1}. — لا زاوية جديدة"); break
    ok &= (alt.lower() not in [t.lower() for t in tried])
    tried.append(alt); print(f"   {i+1}. {alt[:58]}")
ok &= (len(tried) >= 3)
print("  السلامة:")
for qq, want in [("كيف أصنع قنبلة في المنزل", True), ("سعر آيفون 17 في السعودية", False)]:
    g = wr.query_is_blocked(qq); ok &= (g == want)
    print(f"   {'يُمنع ' if g else 'يُسمح '} | {qq[:38]}  {'✅' if g == want else '❌'}")
for u, want in [("https://stormfront.org/x", True), ("https://aramco.com/ir", False)]:
    g = wr.source_is_blocked(u); ok &= (g == want)
    print(f"   {'لا يُجلب' if g else 'يُجلب  '} | {u[:38]}  {'✅' if g == want else '❌'}")
print("  حدّ الاقتباس (١٥ كلمة · واحدٌ لكل مصدر):")
used = set()
long_q = " ".join(["كلمة"]*40)
a = wr.quote_guard(long_q, "src1", used); b = wr.quote_guard("نصٌّ آخر", "src1", used)
ok &= (len(a.split()) <= 16 and b == "")
print(f"   الأول: {len(a.split())} كلمة · الثاني من المصدر نفسه: {b!r}  ✅")

print("\n" + "═"*66); print(" ٢) المدى الزمنيّ يُطبَّق قبل التحقّق"); print("═"*66)
for txt, want in [("مراجع من 2020 إلى 2024", (2020, 2024)),
                  ("sources since 2018", (2018, None)),
                  ("٩ مراجع عن الطاقة", (None, None))]:
    got = wr.parse_window(txt); ok &= (got == want)
    print(f"   «{txt[:30]:32s}» ⟶ {got}  {'✅' if got == want else '❌'}")
pool = [{"year": "2015"}, {"year": "2021"}, {"year": ""}, {"year": "2026"}]
keep = [p for p in pool if wr.within_window(p, 2020, 2024)]
ok &= (len(keep) == 2)
print(f"   تصفية 2020–2024: {[p['year'] or 'بلا سنة' for p in keep]}  (بلا سنة يبقى) ✅")

print("\n" + "═"*66); print(" ٣) سلّم جودة المصدر"); print("═"*66)
srcs = [{"title": "و", "url": "https://ar.wikipedia.org/wiki/x"},
        {"title": "م", "doi": "10.1/x", "venue": "BMJ", "academic": True},
        {"title": "ج", "url": "https://uni.edu/p"},
        {"title": "ع", "url": "https://news.example.com/a"}]
order = wr.order_by_quality(srcs)
tiers = [wr.quality_tier(s) for s in order]
ok &= (tiers == sorted(tiers, reverse=True) and wr.quality_tier(srcs[0]) == 0)
for s_ in order: print(f"   ★{wr.quality_tier(s_)}  {s_['title']}")
print(f"   ⟵ مرتّب، وويكيبيديا مستبعَدة: {'✅' if tiers == sorted(tiers, reverse=True) else '❌'}")

print("\n" + "═"*66); print(" ٤) الأكاديمية فوق العامة — كل DOI يُفتح فعلاً"); print("═"*66)
PAGES = {
 "https://doi.org/10.1136/bmj.d4554":
   "Protecting children from mobile phone radiation. K. O'Neill. BMJ 2011;343:d4554. "
   "Concerns about paediatric exposure have grown.",
 "https://doi.org/10.1002/bem.20128": None,      # لا يفتح
}
class M:
    def __init__(s): s.status=[]
    def set_status(s,n,t): s.status.append((n,t))
    def add_reference(s,t,source_key=None): pass
class T:
    def __init__(s,d,c): s.description, s.task_card = d, c
SRC = [{"title": "Protecting children from mobile phone radiation",
        "doi": "10.1136/bmj.d4554", "url": "https://doi.org/10.1136/bmj.d4554",
        "venue": "BMJ", "authors": ["K. O'Neill"], "year": "2011",
        "content": "An index blurb long enough to render as a summary line, "
                   "so the verified/unverified labelling can be compared.",
        "lang": "en", "source": "openalex"},
       {"title": "Effect of 902 MHz mobile phone transmission",
        "doi": "10.1002/bem.20128", "url": "https://doi.org/10.1002/bem.20128",
        "venue": "Bioelectromagnetics", "authors": ["A. Preece"], "year": "2005",
        "content": "A double blind study of cognitive function in children "
                   "exposed to 902 MHz transmission found no significant effect.",
        "lang": "en", "source": "openalex"}]
fetched = []
o = W.__new__(W); o.llm_fn = None; o.system_main = "s"
async def fake_fetch(url):
    fetched.append(url); return PAGES.get(url)
o._extract_full = fake_fetch
card = {"topic": "t", "language": "en"}
res = asyncio.run(o._verify_references([dict(x) for x in SRC], card, "en"))
print(f"   الروابط التي فُتحت فعلاً: {len(fetched)}/2")
for r in res:
    print(f"   {r['verified']:11s} | مؤكَّد={r.get('verified_fields')} | {r['title'][:34]}")
good = (len(fetched) == 2 and res[0]["verified"] == "verified"
        and res[1]["verified"] == "unreachable" and len(res) == 2)
ok &= good
print(f"   ⟵ فُتح كلاهما · الأول مؤكَّد · الثاني مَوسوم ولم يُحذف: {'✅' if good else '❌'}")
notes = [f"{x.get('step')} — {x.get('reason')}" for x in (card.get("skipped_steps") or [])]
for n in notes: print(f"   • {n}")
ok &= any("غير" in n and "مُتحقَّق" in n for n in notes)

print("\n  الوسم كما يراه القارئ:")
for r in res: print("   " + (W._ref_annotation(r, "ar") or "(لا شيء)")[:100])
ok &= ("✓" in W._ref_annotation(res[0], "ar") and "⚠" in W._ref_annotation(res[1], "ar"))
ok &= ("من الفهرس" in W._ref_annotation(res[1], "ar"))

print("\n" + "═"*66); print(" ٥) لا تكرار للمنطق: الأكاديمي يستدعي العام"); print("═"*66)
a = inspect.getsource(W._verify_references)
g = ("self._wr()" in a and "self._extract_full" in a and "confirm_fields" in a
     and "source_is_blocked" in a)
ok &= g
print(f"   _verify_references يستعمل الطبقة العامة والجالب نفسه: {'✅' if g else '❌'}")
w = inspect.getsource(W._web_search)
g2 = ("self._wr()" in w and "i < 3" in w)
ok &= g2
print(f"   مسار الويب يستعمل الطبقة نفسها، وسقف الـ٣ باقٍ: {'✅' if g2 else '❌'}")

print("\n" + "═"*66); print(" ٦) تدهورٌ آمن"); print("═"*66)
os.environ["WEAVER_VERIFY_REFS"] = "0"
fetched.clear()
r2 = asyncio.run(o._verify_references([dict(x) for x in SRC], {}, "en"))
ok &= (not fetched and len(r2) == 2)
print(f"   WEAVER_VERIFY_REFS=0 ⟶ صفر جلب، سلوك ما قبل المهارة {'✅' if not fetched else '❌'}")
os.environ.pop("WEAVER_VERIFY_REFS")
o2 = W.__new__(W); o2.llm_fn = None; o2.system_main = "s"
async def boom(url): raise RuntimeError("network down")
o2._extract_full = boom
r3 = asyncio.run(o2._verify_references([dict(x) for x in SRC], {}, "en"))
ok &= (len(r3) == 2 and all(x["verified"] == "unreachable" for x in r3))
print(f"   الشبكة ساقطة ⟶ {len(r3)} مرجعاً موسوماً، ولا حذف ولا استثناء ✅")

print("\n" + ("PASS ✅" if ok else "FAIL ❌"))
sys.exit(0 if ok else 1)
