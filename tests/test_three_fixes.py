# -*- coding: utf-8 -*-
"""الثلاثة الباقية من بحث «الزواج في الإسلام» — بأرقام ذلك التشغيل نفسه."""
import sys, os, json, inspect
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


print("═" * 70)
print(" ١) لغة المراجع تُفحص على المطبوع لا على المجلوب")
print("═" * 70)
# التشغيل: «9 مراجع عربية» وخرج أربعةٌ منها لاتينيّ الطباعة، والسجلّ يقول ar.
BODY = """1. أحمد عباس محمد (2025). الإعجاز العلمي في القرآن الكريم. مجلة كلية الإمام.
2. Ismail Firano (2024). MAQASID AL-ZUWAJ AL-SYARIYYAH. Jurnal Al-Dustur.
3. محمد نايف اللحام (2022). الزواج بنية الطلاق: دراسة تأصيلية. https://doi.org/10.1/x
4. Manswab Mahsen Abdulrahman (2018). International Journal of Fiqh Studies.
5. هبة الشرقاوي (1999). المنهج القضائي لمحاكم الأسرة. مجلة بنها."""
ar, en, total = W._printed_refs_language(BODY)
chk(f"عدّ المطبوع: عربية {ar}، إنجليزية {en}، من {total}",
    (ar, en, total) == (3, 2, 5))
chk("ولا تُحسب الروابط لاتينيةً", W._printed_refs_language(
    "1. عنوانٌ عربيّ. https://doi.org/10.1/abc")[0] == 1)
chk("ولا سطرٌ غير مرقّمٍ يُعدّ", W._printed_refs_language("مقدمة القائمة")[2] == 0)

card = {"refs_lang_plan": ["ar"]}
o = W.__new__(W)
o._note_refs_language(card, BODY, "ar")
_d = (card.get("decisions") or {}).get("لغة المراجع المطبوعة") or {}
chk("ويُسجَّل بالعدد", "3 من 5" in str(_d.get("value")), str(_d.get("value")))
chk("ويُقال صراحةً إن الطلب لم يُستوفَ",
    any("لغة المراجع" == n.get("step") for n in (card.get("skipped_steps") or [])))
card2 = {"refs_lang_plan": ["ar"]}
o._note_refs_language(card2, "1. عنوانٌ عربيّ كامل.\n2. آخرُ عربيّ.", "ar")
chk("وإن استُوفي — لا شكوى", not (card2.get("skipped_steps") or []))

# واللغة المطلوبة تدخل في الترجيح عند القصّ
many = [{"title": f"دراسة عربية {i}", "authors": ["فلان"], "venue": "مجلة",
         "doi": f"10.1/a{i}"} for i in range(6)]
many += [{"title": f"Latin study {i}", "authors": ["Smith"],
          "venue": "Journal", "doi": f"10.1/b{i}"} for i in range(10)]
c3 = {"requirements": [{"kind": "source", "target": 6, "must": True}],
      "refs_lang_plan": ["ar"]}
kept, over = W._cap_to_requested(many, c3, "", "ar")
_ar = sum(1 for x in kept if "دراسة" in x["title"])
chk(f"١٦ مرجعاً ⟶ ٦، والعربيةُ أوّلاً: {_ar}/6", len(kept) == 6 and _ar == 6)

print("\n" + "═" * 70)
print(" ٢) القسمةُ على واحدٍ ليست قسمة — اثنان أو صفر")
print("═" * 70)


class _Deep(W):
    def __init__(self, subs):
        self.llm_fn = lambda *a, **k: json.dumps({"subs": subs})
        self.system_main = None
        self._deep_trimmed = 0


plan = [{"title": "المقدمة", "level": 1}]
for a in (1, 2, 3):
    plan.append({"title": f"المبحث {a}", "level": 1})
    for b in (1, 2, 3):
        plan.append({"title": f"المطلب {a}.{b}", "level": 2})
plan += [{"title": "الخاتمة", "level": 1}, {"title": "المراجع", "level": 1}]
subs = [{"index": i, "titles": [f"ت{i}-{k}" for k in range(1, 5)]}
        for i in range(1, 10)]

f = _Deep(subs)
out = f._deepen_structure(plan, "طلب", "موضوع", "تقسيم", "ar", budget_words=3000)
kids = {}
cur = None
for s in out:
    lv = int(s.get("level", 1))
    if lv == 2:
        cur = s["title"]
        kids.setdefault(cur, 0)
    elif lv == 3 and cur:
        kids[cur] += 1
lone = [k for k, v in kids.items() if v == 1]
chk(f"لا مطلبَ بتقسيمٍ واحد (كان 5 منها)", not lone, str(lone))
chk("والموجودُ اثنان فأكثر",
    all(v == 0 or v >= 2 for v in kids.values()), str(sorted(kids.values())))
chk(f"والمجموع ما زال تحت الميزانية: {len(out)} قسماً", len(out) <= 20)

f2 = _Deep(subs)
o2 = f2._deepen_structure(plan, "طلب", "موضوع", "تقسيم", "ar",
                          budget_words=12000)
chk("وميزانيةٌ واسعة ⟶ الـ36 كاملةً كما كانت",
    len(o2) - len(plan) == 36)

print("\n" + "═" * 70)
print(" ٣) المولَّدُ يُحجَز له نصيبُه من الميزانية")
print("═" * 70)
# التشغيل: متنٌ 3645 كلمة تحت سقف 3600، والمقاس 4114 (13.7 صفحة) لأن 9 مراجع
# وغلافاً وفهرساً أضافت ~469 كلمة لم تُحجَز في الخطة.
plan2 = [{"title": "المقدمة", "level": 1}]
for a in (1, 2, 3):
    plan2.append({"title": f"المبحث {a}", "level": 1})
    for b in (1, 2, 3):
        plan2.append({"title": f"المطلب {a}.{b}", "level": 2})
plan2 += [{"title": "الخاتمة", "level": 1},
          {"title": "قائمة المراجع", "level": 1}]
card_l = {"target_words": 3000, "max_words": 3600, "cover": True, "toc": True,
          "sources": [{"title": f"م{i}"} for i in range(9)]}
b = W._section_budgets(plan2, card_l, 120)
_sum = sum(int(v or 0) for v in b.values())
_res = card_l.get("length_reserved")
chk(f"حُجز للمولَّد {_res} كلمة (9×28 + غلاف + فهرس)", _res == 9 * 28 + 40 + 80)
chk(f"ونثرُ الأقسام {_sum} + المولَّد {_res} = {_sum + _res} ≤ 3600",
    _sum + _res <= 3600)
chk("ولا تنزل الحصّة تحت النصف مهما كثرت المراجع",
    W._section_budgets(plan2, {**card_l,
                               "sources": [{"t": i} for i in range(60)]},
                       120) != {})
b0 = W._section_budgets(plan2, {"target_words": 3000}, 120)
chk("وبلا مراجعَ ولا غلاف ⟶ الميزانية كما كانت",
    sum(int(v or 0) for v in b0.values()) > _sum)

print("\n" + "═" * 70)
print(" النتيجة: " + ("PASS ✅" if ok else "FAIL ❌"))
print("═" * 70)
sys.exit(0 if ok else 1)
