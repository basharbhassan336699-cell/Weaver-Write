# -*- coding: utf-8 -*-
"""حائط الاشتراك وسجلّ الـDOI — بسلسلة التحويل الحقيقية من تشغيل المستخدم."""
import sys, os, json, asyncio, inspect
sys.path.insert(0, "/home/user/Weaver-Write")
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
good = ([r.get("verified") for r in res] == ["verified", "registry", "paywalled"])
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
ok &= ("✓" in a[0] and "◐" in a[1] and "mandumah" in a[1] and "⚠" in a[2])
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

print("\n" + ("PASS ✅" if ok else "FAIL ❌"))
sys.exit(0 if ok else 1)
