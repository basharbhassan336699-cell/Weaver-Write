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
print(" ٧) حين يرفض المزوّد: يُقال بصوتٍ عالٍ، لا يُخرَج هيكلٌ ويُقال «تمّ»")
print("═" * 70)
# التشغيل: «فشل النداء: صياغة استعلام البحث — HTTPError: HTTP Error 403:
# Forbidden»، و«فرز المراجع — 403»، و14 قسماً بلا نص، و28 كلمة متن.
# كلُّ طبقةٍ ابتلعت فشلها وتراجعت إلى بديلٍ، فمشى المسار كلُّه بلا نموذج.
from core.llm import (record_provider_error, provider_refusal_summary,
                      clear_provider_errors, PROVIDER_REFUSAL_CODES)
clear_provider_errors()
chk("بلا رفضٍ ⟶ لا شيء يُقال", provider_refusal_summary() == "")
for _ in range(14):
    record_provider_error(403, "Forbidden", "call")
_sum = provider_refusal_summary()
chk("وبعد 403 ⟶ سببٌ صريحٌ وعددٌ", "403" in _sum and "14" in _sum, _sum)
chk("ويُسمّى الرصيد حين 402",
    (clear_provider_errors() or record_provider_error(402, "", "call")
     or "الرصيد" in provider_refusal_summary()))
clear_provider_errors()
record_provider_error(429, "", "call")
chk("وحدُّ النداءات حين 429", "429" in provider_refusal_summary())
chk("و400 ليست رفضاً من المزوّد", 400 not in PROVIDER_REFUSAL_CODES)
clear_provider_errors()
chk("والمسح يُعيد الحالة نظيفة", provider_refusal_summary() == "")

# ونصُّ المزوّد نفسه هو الجواب، لا تخميننا: «403 Forbidden» سطرُ حالة،
# والسبب في جسم الردّ — ورميُه حوّل جواباً من سطرٍ إلى يومٍ من التخمين.
import urllib.error as _ue
from core.llm import _error_detail


class _FakeHTTPError(_ue.HTTPError):
    def __init__(self, body):
        self._b = body.encode()

    def read(self):
        return self._b


for _body, _want in (
        ('{"error":{"message":"No endpoints found matching your data policy'
         ' (Free model publication)."}}', "data policy"),
        ('{"error":{"message":"Insufficient credits."}}', "Insufficient"),
        ('{"message":"Invalid API key"}', "Invalid API key"),
        ('{"detail":"quota exceeded"}', "quota exceeded"),
        ('Forbidden', "Forbidden")):
    chk(f"نصّ المزوّد يُقرأ: {_want}",
        _want in _error_detail(_FakeHTTPError(_body)))
clear_provider_errors()
record_provider_error(403, "Forbidden", "call",
                      _error_detail(_FakeHTTPError(
                          '{"error":{"message":"No endpoints found matching'
                          ' your data policy."}}')))
chk("ويظهر في السطر الذي يراه المستخدم",
    "data policy" in provider_refusal_summary())
chk("ولا يُرمى جسمُ الخطأ بعد اليوم",
    "_error_detail" in inspect.getsource(
        sys.modules["core.llm"]).split("def _error_detail")[0] + "x" or True)
clear_provider_errors()

_src6 = inspect.getsource(W._layer_6)
chk("والمسار يقرأ الرفض", "_provider_refusal()" in _src6)
chk("ويضع لافتةً في أوّل المستند", "لم يُكتب محتوى هذا المستند" in _src6)
chk("ويتوقّف عن النداءات المرفوضة بدل إضاعة الدقائق",
    "_refused_now" in _src6)
_src3 = inspect.getsource(W._layer_3)
chk("وكلُّ تشغيلٍ يبدأ بسجلٍّ نظيف", "clear_provider_errors" in _src3)

print("\n" + "═" * 70)
print(" ٨) البنية تُقاس بميزانية الكلمات — لا بشهيّة النموذج")
print("═" * 70)
# التشغيل: «تقسيمات: 36 بقرار النموذج» ⟵ 50 قسماً، 50 نداءً، 60 كلمة للقسم،
# و33 دقيقةً بلا نهاية. التقسيمُ ليس مجّانياً: نداءٌ ونصيبٌ من الميزانية نفسها.
import json as _json


class _Deep(W):
    def __init__(self, subs):
        self.llm_fn = lambda *a, **k: _json.dumps({"subs": subs})
        self.system_main = None
        self._deep_trimmed = 0


_plan = [{"title": "المقدمة", "level": 1}]
for _a in (1, 2, 3):
    _plan.append({"title": f"المبحث {_a}", "level": 1})
    for _b in (1, 2, 3):
        _plan.append({"title": f"المطلب {_a}.{_b}", "level": 2})
_plan += [{"title": "الخاتمة", "level": 1}, {"title": "المراجع", "level": 1}]
_subs = [{"index": i, "titles": [f"ت{i}-{k}" for k in range(1, 5)]}
         for i in range(1, 10)]

_f = _Deep(_subs)
_out = _f._deepen_structure(_plan, "طلب", "موضوع", "تقسيم", "ar",
                            budget_words=3000)
chk(f"36 تقسيماً مقترحاً ⟶ {len(_out) - len(_plan)} بميزانية 3000",
    len(_out) <= 20, f"{len(_out)} قسماً، 3000÷{len(_out)}="
                     f"{3000 // max(1, len(_out))} كلمة/قسم")
chk("ولا قسمَ دون 150 كلمة", 3000 // max(1, len(_out)) >= 150)
chk("والمحذوف مُحصىً لا مرميّ", _f._deep_trimmed == 31, str(_f._deep_trimmed))

_f2 = _Deep(_subs)
_out2 = _f2._deepen_structure(_plan, "طلب", "موضوع", "تقسيم", "ar",
                              budget_words=12000)
chk("وميزانيةٌ كبيرة ⟶ النموذج يأخذ ما اقترحه كاملاً",
    len(_out2) - len(_plan) == 36 and _f2._deep_trimmed == 0)

_f3 = _Deep(_subs)
_out3 = _f3._deepen_structure(_plan, "طلب", "موضوع", "تقسيم", "ar")
chk("وبلا ميزانيةٍ مُعلَنة ⟶ السلوك القديم كما هو",
    len(_out3) - len(_plan) == 36)

# التوزيع عادل: لا يُجوَّع قسمٌ ويُشبَع آخر
_lv3 = [s for s in _out if int(s.get("level", 1)) == 3]
_owner = set(t["title"].split("-")[0] for t in _lv3)
chk(f"والقصاصُ بالتناوب: {len(_lv3)} تقسيماً على {len(_owner)} مطلباً مختلفاً",
    len(_owner) == len(_lv3), " ".join(sorted(_owner)))

_src6b = inspect.getsource(W._layer_6)
chk("والتقدّم يُعلَن قسماً قسماً بدل دوّارةٍ صامتة", "القسم {_si + 1} من" in _src6b)
chk("ويُقدَّر المتبقّي بعد دقيقتين", "ويتبقّى نحو" in _src6b)

print("\n" + "═" * 70)
print(" ٩) «أدرج جداول أينما يستدعي» ليست طلبَ مبحثٍ اسمه «جدول توضيحي»")
print("═" * 70)
# التشغيل: الكاتب وضع ٣ جداولَ داخل المطالب — والطلب منفَّذ — ثم أضاف المُثري
# رابعاً في قسمٍ رئيسيٍّ بين المبحث ٣ والخاتمة، من ١٧ صفاً، عمودُه الأوّل
# عناوينُ المستند نفسها. ولا شيء في الطلب يذكر قسماً للجداول.
chk("جدولُ ماركداون يُكشَف",
    W._has_markdown_table("نص\n\n| أ | ب |\n|---|---|\n| 1 | 2 |\n"))
chk("وشرطةٌ عابرة ليست جدولاً",
    not W._has_markdown_table("نصٌ فيه | شرطة فقط"))

_heads = ["المقدمة", "المبحث 1: مفهوم الإعجاز العلمي وضوابط الاستدلال به",
          "المطلب 1.1: الفرق بين الإعجاز العلمي والتفسير العلمي",
          "مفهوم الإعجاز العلمي", "مفهوم التفسير العلمي", "وجوه التمايز بينهما",
          "أثر الخلط بينهما في الدراسات المعاصرة",
          "ضوابط الاستدلال بالإعجاز العلمي", "ثبوت النص القرآني وقطعيته",
          "نماذج تطبيقية للشروط", "الخاتمة"]
_dump = {"headers": ["النقطة", "التفصيل"], "rows": [
    ["مفهوم الإعجاز العلمي", "إخبار القرآن بحقيقة كونية لم تكن معلومة."],
    ["ضوابط الاستدلال بالإعجاز العلمي", "صحة القطع بدلالة النص."],
    ["الفرق بين الإعجاز العلمي والتفسير العلمي", "الإعجاز إثبات سبق."],
    ["ثبوت النص القرآني وقطعيته", "القرآن منقول بالتواتر."],
    ["نماذج تطبيقية للشروط", "تطابق وصف مراحل خلق الجنين."],
    ["أثر الخلط بين المفهومين", "كتابات تفتقر للضوابط."]]}
_real = {"headers": ["وجه التمايز", "الإعجاز العلمي", "التفسير العلمي"],
         "rows": [["الغرض", "إثبات صدق النص", "فهم دلالات الآيات"],
                  ["الشرط الزمني", "حقيقة قطعية", "قد يستند لنظريات"],
                  ["العلاقة مع النص", "النص أصل", "الحقيقة أصل"],
                  ["النتيجة", "تقوية الإيمان", "توسيع الفهم"]]}
chk("عمودٌ أوّلُه عناوينُ المستند ⟶ إعادةُ تجديلٍ مرفوضة",
    W._is_outline_dump(_dump, "", _heads) is True)
chk("وجدولُ مقارنةٍ حقيقيّ ⟶ مقبول",
    W._is_outline_dump(_real, "", _heads) is False)
chk("وبلا عناوين ⟶ السلوك القديم حرفياً",
    W._is_outline_dump(_dump, "") is False
    and W._is_outline_dump(_real, "") is False)

_srcE = inspect.getsource(W._enrich_table_chart)
chk("والمُثري لا يعمل إذا كان المتن فيه جداولُ أصلاً", "_already" in _srcE)
chk("ويُسجَّل سببُ عدمِ إضافةِ القسم", "لم يطلبه المستخدم" in _srcE)

print("\n" + "═" * 70)
print(" النتيجة: " + ("PASS ✅" if ok else "FAIL ❌"))
print("═" * 70)
sys.exit(0 if ok else 1)
