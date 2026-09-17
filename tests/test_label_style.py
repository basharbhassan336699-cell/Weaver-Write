# -*- coding: utf-8 -*-
"""قالبُ الترقيم الذي يكتبه المستخدم بيده — يُقرأ ويُطبَّق.

طلبَ المستخدم صراحةً، وضرب المثال في نصّ طلبه:
    المبحث الأول: ......  المطلب الأول: ......  1.1 ...  1.2 ...  1.3 ...
وخرج المستند: «المبحث 1 / المطلب 1.1 / تقسيماتٌ بلا رقم» — الترقيمُ مقلوب.
السبب: _counted_structure تسكّ كلّ لافتةٍ من ثلاث f-strings ثابتة لا يصلها
نصُّ الطلب أبداً."""
import sys, os, inspect
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


REQ = ("أريد بحثاً بالكامل عن الزواج في الإسلام. الهيكلة مكونة من ثلاثة "
       "مباحث، كل مبحث فيه ثلاثة مطالب، وكل مطلب تقسيمات حسب ما يلزم، ويكون "
       "الترتيب بهذا الشكل: المبحث الأول: ...... المطلب الأول: ...... "
       "1.1 ....... 1.2 ......... 1.3 ......... يعني هذا مثال الطريقة الذي "
       "أريدها أضف صفحة غلاف وفهرساً. لا يقل عن 10 صفحات ولا يزيد عن 12 "
       "صفحة، بالعربية، مع 9 مراجع بأسلوب APA.")

print("═" * 70)
print(" ١) المثالُ في نصّ الطلب يُقرأ")
print("═" * 70)
st = W._label_style(REQ, "ar")
chk("ألفاظٌ للمبحث", (st.get("ordinal") or {}).get("المبحث") is True, str(st))
chk("ألفاظٌ للمطلب", (st.get("ordinal") or {}).get("المطلب") is True)
chk("ترقيمٌ نقطيٌّ عارٍ للتقسيمات", st.get("dotted_bare") is True)

print("\n" + "═" * 70)
print(" ٢) والبنية تُسَكّ على مثاله")
print("═" * 70)
plan = [dict(s) for s in W._counted_structure("ar", 3, 3, n_sub=0)]
out = []
for s in plan:
    t = s["title"]
    if t.startswith("المبحث"):
        s = {**s, "title": t + ": أركان عقد الزواج"}
    if t.startswith("المطلب"):
        out.append({**s, "title": t + ": اشتراط الولي"})
        for nm in ("تعريف الولي", "شروط الولي", "أثر الاشتراط"):
            out.append({"key": "body", "title": nm, "level": 3})
        continue
    out.append(s)
res = W._apply_label_style(out, st, "ar")
titles = [s["title"] for s in res]
chk("المبحث الأول", any(t.startswith("المبحث الأول:") for t in titles))
chk("المبحث الثاني", any(t.startswith("المبحث الثاني:") for t in titles))
chk("المطلب الأول", any(t.startswith("المطلب الأول:") for t in titles))
chk("المطلب الثالث", any(t.startswith("المطلب الثالث:") for t in titles))
chk("1.1 / 1.2 / 1.3 للتقسيمات",
    all(f"1.{n} تعريف الولي" in " ".join(titles) or True for n in (1,))
    and "1.1 تعريف الولي" in titles and "1.2 شروط الولي" in titles
    and "1.3 أثر الاشتراط" in titles)
chk("ولا رقمَ على المقدمة والخاتمة والمراجع",
    "المقدمة" in titles and "الخاتمة" in titles and "قائمة المراجع" in titles)
chk("والموضوعُ لم يُمَسّ", all(": اشتراط الولي" in t
                                for t in titles if t.startswith("المطلب")))

print("\n" + "═" * 70)
print(" ٣) وبلا مثالٍ — لا يتغيّر شيء (توافقٌ كامل)")
print("═" * 70)
for lbl, req in (
        ("طلبٌ بلا مثال", "اكتب بحثاً عن الطاقة في ثلاثة مباحث، كل مبحث مطلبان"),
        ("مثالٌ رقميّ", "اكتب بحثاً، والترتيب: المبحث 1: ... المطلب 1.1: ..."),
        ("وحداتٌ أخرى", "بحثٌ في ثلاثة أبواب: الباب الأول: ... الفصل الأول: ...")):
    _p = [dict(s) for s in W._counted_structure("ar", 2, 2, n_sub=0)]
    _s = W._label_style(req, "ar")
    _o = W._apply_label_style(_p, _s, "ar")
    chk(f"{lbl} ⟶ البنية كما هي",
        [a["title"] for a in _p] == [b["title"] for b in _o])

print("\n" + "═" * 70)
print(" ٤) ووحدةُ المستخدم نفسها تُحترم")
print("═" * 70)
_p = [dict(s) for s in W._counted_structure("ar", 2, 2,
                                            units=["الباب", "الفصل", "المبحث"])]
_s = W._label_style("بحثٌ ترتيبه: الباب الأول: ... الفصل الأول: ...", "ar")
_o = W._apply_label_style(_p, _s, "ar")
_t = [s["title"] for s in _o]
chk("الباب الأول", "الباب الأول" in _t, " | ".join(_t[:5]))
chk("الفصل الأول", "الفصل الأول" in _t)
chk("الفصل الثاني", "الفصل الثاني" in _t)

print("\n" + "═" * 70)
print(" ٥) والمسار يستدعيه فعلاً")
print("═" * 70)
_src = inspect.getsource(W._layer_6)
chk("_label_style مُستدعىً في الطبقة ٦", "_label_style(" in _src)
chk("ويُطبَّق بعد التقسيمات", "_apply_label_style(" in _src)
chk("ويُسجَّل في سجلّ القرارات", "نمط الترقيم" in _src)

print("\n" + "═" * 70)
print(" النتيجة: " + ("PASS ✅" if ok else "FAIL ❌"))
print("═" * 70)
sys.exit(0 if ok else 1)
