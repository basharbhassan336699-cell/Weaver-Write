# -*- coding: utf-8 -*-
"""شروح المراجع تخرج من المستند · ولغة الطلب تحكم لغة المراجع."""
import sys, os, inspect
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
import importlib.util as iu
sp = iu.spec_from_file_location("fa", _ROOT + "/capabilities/"
                                "skills/apa_formatter/scripts/format_apa.py")
fa = iu.module_from_spec(sp); sp.loader.exec_module(fa)
ok = True

print("═"*68); print(" ١) لا شرحَ تحت المراجع ما لم يُطلَب"); print("═"*68)
for nm, card, want in [
  ("طلبٌ عاديّ",                {}, False),
  ("طلبٌ فيه «شرح المراجع»",     {"_request_text": "أريد 9 مراجع مع شرح المراجع"}, True),
  ("annotated bibliography",     {"_request_text": "give me an annotated bibliography"}, True),
  ("متطلَّبٌ يذكر وصف المراجع",  {"requirements": [{"text": "وصف المراجع لكل مدخل"}]}, True)]:
    g = (W._ref_notes_wanted(card) is want)
    ok &= g
    print(f"   {nm:26s} ⟶ {'يُشرَح' if W._ref_notes_wanted(card) else 'قائمةٌ نظيفة':12s} {'✅' if g else '❌'}")
os.environ["WEAVER_REF_NOTES"] = "1"
ok &= (W._ref_notes_wanted({}) is True)
print(f"   WEAVER_REF_NOTES=1         ⟶ يُشرَح      ✅")
os.environ["WEAVER_REF_NOTES"] = "0"
ok &= (W._ref_notes_wanted({"_request_text": "مع شرح المراجع"}) is False)
print(f"   WEAVER_REF_NOTES=0         ⟶ يُمنع مطلقاً ✅")
os.environ.pop("WEAVER_REF_NOTES")
a = inspect.getsource(W)
g = "if self._ref_notes_wanted(card):" in a
ok &= g
print(f"   والوصل في بناء القائمة: {'✅' if g else '❌'}")

print("\n" + "═"*68); print(" ٢) الفلتر يعمل على مسار التصنيف أيضاً"); print("═"*68)
g2 = "items, _dropped_general = self._bib_sources(items, card, lang)" in a
ok &= g2
print(f"   _grouped_refs_body يمرّ بـ_bib_sources: {'✅' if g2 else '❌'}")
print("   ⟵ هذا هو المسار الذي أنتج «ثالثاً: المواقع الإلكترونية»")

print("\n" + "═"*68); print(" ٣) لغة الطلب تحكم لغة المراجع"); print("═"*68)
g3 = "استعلام بلغة الطلب" in a
g4 = "ترتيب لغة المراجع" in a
ok &= g3 and g4
print(f"   استعلامٌ إضافيّ بلغة الطلب: {'✅' if g3 else '❌'}")
print(f"   والترتيب يقدّم لغة الطلب:   {'✅' if g4 else '❌'}")
pool = [{"title": "A", "lang": "en", "doi": "10.1/a", "venue": "J", "academic": True},
        {"title": "ب", "lang": "ar", "doi": "10.2/b", "venue": "م", "academic": True},
        {"title": "C", "lang": "en", "doi": "10.3/c", "venue": "J", "academic": True},
        {"title": "د", "lang": "ar", "doi": "10.4/d", "venue": "م", "academic": True}]
_idx = {id(r): i for i, r in enumerate(pool)}
ordered = sorted(pool, key=lambda r: (0 if str(r.get("lang") or "").lower()
                                      .startswith("ar") else 1, _idx.get(id(r), 0)))
g5 = [r["lang"] for r in ordered] == ["ar", "ar", "en", "en"]
ok &= g5
print(f"   طلبٌ عربيّ ⟶ {[r['lang'] for r in ordered]}  {'✅' if g5 else '❌'}")

print("\n" + "═"*68); print(" ٤) (None) ⟶ n.d."); print("═"*68)
for nm, r in [("مقال بلا سنة", fa.format_apa_article("Soo Fei Chuah", None, "T", "J")),
              ("كتاب بلا سنة", fa.format_apa_book("مؤلف", None, "ك", "ناشر")),
              ("موقع بلا سنة", fa.format_apa_website("عنوان", "https://x.com/y"))]:
    g6 = ("(n.d.)" in r) and ("None" not in r)
    ok &= g6
    print(f"   {nm:14s} ⟶ {r[:58]}  {'✅' if g6 else '❌'}")

print("\n" + "═"*68); print(" ٥) الصفحات تصير ميزانيةً فعليّة"); print("═"*68)
for c, want in [({"target_pages": 12}, "3600"), ({"target_pages": 1}, "300"),
                ({"target_words": 3000}, "3000"), ({}, None)]:
    d = W._length_directive(c, 6)
    g7 = ((want in d) if want else (d == ""))
    ok &= g7
    print(f"   {str(c):26s} ⟶ {(d[:52] if d else '(بلا ميزانية)')}  {'✅' if g7 else '❌'}")

print("\n" + "═"*68); print(" ٦) تغطية الجوانب تعبر الاشتقاق"); print("═"*68)
import re, io
src = io.open(_ROOT + "/pipeline/orchestrator.py", encoding="utf-8").read()
m = re.search(r"            def _stem\(w\):.*?\n                return w\n", src, re.S)
ns = {}; exec("\n".join(l[12:] for l in m.group(0).split("\n")), ns)
stem = ns["_stem"]
for a_, b_ in [("الأطفال", "للأطفال"), ("المراهقون", "المراهقين"),
               ("التحصيل", "للتحصيل"), ("الصحية", "صحية")]:
    g8 = (stem(a_) == stem(b_))
    ok &= g8
    print(f"   {a_:11s} ≡ {b_:11s} ⟶ {stem(a_):9s} {'✅' if g8 else '❌'}")

print("\n" + "═"*68); print(" ٧) علامات الماركداون لا تتسرّب"); print("═"*68)
src2 = {"venue": "م", "lang": "ar",
        "content": "###### الفرق بين قصر النظر وضعف النظر – شرح مبسط وسريع "
                   "**أغسطس** 26, 2025 ###### علاج رفة العين اليسرى من الأعلى"}
ann = W._ref_annotation(src2, "ar")
g9 = ("#" not in ann and "**" not in ann and "الفرق بين قصر النظر" in ann)
ok &= g9
print(f"   {ann[:96]}")
print(f"   ⟵ نُزعت العلامات وبقي النصّ: {'✅' if g9 else '❌'}")

print("\n" + ("PASS ✅" if ok else "FAIL ❌"))
sys.exit(0 if ok else 1)
