# -*- coding: utf-8 -*-
"""لغة المراجع: عربي · إنجليزي · الاثنتان · وصمت النموذج."""
import sys, os, json, asyncio
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
POOL = ([{"title": f"دراسة عربية {i}", "lang": "ar", "doi": f"10.1/a{i}",
          "url": f"u{i}", "venue": "مجلة", "academic": True, "year": "2023",
          "authors": ["مؤلف"], "content": ""} for i in range(1, 4)]
      + [{"title": f"English study {i}", "lang": "en", "doi": f"10.2/e{i}",
          "url": f"v{i}", "venue": "Journal", "academic": True, "year": "2022",
          "authors": ["Author"], "content": ""} for i in range(1, 6)])
calls = []
W._scholarly_search = classmethod(
    lambda c, q, l, lim, timeout=14, wide=False:
    (calls.append(q) or [dict(x) for x in POOL]))
W._crossref_record = classmethod(lambda c, d, timeout=15: None)
class M:
    def set_status(s, n, t): pass
    def add_reference(s, t, source_key=None): pass
class T:
    def __init__(s, d, c): s.description, s.task_card = d, c

def run(req, doclang, refs_lang):
    calls.clear()
    def model(p, **k):
        if "facets" in p:
            return json.dumps({"query": "composed query", "refs_lang": refs_lang,
                               "facets": [], "note": ""}, ensure_ascii=False)
        if '"keep"' in p:
            return json.dumps({"keep": list(range(1, 9)), "drop": []})
        return ""
    o = W.__new__(W); o.llm_fn = model; o.system_main = "s"
    async def nf(u): return None
    o._extract_full = nf
    card = {"topic": req, "language": doclang, "reference_count": 6}
    asyncio.run(o._academic_search(T(req, card), M()))
    return card, [s.get("lang") for s in (card.get("sources") or [])], list(calls)

print("═"*68)
print(" ١) طلبٌ عربيّ ⟶ العربية أولاً")
print("═"*68)
c, langs, q = run("أثر النوم على التركيز", "ar", "ar")
g = (langs[:3] == ["ar"]*3 and len(q) == 2)
ok &= g
print(f"   استعلامات: {q}")
print(f"   اللغات   : {langs}   {'✅' if g else '❌'}")

print("\n" + "═"*68)
print(" ٢) طلبٌ إنجليزيّ ⟶ الإنجليزية أولاً")
print("═"*68)
c, langs, q = run("Effect of sleep on focus", "en", "en")
g = (langs[:3] == ["en"]*3)
ok &= g
print(f"   اللغات   : {langs}   {'✅' if g else '❌'}")

print("\n" + "═"*68)
print(" ٣) «الاثنتان» ⟶ تناوبٌ مضمون، لا إهمال")
print("═"*68)
for tag in ("any", "both", "mixed", "ar+en"):
    c, langs, q = run("أثر النوم — مراجع عربية وإنجليزية", "ar", tag)
    g = (langs[:4] == ["ar", "en", "ar", "en"] and len(q) == 2)
    ok &= g
    d = (c.get("decisions") or {}).get("ترتيب لغة المراجع", {}).get("value", "—")
    print(f"   refs_lang={tag:6s} ⟶ {langs}  · {d}  {'✅' if g else '❌'}")
print("   ⟵ كانت تُعطَّل الآليتان معاً فتصير «لا تفضيل»")

print("\n" + "═"*68)
print(" ٤) صمت النموذج ⟶ لغة المستند تحكم (لا نصف آلية)")
print("═"*68)
for rl in (None, "", "null"):
    c, langs, q = run("أثر النوم على التركيز", "ar", rl)
    d = (c.get("decisions") or {}).get("ترتيب لغة المراجع", {}).get("value", "—")
    g = (langs[:3] == ["ar"]*3 and len(q) == 2 and d != "—")
    ok &= g
    print(f"   refs_lang={str(rl):5s} ⟶ {langs} · {d}  {'✅' if g else '❌'}")

print("\n" + "═"*68)
print(" ٥) لغةٌ واحدة لا تُناوَب، والمجهول لا يُحذف")
print("═"*68)
wr = W._wr()
pool = ([{"t": f"ar{i}", "lang": "ar"} for i in range(1, 4)]
        + [{"t": f"en{i}", "lang": "en"} for i in range(1, 6)]
        + [{"t": "??", "lang": ""}])
one = [x["t"] for x in wr.interleave_by_lang(pool, ["ar"])]
both = [x["t"] for x in wr.interleave_by_lang(pool, ["ar", "en"])]
g = (one == [x["t"] for x in pool] and both[:4] == ["ar1", "en1", "ar2", "en2"]
     and both[-1] == "??" and len(both) == len(pool))
ok &= g
print(f"   لغةٌ واحدة ⟶ بلا تغيير: {'✅' if one == [x['t'] for x in pool] else '❌'}")
print(f"   الاثنتان  ⟶ {both}")
print(f"   والمجهول في آخرها ولم يُحذف: {'✅' if both[-1] == '??' else '❌'}")

print("\n" + ("PASS ✅" if ok else "FAIL ❌"))
sys.exit(0 if ok else 1)
