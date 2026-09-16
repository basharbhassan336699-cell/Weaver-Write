# -*- coding: utf-8 -*-
"""الثغرات الأربع — بأرقام ملفك الحقيقي."""
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
import core.llm as L
ok = True
def mk(fn):
    o = W.__new__(W); o.llm_fn = fn; o.system_main = "نظامٌ طويل " * 40; return o

print("═" * 68)
print(" ١) النسبة الكاذبة: المنسّق يُرتّب، فهل تنزاح الأوصاف؟")
print("═" * 68)
SRC = [  # بترتيب الجمع (غير مرتّب)
 {"title": "الإعجاز العلمي في القرآن الكريم", "doi": "10.53796/hnsj4411",
  "venue": "Humanitarian and Natural Sciences Journal", "lang": "ar"},
 {"title": "الإعجاز التشريعي في القرآن الكريم", "doi": "10.69844/40hy4q92",
  "venue": "الباحث الجامعي", "lang": "ar"},
 {"title": "الإعجاز التشريعي في الميراث", "doi": "10.21608/zhr.2021.1",
  "venue": "مجلة الزهراء", "lang": "ar"},
 {"title": "الإعجاز العلمي واللغوي في سورة النور", "doi": "10.5555/noor2014",
  "venue": "DOAJ", "lang": "ar"},
]
# ما يُعيده المنسّق فعلاً: مرتَّبٌ أبجدياً — أي بترتيبٍ مغاير للمدخلات
RENDERED = "\n".join([
 "1. خالد بليل (2021). الإعجاز التشريعي في الميراث. مجلة الزهراء. https://doi.org/10.21608/zhr.2021.1",
 "2. مرتضى الشاوي (2014). الإعجاز العلمي واللغوي في سورة النور. DOAJ. https://doi.org/10.5555/noor2014",
 "3. الإعجاز العلمي في القرآن الكريم (2023). https://doi.org/10.53796/hnsj4411",
 "4. حكمت الحريري (2024). الإعجاز التشريعي في القرآن الكريم. الباحث الجامعي. https://doi.org/10.69844/40hy4q92",
])
out = W._annotate_bibliography(RENDERED, SRC, "ar")
print(out)
import re
bad = []
for ln in out.split("\n"):
    if ln.strip().startswith("الجهة:"):
        continue
lines = out.split("\n")
for i, ln in enumerate(lines):
    if not re.match(r"^\s*\d+[.)]", ln): continue
    ann = lines[i+1] if i+1 < len(lines) and lines[i+1].strip().startswith("الجهة:") else ""
    for s_ in SRC:
        if s_["doi"] in ln:
            if ann and s_["venue"] not in ann:
                bad.append((ln[:40], ann[:40]))
good = not bad
ok &= good
print(f"\n  ⟵ كل وصفٍ تحت صاحبه: {'✅' if good else '❌ ' + str(bad)}")

print("\n" + "═" * 68)
print(" ٢) التفكير لا يُطبع مكان الجواب")
print("═" * 68)
print("  حمولة التعطيل:")
for nm, b, m in [("أوبن روتر", "https://openrouter.ai/api/v1", "deepseek/deepseek-v4.1-flash"),
                 ("ديب سيك مباشر", "https://api.deepseek.com", "deepseek-v4-flash"),
                 ("أنثروبيك", "https://api.anthropic.com/v1", "claude-opus-5")]:
    print(f"   {nm:14s} ⟶ {L.reasoning_payload('', b, m)}")
ok &= ("reasoning" in L.reasoning_payload("", "https://openrouter.ai/api/v1", "x-deepseek"))
ok &= (L.reasoning_payload("", "https://api.anthropic.com/v1", "claude-opus-5") == {})
src = inspect.getsource(L)
g = ("_REASONING_MARK" in src and "return last or _thought" in src)
ok &= g
print(f"  التفكير يُؤجَّل حتى استنفاد المحاولات: {'✅' if g else '❌'}")

print("\n" + "═" * 68)
print(" ٣) الفارز لا يستسلم: تنازلٌ عن الشكل لا عن القرار")
print("═" * 68)
TITLES = ["الإعجاز العلمي في القرآن الكريم", "الإعجاز التشريعي في الميراث",
          "العدد والحساب وأثره في أحكام الزكاة", "الإعجاز العلمي بين القبول والرفض",
          "الحقوق المالية للمرأة المطلقة"]
items = [{"title": t} for t in TITLES]
TRUNC = "We need answer JSON only. Need decide which titles actually pertain to research )"
calls = []
def flaky(prompt, system=None, temperature=0.7, max_tokens=None, timeout=None):
    calls.append(max_tokens)
    if "مفصولةً بفواصل" in prompt or "separated by commas" in prompt:
        return "دعني أفكّر… العناوين المطابقة هي: 1,4"
    return TRUNC                      # JSON مقطوع في كل محاولة
o = mk(flaky)
kept, dropped = o._judge_relevance(items, "الإعجاز العلمي والأخلاقي", "…", "ar")
names = [r["title"] for r in (kept or [])]
good = (names == [TITLES[0], TITLES[3]] and len(dropped) == 3)
ok &= good
print(f"  الميزانيات المجرَّبة: {calls}")
print(f"  أُبقي: {names}")
print(f"  استُبعد: {[r['title'][:34] for r in (dropped or [])]}")
print(f"  ⟵ الحكم وقع رغم انقطاع الـJSON: {'✅' if good else '❌'}")
for nm, rep in [("كل الأرقام (ليس حكماً)", "1,2,3,4,5"), ("لا رقم", "لا أدري"),
                ("رقمٌ خارج المدى", "99")]:
    o2 = mk(lambda p, **k: rep if ("بفواصل" in p or "commas" in p) else TRUNC)
    r = o2._judge_relevance(items, "t", "r", "ar")
    good2 = (r == (None, None))
    ok &= good2
    print(f"  {nm:24s} ⟶ يُرفض ويُعلَن {'✅' if good2 else '❌'}")

print("\n" + "═" * 68)
print(" ٤) جانبٌ من الموضوع رجع فارغاً")
print("═" * 68)
class M:
    def __init__(s): s.status=[]
    def set_status(s,n,t): s.status.append((n,t))
    def add_reference(s,t,source_key=None): pass
class T:
    def __init__(s,d,c): s.description, s.task_card = d, c
OA = [{"title": t, "content": "", "lang": "ar", "venue": "مجلة", "url": f"u{i}",
       "doi": f"10.1/{i}", "authors": [], "year": "2023", "source": "openalex"}
      for i, t in enumerate(["الإعجاز العلمي في القرآن", "الإعجاز التشريعي في الميراث",
                             "الإعجاز العلمي بين القبول والرفض"])]
def model(prompt, system=None, temperature=0.7, max_tokens=None, timeout=None):
    if "facets" in prompt:
        return json.dumps({"query": "الإعجاز العلمي والأخلاقي",
                           "refs_lang": "ar",
                           "facets": ["الإعجاز العلمي", "الإعجاز الأخلاقي"],
                           "note": ""}, ensure_ascii=False)
    if '"keep"' in prompt: return json.dumps({"keep": [1, 2, 3], "drop": []})
    return ""
o = mk(model)
W._scholarly_search = classmethod(lambda cls, q, l, lim, timeout=14, wide=False: list(OA))
card = {"topic": "الإعجاز العلمي والأخلاقي في القرآن الكريم", "language": "ar",
        "reference_count": 9}
task, mem = T("أريد 9 مراجع عربية", card), M()
asyncio.run(o._academic_search(task, mem))
notes = [f"{x.get('step')} — {x.get('reason')}" if isinstance(x, dict) else str(x)
         for x in (card.get("skipped_steps") or [])]
for n in notes: print("  •", n)
good = any("الإعجاز الأخلاقي" in n and "لم تُعِد" in n for n in notes)
ok &= good
print(f"  ⟵ الشقّ الغائب يُسمّى صراحةً: {'✅' if good else '❌'}")

print("\n" + ("PASS ✅" if ok else "FAIL ❌"))
sys.exit(0 if ok else 1)
