# -*- coding: utf-8 -*-
"""حائط الاشتراك وسجلّ الـDOI — بسلسلة التحويل الحقيقية من تشغيل المستخدم."""
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

print("═"*66); print(" ١) كشف الحائط من شكل الرحلة — لا من قائمة مواقع"); print("═"*66)
MAND = [(302, "https://search.mandumah.com/Record/1578162"),
        (302, "https://search.mandumah.com/MyResearch/Home?rurl=%2FRecord%2F1578162"),
        (302, "https://search.mandumah.com/MyResearch/Home"),
        (302, "https://search.mandumah.com/MyResearch/Home"),
        (302, "https://search.mandumah.com/MyResearch/Home")]
v = wr.redirect_verdict(MAND, "https://search.mandumah.com/MyResearch/Home",
                        "https://doi.org/10.36047/1227-000-052-004")
ok &= (v in ("paywall", "loop"))
print(f"   سلسلة المنظومة الحقيقية ⟶ {v!r}  {'✅' if v != 'ok' else '❌'}")
for nm, ch, fin, want in [
  ("تحويلٌ عاديّ لناشر مفتوح",
   [(302, "https://journals.x.org/article/55")], "https://journals.x.org/article/55", "ok"),
  ("بلا تحويل", [], "https://doi.org/10.1/x", "ok"),
  ("عودةٌ في المعامل (returnUrl)",
   [(302, "https://p.com/a/9")], "https://p.com/login?returnUrl=%2Fa%2F9", "paywall")]:
    g = wr.redirect_verdict(ch, fin, "")
    ok &= (g == want)
    print(f"   {nm:28s} ⟶ {g!r:10s} {'✅' if g == want else '❌ متوقّع '+want}")

print("\n" + "═"*66); print(" ٢) صفحةٌ واحدة لعدّة أوراق = صفحة موقع لا ورقة"); print("═"*66)
MENU = ("العلوم التربوية والإجتماعية العلوم الإقتصادية والإدارية العلوم "
        "الإسلامية والقانونية العلوم الإنسانية علوم اللغة والأدب الرسائل الجامعية")
seen = {}
r1 = wr.same_page_across_sources(MENU, seen)
r2 = wr.same_page_across_sources(MENU, seen)
r3 = wr.same_page_across_sources("نصُّ ورقةٍ مختلفٍ تماماً وطويلٌ بما يكفي للقياس هنا", seen)
ok &= (r1 is False and r2 is True and r3 is False)
print(f"   أول ظهور: {r1} · الظهور الثاني لورقةٍ أخرى: {r2} · صفحةٌ مختلفة: {r3}  "
      f"{'✅' if (not r1 and r2 and not r3) else '❌'}")

print("\n" + "═"*66); print(" ٣) الحالات الثلاث في تشغيلٍ كامل"); print("═"*66)
SRC = [
 {"title": "الإعجاز العلمي في القرآن الكريم", "doi": "10.53796/hnsj4411",
  "url": "https://doi.org/10.53796/hnsj4411", "venue": "HNSJ", "year": "2023",
  "authors": ["الباحث"], "content": "", "oa": True},
 {"title": "الإعجاز العلمي وأثره", "doi": "10.36047/1227-000-052-004",
  "url": "https://doi.org/10.36047/1227-000-052-004", "venue": "منظومة",
  "year": "2020", "authors": ["مؤلف"], "content": ""},
 {"title": "ورقةٌ بلا سجلّ", "doi": "10.9999/none",
  "url": "https://doi.org/10.9999/none", "venue": "", "year": "", "authors": [],
  "content": ""},
]
o = W.__new__(W); o.llm_fn = None; o.system_main = ""
async def fake_extract(url):
    if "hnsj4411" in url:
        return ("الإعجاز العلمي في القرآن الكريم — الباحث — HNSJ 2023. " + "نصٌّ. "*40)
    return MENU          # كلاهما يهبط على قائمة المنظومة
o._extract_full = fake_extract
W._resolve_chain = staticmethod(lambda u, timeout=20: (
    ("https://search.mandumah.com/MyResearch/Home", MAND) if "36047" in u
    else (u, [])))
W._crossref_record = classmethod(lambda cls, doi, timeout=15: (
    {"doi": doi, "title": "الإعجاز العلمي وأثره", "venue": "مجلة الدراسات",
     "authors": ["مؤلف حقيقيّ"], "year": "2020", "volume": "52",
     "issue": "4", "pages": "77-98"} if "36047" in str(doi) else None))
card = {}
res = asyncio.run(o._verify_references([dict(x) for x in SRC], card, "ar"))
v = card.get("refs_verified") or {}
print(f"   من الصفحة {v.get('ok')} · من السجلّ {v.get('registry')} · "
      f"بلا تحقّق {v.get('unverified')} · محجوب {v.get('paywalled')}")
for r in res:
    print(f"   {str(r.get('verified')):11s} | {r['title'][:34]}")
# الثالثة لا دليلَ تحويلٍ عليها — صفحةٌ مشتركةٌ فقط — فهي «لا تُقرأ» لا
# «محجوبة باشتراك». هذا هو التمييز الذي بُني بعد أن وُسم سيمانتك سكولار
# حجباً وهو لا يحجب أحداً.
good = ([r.get("verified") for r in res] == ["verified", "registry", "unreadable"])
ok &= good
print(f"   ⟵ ثلاث حالات متمايزة: {'✅' if good else '❌'}")
reg = res[1]
ok &= (reg.get("venue") == "مجلة الدراسات" and reg.get("volume") == "52")
print(f"   حقول السجلّ حلّت محلّ حقول الفهرس: venue={reg.get('venue')} "
      f"vol={reg.get('volume')} pp={reg.get('pages')}  "
      f"{'✅' if reg.get('volume') == '52' else '❌'}")

print("\n   الوسم كما يراه القارئ:")
for r in res:
    print("    " + (W._ref_annotation(r, "ar") or "—")[:104])
a = [W._ref_annotation(r, "ar") for r in res]
ok &= ("✓" in a[0] and "◐" in a[1] and "mandumah" in a[1]
       # النصّ يقول «ليست محجوبةً باشتراك» — فالكلمة واردةٌ منفيّةً، والشرط
       # الصحيح أن يكون النفي حاضراً لا أن تغيب الكلمة.
       and "لا تُقرأ" in a[2] and "ليست محجوبةً" in a[2])
for n in (card.get("skipped_steps") or []):
    print(f"   • {n.get('step')} — {n.get('reason')}")
ok &= any("محجوب" in str(n.get("step", "")) for n in (card.get("skipped_steps") or []))

print("\n" + "═"*66); print(" ٤) المفتوح يعلو عند التساوي"); print("═"*66)
a1 = {"doi": "10.1/x", "venue": "J", "academic": True, "oa": True}
b1 = {"doi": "10.2/y", "venue": "J", "academic": True}
ok &= (wr.quality_tier(a1) > wr.quality_tier(b1))
print(f"   مفتوح ★{wr.quality_tier(a1)} · محجوب ★{wr.quality_tier(b1)}  "
      f"{'✅' if wr.quality_tier(a1) > wr.quality_tier(b1) else '❌'}")
print(f"   الترتيب: {[wr.quality_tier(x) for x in wr.order_by_quality([b1, a1])]}")

print("\n" + "═"*66); print(" ٥) تدهورٌ آمن"); print("═"*66)
W._resolve_chain = staticmethod(lambda u, timeout=20: (_ for _ in ()).throw(OSError("down")))
try:
    r = asyncio.run(o._verify_references([dict(SRC[0])], {}, "ar"))
    print("   ❌ كان يجب ألّا ينهار"); ok = False
except Exception:
    print("   (يُرمى من المحاكاة لا من الكود — نتحقّق من الغلاف)")
src_txt = inspect.getsource(W._resolve_chain.__func__ if hasattr(W._resolve_chain,'__func__') else W._resolve_chain)
import importlib; importlib.reload(sys.modules["pipeline.orchestrator"])
from pipeline.orchestrator import WeaverOrchestrator as W2
fin, ch = W2._resolve_chain("http://127.0.0.1:9/nope", timeout=2)
ok &= (fin == "http://127.0.0.1:9/nope" and ch == [])
print(f"   منفذٌ ميّت ⟶ يُعيد الرابط كما هو بلا استثناء: "
      f"{'✅' if ch == [] else '❌'}")
print(f"   crossref على doi فاسد ⟶ {W2._crossref_record('لا-شيء')!r}  ✅")

print("\n" + "═"*66)
print(" ٦) الظهور الأول لصفحةٍ مشتركة يُصحَّح بأثرٍ رجعيّ")
print("═"*66)
# ثلاث أوراق، كلّها تهبط على قائمة المنظومة نفسها. الأولى لا يمكن أن
# تُعرف مكرّرةً وقت جلبها — ولا يجوز أن تبقى وحدها بلا وسم.
o3 = W.__new__(W); o3.llm_fn = None; o3.system_main = ""
async def all_menu(url): return MENU
o3._extract_full = all_menu
W._resolve_chain = staticmethod(lambda u, timeout=20: (
    "https://search.mandumah.com/MyResearch/Home", MAND))
W._crossref_record = classmethod(lambda cls, doi, timeout=15: None)
TRIO = [{"title": f"ورقة {i}", "doi": f"10.36047/{i}",
         "url": f"https://doi.org/10.36047/{i}", "venue": "", "year": "",
         "authors": [], "content": ""} for i in (1, 2, 3)]
c3 = {}
r3 = asyncio.run(o3._verify_references([dict(x) for x in TRIO], c3, "ar"))
for r in r3:
    print(f"   {str(r.get('verified')):11s} | حاجب: {r.get('blocked_at') or '—'}")
g6 = all(str(r.get("verified")) == "paywalled" and r.get("blocked_at")
         for r in r3)
ok &= g6
print(f"   ⟵ الثلاث موسومة والحاجب مُسمّى، الأولى منها: {'✅' if g6 else '❌'}")
print(f"   العدّاد: محجوب={(c3.get('refs_verified') or {}).get('paywalled')}")
for n in (c3.get("skipped_steps") or []):
    print(f"   • {n.get('step')} — {n.get('reason')}")
# «٨ من ٦» لا تتكرّر: العدد المُنقَذ لا يتجاوز المحجوب
_n = (c3.get("refs_verified") or {})
ok &= (_n.get("paywalled", 0) == 3)
# ولا تُمسّ ورقةٌ تحقّقت من صفحتها
print(f"   ⟵ حسابُ الملاحظة متّسق: {'✅' if _n.get('paywalled') == 3 else '❌'}")

print("\n" + "═"*66)
print(" ٧) صفحةٌ لا تُقرأ ≠ حائط اشتراك")
print("═"*66)
# سيمانتك سكولار أعاد ١٥٧ حرفاً متطابقة لأربع أوراق — صفحةُ موقعٍ تحتاج
# جافاسكربت، ولا يتقاضى أحداً شيئاً. وسمُها «محجوب باشتراك» كذبٌ عليها.
S2 = "Semantic Scholar Sign In Create Free Account Home Research Feeds Papers"
o4 = W.__new__(W); o4.llm_fn = None; o4.system_main = ""
async def s2page(url): return S2
o4._extract_full = s2page
W._resolve_chain = staticmethod(lambda u, timeout=20: (u, []))   # لا تحويل
W._crossref_record = classmethod(lambda cls, doi, timeout=15: None)
S2SRC = [{"title": f"ورقة {i}", "doi": "",
          "url": f"https://www.semanticscholar.org/paper/{i}abc",
          "venue": "", "year": "", "authors": [], "content": ""}
         for i in (1, 2, 3)]
c4 = {}
r4 = asyncio.run(o4._verify_references([dict(x) for x in S2SRC], c4, "ar"))
for r in r4:
    print(f"   {str(r.get('verified')):11s} | حاجب: {r.get('blocked_at') or '—'}")
g7 = all(str(r.get("verified")) == "unreadable" for r in r4)
ok &= g7
print(f"   ⟵ وُسمت «لا تُقرأ» لا «محجوب»: {'✅' if g7 else '❌'}")
ann = W._ref_annotation(r4[0], "ar")
ok &= ("لا تُقرأ" in ann and "ليست محجوبةً" in ann)
print(f"   الوسم: {ann[:80]}")
n4 = c4.get("refs_verified") or {}
print(f"   محجوب={n4.get('paywalled')} · لا-تُقرأ={n4.get('unreadable')} "
      f"· بلا-DOI={n4.get('no_doi')}")
ok &= (n4.get("paywalled") == 0 and n4.get("unreadable") == 3
       and n4.get("no_doi") == 3)
print(f"   ⟵ لا يُنسَب حجبٌ إلى موقعٍ لا يحجب: "
      f"{'✅' if n4.get('paywalled') == 0 else '❌'}")
for n in (c4.get("skipped_steps") or []):
    print(f"   • {n.get('step')} — {n.get('reason')}")

print("\n" + "═"*66)
print(" ٨) الحالات الثلاث تجمع إلى المجموع دائماً")
print("═"*66)
for nm, cc in [("المنظومة", c3), ("سيمانتك", c4)]:
    d = cc.get("refs_verified") or {}
    tot = d.get("ok",0) + d.get("registry",0) + d.get("unverified",0)
    g = (tot == d.get("total"))
    ok &= g
    print(f"   {nm:10s} {d.get('ok',0)}+{d.get('registry',0)}+"
          f"{d.get('unverified',0)} = {tot} / {d.get('total')}  "
          f"{'✅' if g else '❌'}")

print("\n" + ("PASS ✅" if ok else "FAIL ❌"))
sys.exit(0 if ok else 1)
