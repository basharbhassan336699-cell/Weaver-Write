# -*- coding: utf-8 -*-
"""إعادة تشغيل ردود القواعد الحقيقية — بأوراقك أنت — عبر الكود الحقيقي.
لا شبكة (محجوبة هنا)، لكن كل دالّة تعمل كما تعمل على جهازك."""
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

# ── ردٌّ حقيقيّ الشكل من OpenAlex، بأوراقٍ من لقطاتك حرفياً ───────────────
def _inv(txt):                       # abstract_inverted_index كما تُعيده OpenAlex
    d = {}
    for i, w in enumerate(txt.split()):
        d.setdefault(w, []).append(i)
    return d

OA = {"results": [
 {"title": "Protecting children from mobile phone radiation", "publication_year": 2011,
  "doi": "https://doi.org/10.1136/bmj.d4554", "language": "en",
  "primary_location": {"source": {"display_name": "BMJ"}},
  "authorships": [{"author": {"display_name": "K. O'Neill"}}],
  "abstract_inverted_index": _inv("Concerns about the health effects of mobile phone "
    "radiation on children have grown steadily. This paper reviews the precautionary "
    "approach adopted by several governments and the evidence base behind it, and "
    "argues that further study of paediatric exposure is needed.")},
 {"title": "Effect of 902 MHz mobile phone transmission on cognitive function in children",
  "publication_year": 2005, "doi": "https://doi.org/10.1002/bem.20128", "language": "en",
  "primary_location": {"source": {"display_name": "Bioelectromagnetics"}},
  "authorships": [{"author": {"display_name": "A. Preece"}},
                  {"author": {"display_name": "Stephanie Goodfellow"}}],
  "abstract_inverted_index": _inv("A double blind study of cognitive function in "
    "children exposed to 902 MHz mobile phone transmission found no significant "
    "effect on reaction time or word recall in the exposed group.")},
 # ── الورقة المكرّرة: بندا ٨ و٩ في ملفك، بـDOI مختلفَين ──
 {"title": "Solar energy: A viable pathway towards ecologically sustainable development",
  "publication_year": 1994, "doi": "https://doi.org/10.1016/0038-092x(94)90033-7",
  "language": "en", "primary_location": {"source": {"display_name": "Solar Energy"}},
  "authorships": [{"author": {"display_name": "W.W.S. Charters"}}],
  "abstract_inverted_index": _inv("")},
 {"title": "Solar Energy:  A Viable Pathway Towards Ecologically Sustainable Development",
  "publication_year": 1994, "doi": "https://doi.org/10.1016/0038-092x(94)90113-g",
  "language": "en", "primary_location": {"source": {"display_name": "Solar Energy"}},
  "authorships": [{"author": {"display_name": "W.W.S. Charters"}}],
  "abstract_inverted_index": _inv("")},
 # ── وأوراقٌ عربية لا تخصّ الموضوع، كالتي أغرقت ملفك الأول ──
 {"title": "أثر الطلاق على نفسية الأطفال", "publication_year": 2011,
  "doi": "https://doi.org/10.35217/0048-028-110-006", "language": "ar",
  "primary_location": {"source": {"display_name": "مجلة العلوم الاجتماعية"}},
  "authorships": [{"author": {"display_name": "فريدة لوشاحي"}}],
  "abstract_inverted_index": _inv("دراسة ميدانية عن الآثار النفسية للطلاق على الأطفال.")},
 {"title": "أثر استقلالية مراجع الحسابات على الأداء المالي", "publication_year": 2022,
  "doi": "https://doi.org/10.53796/hnsj3223", "language": "ar",
  "primary_location": {"source": {"display_name": "مجلة العلوم الإنسانية"}},
  "authorships": [{"author": {"display_name": "ديوان المراجعة القومي"}}],
  "abstract_inverted_index": _inv("")},
]}

_calls = []
def fake_http_get(url, headers, timeout=15):
    _calls.append(url)
    return json.dumps(OA) if "openalex" in url else None
W._http_get = staticmethod(fake_http_get)

print("═" * 62)
print("  ١ — المحرّك: هل يلتقط الجهة واللغة؟")
print("═" * 62)
res = W._openalex_search("mobile phone radiation effects on children", "en", 8)
for r in res[:2]:
    print(f"  • {r['title'][:52]}")
    print(f"    الجهة={r['venue']!r}  اللغة={r['lang']!r}  DOI={r['doi'][:28]}")
ok = all(r.get("venue") and r.get("lang") for r in res[:2])
print(f"  ⟵ {'✅ التُقطا' if ok else '❌ ما زالا يُرميان'}")

print("\n" + "═" * 62)
print("  ٢ — الدمج: هل تمرّ الورقة المكرّرة مرّتين؟")
print("═" * 62)
merged = W._scholarly_search("mobile phone radiation effects on children", "en", 9, wide=True)
titles = [m["title"] for m in merged]
n_ch = sum(1 for t in titles if "viable pathway" in t.lower())
print(f"  دخل: {len(OA['results'])} سجلّ (فيها Charters مرّتين بـDOI مختلفَين)")
print(f"  خرج: {len(merged)} مرجعاً · Charters ظهر {n_ch} مرّة "
      f"{'✅' if n_ch == 1 else '❌'}")
ok &= (n_ch == 1)
print("  الوسم:", {m["title"][:22]: m.get("_prefilter") for m in merged[:3]})

print("\n" + "═" * 62)
print("  ٣ — خطّ الأنابيب كاملاً: _academic_search بطلبك الحقيقي")
print("═" * 62)

class FakeMem:
    def __init__(self): self.status, self.refs = [], []
    def set_status(self, n, t): self.status.append((n, t))
    def add_reference(self, t, source_key=None): self.refs.append(t)

class FakeTask:
    def __init__(self, desc, card): self.description, self.task_card = desc, card

def model(prompt, system=None, temperature=0.7, max_tokens=None, timeout=None):
    if "refs_lang" in prompt:            # صياغة الاستعلام
        return json.dumps({"query": "mobile phone radiation effects on children",
                           "refs_lang": "ar",
                           "note": "الأدب المحكَّم في هذا الموضوع إنجليزيٌّ غالباً"},
                          ensure_ascii=False)
    if '"keep"' in prompt:               # الفرز: الأوّلان فقط يخصّان الموضوع
        import re
        n = len(re.findall(r"^\s*\d+\.", prompt, re.M))
        return json.dumps({"keep": [1, 2], "drop": list(range(3, n + 1))})
    return ""

o = W.__new__(W); o.llm_fn = model; o.system_main = "s"
REQ = "أريدك توجد 9 مراجع عربية أكاديمي لموضوع البحث: أثر إشعاعات الهاتف على الأطفال"
card = {"topic": "أثر إشعاعات الهاتف على الأطفال", "language": "ar",
        "reference_count": 9}
task, mem = FakeTask(REQ, card), FakeMem()
asyncio.run(o._academic_search(task, mem))

print("  المراجع المحفوظة:")
for i, s in enumerate(card.get("sources", []), 1):
    print(f"   {i}. {s['title'][:56]}")
print("\n  سجلّ القرارات:")
for k, v in (card.get("decisions") or {}).items():
    print(f"   · {k}: {v['value']}  ← {v['by']}")
print("\n  لم يُنفَّذ، والسبب:")
for st in (card.get("skipped_steps") or []):
    _s = st if isinstance(st, str) else f"{st.get('step')} — {st.get('reason')}"
    print(f"   • {_s}")
print("\n  الحالة:", mem.status[-1][1] if mem.status else "—")

kept_ok = len(card.get("sources", [])) == 2
lang_note = any("طُلبت المراجع" in str(st) for st in (card.get("skipped_steps") or []))
ok &= kept_ok and lang_note
print(f"\n  ⟵ أُبقي مرجعان يخصّان الموضوع: {'✅' if kept_ok else '❌'}")
print(f"  ⟵ وقيلت الحقيقة عن اللغة بالأرقام: {'✅' if lang_note else '❌'}")

print("\n" + "═" * 62)
print("  ٤ — كيف تُطبع القائمة في ملفك")
print("═" * 62)
txt = "\n".join(f"{i}. {s['title']}  {s.get('url','')}"
                for i, s in enumerate(card["sources"], 1))
print(W._annotate_bibliography(txt, card["sources"], "ar"))

print("\n" + ("PASS ✅" if ok else "FAIL ❌"))
sys.exit(0 if ok else 1)
