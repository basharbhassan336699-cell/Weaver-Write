# -*- coding: utf-8 -*-
"""«أريدك ٩ مراجع» فعاد باثنين — والسبعةُ سقطت في صمتٍ داخل `_bib_sources`.

لم يكن العطبُ في النموذج، ولا في البحث، ولا في القواعد. كان في سطرٍ واحدٍ
يقرّر أيُّ مصدرٍ يستحقّ أن يُطبع في قائمة المراجع:

    _is_acad = doi  OR  tier >= 4  OR  (venue AND authors)

وأكثرُ الأدبِ العربيّ بلا DOI، والفهارسُ تُعيد اسمَ المجلّة **أو** أسماءَ
المؤلِّفين أكثرَ ممّا تُعيدهما معاً — فاشتراطُ اجتماعهما كان في الواقع اشتراطَ
DOI. تسعةُ مراجعَ عربيةٍ عاديةٍ تدخل، فيُطبع منها اثنان.

والأدهى: `card["refs_general_dropped"] = 7` كان يُكتب في البطاقة **ولا يقرؤه
أحدٌ في المشروع كلِّه** — فالقارئُ يطلب تسعةً، ويستلم اثنين، ولا يُقال له شيء.

والحارسُ الذي بُني لأجل هذا السطر (ألّا تُطبع صفحةُ وزارةٍ أو موقعُ رفعٍ
بجانب دراسةٍ محكَّمة) لم يكن «هل فيه حقلان»، بل **من أين جاء**. فصار المصدرُ
المفهرَس (OpenAlex/Crossref/DOAJ/…) يكفيه جهةُ نشرٍ **أو** مؤلِّف؛ وصفحةُ
الويب تُحاكَم بالصرامة نفسِها التي كانت."""
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


def idx(**k):
    return dict(source="openalex", **k)


NINE = [
    idx(title="أحكام الزواج في الفقه الإسلامي", doi="10.1/a",
        venue="مجلة الشريعة", authors=["الزحيلي"]),
    idx(title="الولاية في عقد النكاح", venue="مجلة كلية الشريعة",
        authors=["ابن عاشور"]),
    idx(title="المهر وأحكامه", authors=["القرضاوي"]),
    idx(title="موانع الزواج المؤبدة", venue="حوليات الجامعة"),
    idx(title="الشروط في عقد الزواج", authors=["السنهوري"]),
    idx(title="النفقة الزوجية", authors=["الزرقا"]),
    idx(title="الكفاءة في النكاح", venue="مجلة البحوث"),
    idx(title="عقد الزواج المدني", authors=["شلبي"]),
    idx(title="الطلاق وأثره", authors=["أبو زهرة"]),
]

print("═" * 70)
print(" ١) تسعةٌ تدخل — وتسعةٌ تخرج")
print("═" * 70)
card = {"request": "أريدك ٩ مراجع عربية", "reference_count": 9}
acad, gen = W._bib_sources(NINE, card, "ar")
chk(f"يُطبع {len(acad)} من ٩ (كان يُطبع اثنان)", len(acad) == 9, str(len(acad)))
chk("ولا يُسقَط شيء", gen == [])
chk("مرجعٌ بمؤلِّفٍ بلا مجلّةٍ ولا DOI يبقى",
    any(s["title"] == "المهر وأحكامه" for s in acad))
chk("ومرجعٌ بمجلّةٍ بلا مؤلِّفٍ ولا DOI يبقى",
    any(s["title"] == "الكفاءة في النكاح" for s in acad))

print("\n" + "═" * 70)
print(" ٢) والحارسُ لم يُفتح: من أين جاء المصدرُ هو الفيصل")
print("═" * 70)
WEB = [
    {"title": "وزارة العدل — الزواج", "source": "web", "venue": "وزارة العدل",
     "url": "https://moj.gov.sa/x"},
    {"title": "مدوّنتي عن الزواج", "source": "web", "authors": ["فلان"]},
    {"title": "دراسةٌ محكَّمة", "source": "crossref", "doi": "10.2/b"},
]
card2 = {}
a2, g2 = W._bib_sources(WEB, card2, "ar")
chk("صفحةُ الوزارة خارج القائمة كما كانت",
    all("وزارة" not in s["title"] for s in a2))
chk("والمدوّنةُ خارجها كما كانت",
    all("مدوّنتي" not in s["title"] for s in a2))
chk("والمحكَّمةُ داخلها", any("محكَّمة" in s["title"] for s in a2))
chk("وصفحةُ ويبٍ بجهةِ نشرٍ لا تدخل بحجّة الحقل الواحد", len(a2) == 1)

print("\n" + "═" * 70)
print(" ٣) وما يُستبعَد يُقال — لا يُكتب في حقلٍ لا يقرؤه أحد")
print("═" * 70)
chk(f"استُبعد {len(g2)} ⟶ وسُجِّل في البطاقة",
    card2.get("refs_general_dropped") == 2)
_n = card2.get("skipped_steps") or []
chk("ويُقال للقارئ نصّاً", any(x.get("step") == "قائمة المراجع" for x in _n),
    str(_n)[:100])
chk("ويُذكر العددان: المطبوعُ والمستبعَد",
    any("1" in x.get("reason", "") and "2" in x.get("reason", "")
        for x in _n), str(_n)[:120])
chk("ويُقال إنّها لم تُحذف من البحث",
    any("لم تُحذف" in x.get("reason", "") for x in _n))
chk("ولا ملاحظةَ حين لا يُستبعَد شيء",
    not (card.get("skipped_steps") or []))

print("\n" + "═" * 70)
print(" ٤) ولا ينهار على مُدخَلٍ شاذّ")
print("═" * 70)
chk("قائمةٌ فارغة", W._bib_sources([], {}, "ar") == ([], []))
chk("ولا محكَّمَ إطلاقاً ⟶ تبقى القائمةُ ولا تُفرَّغ",
    W._bib_sources([{"title": "خبر", "source": "web"}], {}, "ar")[0] != [])
chk("وبطاقةٌ ليست قاموساً لا تُسقط الدالّة",
    isinstance(W._bib_sources(NINE, None, "ar"), tuple))

print("\n" + "═" * 70)
print(" النتيجة: " + ("PASS ✅" if ok else "FAIL ❌"))
print("═" * 70)
sys.exit(0 if ok else 1)
