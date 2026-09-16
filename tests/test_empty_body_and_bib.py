# -*- coding: utf-8 -*-
"""ما أظهره تشغيل «الإعجاز العلمي»: مستندٌ بلا متن، وقائمةٌ بلا فرز.

أربعةَ عشرَ عنواناً بلا سطرِ نصٍّ واحدٍ تحتها، وكلُّ خطوةٍ تقول «تمّ»؛ وستةَ
عشرَ مرجعاً لطلبِ تسعة، فيها موقعُ مقالاتٍ عامّ وكتابٌ مكرّرٌ برابطين. كلُّ
فحصٍ هنا يعيد إنتاج العطب من ذلك التشغيل، ثم يثبت زواله."""
import sys, os, importlib.util as iu
# THE TESTS ONLY RAN ON THE MACHINE THEY WERE WRITTEN ON — the root is computed
# from this file's own location, so the suite runs from any clone on any device.
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
for k in list(os.environ):
    if k.startswith("WEAVER_"):
        os.environ.pop(k)
from pipeline.orchestrator import WeaverOrchestrator as W, Task
sp = iu.spec_from_file_location(
    "fa", _ROOT + "/capabilities/skills/apa_formatter/scripts/format_apa.py")
fa = iu.module_from_spec(sp); sp.loader.exec_module(fa)
ok = True


def chk(label, good, detail=""):
    global ok
    ok &= bool(good)
    print(f"   {'✅' if good else '❌'} {label}" + (f" — {detail}" if detail else ""))


print("═" * 70)
print(" ١) الفرز المحكَّم لم يكن يعمل أصلاً على هذا المسار")
print("═" * 70)
# `lang` كانت تُقرأ قبل إسنادها بـ29 سطراً ⟶ UnboundLocalError يبتلعه except،
# فتخرج القائمة بلا أيّ فرز. ولهذا وقف alukah.net بجوار ورقةٍ محكَّمة.
o = W.__new__(W)
t = Task.__new__(Task)
t.task_card = {
    "language": "ar", "sourcing_mode": "cited", "citation_style": "APA",
    "sources": [
        {"title": "ورقة محكّمة", "doi": "10.1/x", "venue": "مجلة علمية",
         "authors": ["فلان الفلاني"], "year": 2024,
         "url": "https://doi.org/10.1/x"},
        {"title": "الإعجاز العلمي في القرآن - شبكة الألوكة",
         "url": "https://www.alukah.net/sharia/0/114148/"},
        {"title": "بحث عن الإعجاز العلمي - موقع محتويات",
         "url": "https://mhtwyat.com/x"},
        {"title": "موسوعة الإعجاز", "url": "https://quran-m.com/"},
    ]}
t.draft = ""
t.sections = []
o._append_references(t)
body = "\n".join(s.get("body", "") for s in (t.sections or []))
chk("الورقة المحكَّمة باقية", "ورقة محكّمة" in body)
chk("alukah.net خارج القائمة", "alukah" not in body)
chk("mhtwyat.com خارج القائمة", "mhtwyat" not in body)
chk("quran-m.com خارج القائمة", "quran-m" not in body)
_notes = " | ".join(n.get("reason", "")
                    for n in (t.task_card.get("skipped_steps") or []))
chk("والاستبعادُ مسجَّلٌ لا صامت", "استُبعد 3" in _notes, _notes[:70])

print("\n" + "═" * 70)
print(" ٢) مرجعٌ واحدٌ برابطين ليس مرجعين")
print("═" * 70)
dup = [
    {"title": "كتاب الإعجاز العلمي - جامعة المدينة",
     "url": "https://shamela.ws/book/31080"},
    {"title": "كتاب الإعجاز العلمي - جامعة المدينة",
     "url": "https://shamela.ws/index.php/book/31080"},
    {"title": "ورقة", "doi": "10.1/y", "url": "https://doi.org/10.1/y"},
    {"title": "ورقة", "doi": "https://doi.org/10.1/y",
     "url": "https://mirror.example/y"},
    {"title": "أخرى", "url": "https://x.org/a/"},
    {"title": "أخرى", "url": "http://www.x.org/a?utm=1#top"},
]
chk("ستةُ سجلّاتٍ ⟶ ثلاثةُ مراجع", len(fa.dedupe_sources(dup)) == 3,
    str(len(fa.dedupe_sources(dup))))
_b = fa.build_bibliography(dup)
chk("ولا يتكرّر الكتاب في المطبوع", _b.count("/book/31080") == 1,
    f"ظهر {_b.count(chr(34)+chr(34)) if False else _b.count('/book/31080')} مرّة")

print("\n" + "═" * 70)
print(" ٣) doi.org موجِّهٌ لا ناشر")
print("═" * 70)
e = fa.format_apa_website("الإعجاز العلمي في القرآن الكريم",
                          "https://doi.org/10.53796/hnsj4411", 2023)
chk("لا يُطبع «doi.org» اسمَ موقع", "*doi.org*" not in e, e[:70])
chk("والرابط باقٍ", "10.53796/hnsj4411" in e)
chk("وموقعٌ حقيقيّ ما زال يُذكر",
    "*shamela.ws*" in fa.format_apa_website("كتاب", "https://shamela.ws/b/1"))

print("\n" + "═" * 70)
print(" ٤) العدد المطلوب جزءٌ من الطلب")
print("═" * 70)
card = {"requirements": [{"kind": "source", "target": 9, "must": True}]}
chk("العدد يُقرأ من القائمة المصنّفة", W._requested_source_count(card) == 9)
chk("ومن نصّ الطلب حين لا قائمة",
    W._requested_source_count({"request": "مع 9 مراجع موثقة"}) == 9)
chk("وبلا طلبٍ ⟶ None", W._requested_source_count({"topic": "الطاقة"}) is None)
many = [{"title": f"م{i}", "doi": f"10.1/{i}", "venue": "مجلة",
         "verify_state": "verified" if i < 5 else ""} for i in range(16)]
kept, over = W._cap_to_requested(many, card, "", "ar")
chk("ستةَ عشرَ ⟶ تسعة", len(kept) == 9 and len(over) == 7,
    f"{len(kept)} + {len(over)}")
chk("والمتحقَّق منها أُبقيت أولاً",
    sum(1 for x in kept if x.get("verify_state")) == 5)
# مرجعٌ مستشهَدٌ به لا يُحذف مهما كان العدد
cited = [{"title": "مستشهد", "authors": ["زيدان"], "year": 2020,
          "venue": "مجلة"}] + many
k2, o2 = W._cap_to_requested(cited, card, "كما بيّن (زيدان، 2020) فإن…", "ar")
chk("ومرجعٌ مستشهَدٌ به في النصّ لا يُسقَط",
    any(x.get("title") == "مستشهد" for x in k2))

print("\n" + "═" * 70)
print(" ٥) عنوانٌ فارغٌ من المعنى: أرقامٌ بلا موضوع")
print("═" * 70)
for _t, _e in (("المبحث 1", True), ("المطلب 1.1", True), ("الباب 2", True),
               ("الجزء 3.1", True), ("Section 3", True), ("المقدمة", False),
               ("المبحث 1: مفهوم الإعجاز وضوابطه", False),
               ("قائمة المراجع", False)):
    chk(f"الشكل: {_t}", W._is_bare_label(_t) is _e)


class _Half(W):
    """نموذجٌ يُسمّي نصف الأقسام فقط — وهو حال النموذج الضعيف."""
    def __init__(self):
        self.llm_fn = self._fn
        self.system_main = None
        self._n = 0

    def _fn(self, prompt, **kw):
        import re
        n = len(re.findall(r"^\d+\.\s", prompt, re.M)) or 1
        return "\n".join(f"{i+1}. عنوانٌ وصفيٌّ للقسم رقم {i+1}"
                         for i in range(n) if i % 2 == 0)


plan = ([{"title": "المقدمة", "level": 1}]
        + [{"title": f"المبحث {a}", "level": 1} for a in (1, 2, 3)]
        + [{"title": "الخاتمة", "level": 1}])
out = _Half()._descriptive_titles("الإعجاز العلمي في القرآن", plan, "ar")
named = [s["title"] for s in out if ":" in s["title"]]
chk(f"القديم كان يرمي الجميع لفشلِ واحد — الآن سُمّي {len(named)} من 3",
    len(named) >= 1, " | ".join(named))
chk("وغيرُ المسمّى يحتفظ بعنوانه النظيف",
    any(s["title"] == "المبحث 2" for s in out)
    or all(":" in s["title"] for s in out[1:4]))

print("\n" + "═" * 70)
print(" ٦) إعادة الصياغة تغيّر الألفاظ لا الحجم")
print("═" * 70)
# طبقة ٦.٥ كانت تُسند ناتجها فوق task.draft بلا أيّ فحص: ناتجٌ فارغٌ يمحو
# المستند كلَّه في صمت، ولا خطوةَ بعده تستطيع التمييز.
import inspect
_src65 = inspect.getsource(W._layer_6_5)
chk("الناتج لم يعد يُسنَد مباشرةً", "task.draft = self._humanize_draft" not in _src65)
chk("ويُقاس قبل القبول", "_bw, _aw" in _src65)
chk("ويُرفض الفارغ", "_aw == 0" in _src65)
chk("ويُسجَّل الرفض", "أنسنة النصّ" in _src65)

_src6 = inspect.getsource(W._layer_6)
chk("والأقسام الفارغة تُعدّ وتُسجَّل", "_empty_secs" in _src6)
chk("وعدد الكلمات يُعلَن مع عدد الأقسام", "كلمة" in _src6 and "صياغة:" in _src6)

print("\n" + "═" * 70)
print(" النتيجة: " + ("PASS ✅" if ok else "FAIL ❌"))
print("═" * 70)
sys.exit(0 if ok else 1)
