# -*- coding: utf-8 -*-
"""قائمة التوثيق: محكَّمة، مقروءة، ومطابقة لما استُشهد به في النصّ."""
import sys, os, importlib.util as iu, inspect
sys.path.insert(0, "/home/user/Weaver-Write")
for k in list(os.environ):
    if k.startswith("WEAVER_"): os.environ.pop(k)
from pipeline.orchestrator import WeaverOrchestrator as W
sp = iu.spec_from_file_location("fa", "/home/user/Weaver-Write/capabilities/"
                                "skills/apa_formatter/scripts/format_apa.py")
fa = iu.module_from_spec(sp); sp.loader.exec_module(fa)
ok = True

print("═"*70); print(" ١) رابطٌ خام ⟶ نصٌّ عربيّ مقروء"); print("═"*70)
RAW = ("https://altibbi.com/%D9%85%D9%82%D8%A7%D9%84%D8%A7%D8%AA-"
       "%D8%B7%D8%A8%D9%8A%D8%A9/%D8%B5%D8%AD%D8%A9")
out = fa.format_apa_website("أعراض قلة النوم | الطبي", RAW)
g = ("%D9%" not in out and "مقالات" in out)
ok &= g
print(f"   {out[:96]}")
print(f"   ⟵ فُكّ الترميز: {'✅' if g else '❌'}")

print("\n" + "═"*70); print(" ٢) لا مدخلَ عارياً: اسم الموقع والتاريخ"); print("═"*70)
cases = [("بلا سنة ولا موقع", fa.format_apa_website("عنوان", "https://www.aawsat.com/x")),
         ("بسنة",            fa.format_apa_website("عنوان", "https://misbar.com/y", 2025)),
         ("بمؤلّف",           fa.format_apa_website("عنوان", "https://x.org/z", 2020, None, "فلان"))]
for nm, r in cases:
    g2 = ("*" in r) and (("(n.d.)" in r) or ("(2" in r))
    ok &= g2
    print(f"   {nm:18s} ⟶ {r[:70]}  {'✅' if g2 else '❌'}")
print("   ⟵ لا «عنوان. رابط» مجرّدة بعد اليوم")

print("\n" + "═"*70); print(" ٣) القائمة للمحكَّم وحده"); print("═"*70)
ACAD = [{"title": "Sleep deprivation and vigilant attention", "doi": "10.1/a",
         "url": "https://doi.org/10.1/a", "venue": "Sleep", "academic": True,
         "authors": ["Hans P.A. Van Dongen"], "year": "2003"},
        {"title": "Impact on cognitive performance", "doi": "10.2/b",
         "url": "https://doi.org/10.2/b", "venue": "NDT", "academic": True,
         "authors": ["Paula Alhola"], "year": "2007"}]
WEB = [{"title": "أعراض قلة النوم | الطبي", "url": "https://altibbi.com/y"},
       {"title": "هل نقص النوم يؤثر؟", "url": "https://misbar.com/z"},
       {"title": "٥ أضرار", "url": "https://elconsolto.com/w"}]
card = {}
chosen, dropped = W._bib_sources(ACAD + WEB, card, "ar")
g3 = (len(chosen) == 2 and len(dropped) == 3
      and all(x.get("academic") for x in chosen))
ok &= g3
print(f"   دخل ٥ (٢ محكَّم + ٣ عامّ) ⟶ القائمة {len(chosen)} · مُستبعَد {len(dropped)}"
      f"  {'✅' if g3 else '❌'}")
print(f"   المُستبعَد يبقى في السياق، لا يُحذف: {[x['title'][:18] for x in dropped]}")
card2 = {}
ch2, dr2 = W._bib_sources(list(WEB), card2, "ar")
g4 = (len(ch2) == 3 and not dr2 and card2.get("refs_no_academic"))
ok &= g4
print(f"   بلا محكَّمٍ إطلاقاً ⟶ تُستعمل العامّة ويُعلَن ذلك: "
      f"{'✅' if g4 else '❌'} (refs_no_academic={card2.get('refs_no_academic')})")

print("\n" + "═"*70); print(" ٤) كل استشهادٍ في النصّ له مدخلٌ في القائمة"); print("═"*70)
DRAFT = ("أظهرت الدراسات (Hans P.A. Van Dongen وآخرون، 2003) أن الحرمان يؤثر، "
         "كما بيّن (Paula Alhola، 2007). وأضاف (William D. S. Killgore، 2010) "
         "بعداً آخر، ووافقه (Kylie C. Kayser وآخرون، 2022).")
miss = W._citation_coverage(DRAFT, ACAD)
g5 = (len(miss) == 2 and any("Killgore" in m for m in miss)
      and any("Kayser" in m for m in miss))
ok &= g5
print(f"   ٤ استشهادات · ٢ في القائمة ⟶ ناقصٌ {len(miss)}: {miss}  {'✅' if g5 else '❌'}")
full = W._citation_coverage(DRAFT, ACAD + [
    {"authors": ["William D. S. Killgore"], "title": "t", "year": "2010"},
    {"authors": ["Kylie C. Kayser"], "title": "t2", "year": "2022"}])
ok &= (full == [])
print(f"   والقائمة كاملة ⟶ {full}  {'✅' if full == [] else '❌'}")
ok &= (W._citation_coverage("نصٌّ بلا استشهادات", ACAD) == [])
print(f"   نصٌّ بلا استشهادات ⟶ لا إنذار ✅")

print("\n" + "═"*70); print(" ٥) الوصل في طبقة ٨"); print("═"*70)
a = inspect.getsource(W)
for nm, pat in [("القائمة للمحكَّم", "_bib_sources(sources, card, lang)"),
                ("إعلان الاستبعاد", "استُبعد {len(_drop)} مصدراً عامّاً"),
                ("إعلان غياب المحكَّم", "refs_no_academic"),
                ("تطابق الاستشهادات", "استشهاداتٌ في النصّ لا تقابلها")]:
    g6 = pat in a
    ok &= g6
    print(f"   {nm:22s} {'✅' if g6 else '❌'}")

print("\n" + ("PASS ✅" if ok else "FAIL ❌"))
sys.exit(0 if ok else 1)
