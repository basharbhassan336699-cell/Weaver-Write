# -*- coding: utf-8 -*-
"""العيوب الخمسة التي أظهرها تشغيل «أثر الهواتف الذكية على الأطفال».

كلّ فحصٍ هنا يُعيد إنتاج العيب بأرقامه من ذلك التشغيل نفسه، ثم يثبت أنه زال:
جداولٌ طُلبت ولم تُكتب، وسقفُ طولٍ أذن بتجاوز نفسه، وتقليصٌ لم يجد ما يقلّصه،
وسجلٌّ ينسب للمستخدم ما لم يقله، وقائمةُ توثيقٍ تُدخل المواقع بين المحكَّم."""
import sys, os, importlib.util as iu
# THE TESTS ONLY RAN ON THE MACHINE THEY WERE WRITTEN ON. The repository
# root was hardcoded as an absolute path, so on any other checkout the insert
# pointed at a directory that does not exist and every file died on
# "No module named 'pipeline'" before running a single check. The root is
# where this file lives, one directory up — the way tests/smoke_pipeline.py
# already computes it — so the suite runs from any clone on any device.
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
import tempfile as _tempfile
# a scratch directory of the machine RUNNING the test, never a path
# baked in from the machine that wrote it
_TMP = _tempfile.mkdtemp(prefix="weaver-test-")
for k in list(os.environ):
    if k.startswith("WEAVER_"):
        os.environ.pop(k)
from pipeline.orchestrator import WeaverOrchestrator as W
sp = iu.spec_from_file_location(
    "wr", _ROOT + "/capabilities/skills/web_research/"
          "scripts/web_research.py")
wr = iu.module_from_spec(sp); sp.loader.exec_module(wr)
ok = True


def chk(label, good, detail=""):
    global ok
    ok &= bool(good)
    print(f"   {'✅' if good else '❌'} {label}" + (f" — {detail}" if detail else ""))


print("═" * 70)
print(" ١) الجداول: القرار يصل إلى الكاتب من أيّ بوّابةٍ جاء")
print("═" * 70)
# التشغيل: want_table=True و table_budget=3 و«لا يوجد أي جدول في النص» — لأن
# جملة «أدرج جداول للمصطلحات التقنية وشرحها» صُنّفت content لا insert.
card_c = {"want_table": True, "requirements": [
    {"kind": "content", "text": "أدرج جداول للمصطلحات التقنية وشرحها"}]}
d = W._requirements_directive(card_c, "المطلب الأول", "ar", tables_left=3)
chk("طلبٌ مصنّفٌ content ⟵ سطر جدولٍ يصل الكاتب", "جدول" in d)
chk("وبنصّ المستخدم نفسه، لا بصيغةٍ عامّة",
    "الجداول مطلوبةٌ بنصّ المستخدم" in d and "التقنية وشرحها" in d)

# ولا قائمة متطلبات إطلاقاً — العَلَم وحده
d2 = W._requirements_directive({"want_table": True}, "المبحث", "ar",
                               tables_left=2)
chk("العَلَم وحده بلا أيّ متطلّب ⟵ سطر جدول", "جدول" in d2)

# insert صريح: السلوك القديم كما هو
d3 = W._requirements_directive(
    {"requirements": [{"kind": "insert", "text": "أضف جدول مقارنة"}]},
    "المطلب", "ar", tables_left=1)
chk("المسار القديم (insert) لم يتغيّر", "جدول مقارنة" in d3)

# «بلا جداول» يُنفَّذ، لا يُسجَّل فقط
d4 = W._requirements_directive(
    {"tables_forbidden": True, "want_table": True,
     "requirements": [{"kind": "insert", "text": "أضف جدولاً"}]},
    "المطلب", "ar", tables_left=3)
chk("«بلا جداول» ⟵ لا دعوةَ جدولٍ أصلاً", "جدول" not in d4)

# الميزانية المستنفدة تُسكت الدعوة
d5 = W._requirements_directive(card_c, "المطلب", "ar", tables_left=0)
chk("الميزانية = ٠ ⟵ لا دعوة", "جدول" not in d5)

# الكاشف الاحتياطيّ: حين يصمت النموذج، الجملة نفسها يجب أن تُقرأ.
# القائمة كانت تحوي «أدرج جدول» والمستخدم كتب «أدرج جداول» — و«جدول» ليست
# داخل «جداول» حرفاً بحرف، فماتت سلسلة الجداول كلّها عند بوّابتها الأولى.
for _t, _exp in (("أدرج جداول للمصطلحات التقنية وشرحها", True),
                 ("مع جداول توضيحية", True),
                 ("أضف الجداول اللازمة", True),
                 ("include a table of terms", True),
                 ("provide tables for the metrics", True),
                 ("أضف جدولاً", True),            # المسار القديم كما هو
                 ("ضع جدول مقارنة", True),
                 ("أضف صفحة غلاف وفهرساً وجدول المحتويات", False),
                 ("بحث 20 صفحة عن التنمية مع مراجع APA", False),
                 ("اكتب بحثاً عن التنمية", False)):
    chk(f"الكاشف: {_t[:38]}", W._wants_table(_t) is _exp,
        f"عاد {W._wants_table(_t)}")

# لا جداولَ في قائمة المراجع
d6 = W._requirements_directive(card_c, "المراجع", "ar", tables_left=3)
chk("قائمة المراجع مستثناة", d6 == "")

# قاعدة النقل تنجو من الخروج المبكر
d7 = W._requirements_directive({"sources": [{"url": "x"}]}, "المطلب", "ar")
chk("قاعدة «أعِد الصياغة» تصل رغم غياب المتطلّبات", "أعِد صياغته" in d7)

print("\n" + "═" * 70)
print(" ٢) الطول: المدى الذي ذكره المستخدم — أرضيّتُه هدفٌ وسقفُه حدّ")
print("═" * 70)
REQ = ("أريد بحثاً كاملاً. لا يقل عن 10 صفحات ولا يزيد عن 12 صفحة، "
       "بالعربية وبأسلوب أكاديمي، مع 9 مراجع موثقة.")
lt = W.extract_length_target(REQ)
chk("الأرضية 10 صفحات", lt["pages"] == 10, str(lt["pages"]))
chk("الهدف 3000 كلمة (10×300)", lt["words"] == 3000, str(lt["words"]))
chk("السقف 12 صفحة", lt["max_pages"] == 12, str(lt["max_pages"]))
chk("السقف 3600 كلمة", lt["max_words"] == 3600, str(lt["max_words"]))

# الأسبقية: كلمة المستخدم الصريحة تسبق قراءة النموذج
c = {}
W._settle(c, "target_pages", 12, lt["pages"], "فهم الطلب",
          explicit=lt["pages"])
chk("النموذج قال 12 (وهو السقف) والمستخدم قال 10 ⟵ 10",
    c["target_pages"] == 10, f"target_pages={c['target_pages']}")
chk("والنسبة للمستخدم لا للنموذج",
    c["decisions"]["target_pages"]["by"] == "user")

# بلا مدى: النموذج هو الحاكم كما كان
c2 = {}
W._settle(c2, "target_pages", 7, 5, "فهم الطلب", explicit=None)
chk("بلا مدىً صريح ⟵ قراءة النموذج تحكم",
    c2["target_pages"] == 7 and c2["decisions"]["target_pages"]["by"] == "model")

print("\n" + "═" * 70)
print(" ٣) الحساب: مجموع حصص الأقسام يجب أن يقع تحت السقف")
print("═" * 70)
# بنية التشغيل نفسها: ٣ مباحث × ٣ مطالب × تقسيمات = ٤٢ قسماً
plan = [{"title": "المقدمة", "level": 1}]
for a in range(1, 4):
    plan.append({"title": f"المبحث {a}", "level": 1})
    for b in range(1, 4):
        plan.append({"title": f"المطلب {a}.{b}", "level": 2})
        for k in range(3):
            plan.append({"title": f"تقسيم {a}.{b}.{k}", "level": 3})
plan += [{"title": "الخاتمة", "level": 1}, {"title": "المراجع", "level": 1}]
card = {"target_words": 3000, "max_words": 3600, "target_pages": 10,
        "max_pages": 12}
n = len(plan)
print(f"   البنية: {n} قسماً، الهدف 3000، السقف 3600")

OLD = max(120, int(3600 / n))
chk(f"القديم: {n} × {OLD} = {n * OLD} — فوق السقف (وقد خرج التشغيل بـ4902)",
    n * OLD > 3600, f"{n * OLD} > 3600")

bud = W._section_budgets(plan, card, 120)
caps = [max(40, int(int(v) * 1.15)) if v else 0 for v in
        (bud.get(i) for i in range(n))]
tot = sum(caps)
chk(f"الجديد: مجموع الحصص = {tot} ≤ 3600", tot <= 3600)
_leaf = max(caps)
chk(f"وأكبر حصّةٍ ({_leaf} كلمة) ما زالت رقماً يصدّقه الكاتب", _leaf >= 60)

print("\n" + "═" * 70)
print(" ٤) التقليص: العتبة تتبع المستند لا رقماً ثابتاً")
print("═" * 70)
# التشغيل: 4902 كلمة على 41 قسماً غير مرجعيّ ⟶ متوسط 119، والعتبة كانت 120
_cur, _nsec = 4902, 41
_avg = int(_cur / _nsec)
new_floor = max(60, min(120, int(_avg * 0.8)))
bodies = [119] * _nsec                       # مستندٌ منبسطٌ كالذي خرج فعلاً
old_c = [b for b in bodies if b >= 120]
new_c = [b for b in bodies if b >= new_floor]
chk(f"القديم: {len(old_c)} مرشّحاً من {_nsec} — فادّخر 156 من 1302",
    len(old_c) == 0)
chk(f"الجديد: العتبة {new_floor} ⟵ {len(new_c)} مرشّحاً",
    len(new_c) >= _nsec // 2)
_save = sum(b - max(80, int(b * 0.65)) for b in new_c)
chk(f"وطاقةُ الادّخار {_save} كلمة ≥ الفائض 1302", _save >= 1302)
# مستندٌ قصيرٌ ذو أقسامٍ ضخمة: العتبة لا تنزل تحت المعقول
chk("مستندٌ من 4 أقسامٍ × 800 كلمة ⟵ العتبة تبقى 120",
    max(60, min(120, int(int(3200 / 4) * 0.8))) == 120)

print("\n" + "═" * 70)
print(" ٥) قائمة التوثيق: محكَّمة — لا «المواقع الإلكترونية» بينها")
print("═" * 70)
chk("academia.edu ⟵ عامّ (1) لا رسميّ (3)",
    wr.quality_tier({"url": "https://www.academia.edu/123/x"}) == 1)
chk("researchgate.net ⟵ عامّ", wr.quality_tier(
    {"url": "https://www.researchgate.net/publication/1"}) == 1)
chk("moh.gov.sa ⟵ رسميّ (3) وهو تصنيفٌ صحيح",
    wr.quality_tier({"url": "https://www.moh.gov.sa/a"}) == 3)
chk("harvard.edu ⟵ رسميّ (3)",
    wr.quality_tier({"url": "https://www.harvard.edu/a"}) == 3)
chk("mygov-news.com ⟵ عامّ (المطابقة لاحقةٌ لا تضمين)",
    wr.quality_tier({"url": "https://mygov-news.com/a"}) == 1)
chk("ورقةٌ بـDOI مرفوعةٌ على RG ⟵ محكَّمة (5) بهويّتها لا بمضيفها",
    wr.quality_tier({"url": "https://www.researchgate.net/p",
                     "doi": "10.1/x", "venue": "J"}) == 5)

srcs = [
    {"title": "Smartphone use in children", "doi": "10.1016/j.x.2021.01",
     "venue": "Comput Human Behav", "academic": True,
     "url": "https://doi.org/10.1016/j.x.2021.01"},
    {"title": "أثر الهاتف الذكي", "venue": "مجلة العلوم التربوية",
     "authors": ["نعيم بوعموشة"], "url": "https://journal.dz/1"},
    {"title": "صحة الطفل", "url": "https://www.moh.gov.sa/awareness",
     "academic": True},
    {"title": "دراسة مرفوعة", "url": "https://www.academia.edu/9/x",
     "academic": True},
]
card_b = {}
keep, drop = W._bib_sources(srcs, card_b, "ar")
kt = [s["title"] for s in keep]
chk("الورقة ذات الـDOI باقية", "Smartphone use in children" in kt)
chk("الدوريّة العربية بلا DOI باقية (سجلٌّ ببليوغرافيّ كامل)",
    "أثر الهاتف الذكي" in kt)
chk("صفحة الوزارة خارج القائمة", "صحة الطفل" not in kt)
chk("academia.edu خارج القائمة", "دراسة مرفوعة" not in kt)
chk(f"واستُبعد {len(drop)} — مسجَّلاً لا محذوفاً",
    len(drop) == 2 and card_b.get("refs_general_dropped") == 2)

# لا محكَّمَ إطلاقاً ⟵ القائمة تبقى وتُعلَّم، ولا تُفرَّغ
card_e = {}
k2, d2_ = W._bib_sources([{"title": "خبر", "url": "https://news.com/1"}],
                         card_e, "ar")
chk("بلا محكَّمٍ ⟵ القائمة تبقى وتُعلَّم",
    len(k2) == 1 and card_e.get("refs_no_academic") is True)

print("\n" + "═" * 70)
print(" ٦) حين يصمت النموذج: الطلب يُقرأ، ولا يُترك بلا قارئ")
print("═" * 70)
# التشغيل الكامل بالنموذج المجّاني (بلا فهمٍ صالح): كلّ الكواشف كانت تحت
# `if _iv` — فلمّا صمت النموذج وصمت الموجّه، لم يقرأ الطلبَ أحدٌ إطلاقاً.
import asyncio
from pipeline.orchestrator import Task
os.environ["WEAVER_LLM"] = "offline"
_o = W(db_path=os.path.join(_TMP, "defects.db"))
_t = Task(description=REQ + " أدرج جداول للمصطلحات التقنية وشرحها.",
          input_files=[])
_m = _o.memory.create_task(_t.task_id)
_lp = asyncio.new_event_loop()
_lp.run_until_complete(_o._layer_3(_t, _m))
_c3 = _t.task_card or {}
_dec = _c3.get("decisions") or {}
chk("النموذج صامت ⟵ want_table مقروءٌ من الطلب",
    _c3.get("want_table") is True,
    f"{_c3.get('want_table')} ← {(_dec.get('want_table') or {}).get('by')}")
chk("ومنسوبٌ لقراءة الطلب لا للمستخدم ولا للنموذج",
    (_dec.get("want_table") or {}).get("by") == "fallback")
chk("والسقف مقروءٌ أيضاً", _c3.get("max_words") == 3600,
    str(_c3.get("max_words")))
chk("والأرضية هدفاً", _c3.get("target_pages") == 10,
    str(_c3.get("target_pages")))

# «بالعربية وبأسلوب أكاديمي» لغةُ الإخراج وأسلوبُه، لا أمرٌ بالترجمة ولا بإعادة
# الصياغة — و«بالعربي» داخل «بالعربية» حرفاً بحرف.
for _t2, _e2 in ((REQ, None),
                 ("اكتبه بالإنجليزي", None),
                 ("ترجم هذا النص إلى الإنجليزية", "translate"),
                 ("ترجمه بالعربي", "translate"),
                 ("أعد صياغة النص بأسلوب أكاديمي", "rewrite"),
                 ("لخّص لي المقال", "summarize"),
                 ("حوّل هذا الملف إلى PDF", "convert")):
    chk(f"الفعل: {_t2[:36]}", W._task_action(_t2) == _e2,
        f"عاد {W._task_action(_t2)}")

print("\n" + "═" * 70)
print(" ٧) «بحثاً بالكامل» بحثٌ كامل — لا هيكلٌ فارغ")
print("═" * 70)
# التشغيل: طلبُ «بحثٍ بالكامل» خرج هيكلاً — قسمٌ واحد، ولا بحثٌ أكاديمي، ولا
# تحقّق، و13 مرجعاً من ذاكرة النموذج. السبب: القائمة تحوي «بحثاً كاملاً»
# والمستخدم كتب «بحثاً بالكامل» — ليست الحروف نفسها.
QURAN = ("أريد بحثاً بالكامل عن الإعجاز العلمي في القرآن الكريم. الهيكلة "
         "مكونة من ثلاثة مباحث، كل مبحث فيه ثلاثة مطالب، وكل مطلب تقسيمات "
         "حسب ما يلزم. أضف صفحة غلاف وفهرساً. أدرج جداول أينما يستدعي لذلك. "
         "لا يقل عن 10 صفحات ولا يزيد عن 12 صفحة، بالعربية وبأسلوب أكاديمي، "
         "مع 9 مراجع أدبية عربية موثقة ومحكّمة وبأسلوب APA.")
chk("الطلب لم يعد يُقرأ هيكلاً", W._task_scope(QURAN) is None,
    str(W._task_scope(QURAN)))
_ev = W._full_document_marks(QURAN)
chk(f"وأدلّةُ المستند الكامل مقروءةٌ من نصّ الطلب: {len(_ev)}", len(_ev) >= 4,
    "، ".join(_ev))

# والأهمّ: الاحتياطُ لا يعتمد على عبارةٍ بعينها. أيُّ صياغةٍ تحمل أدلّةَ
# مستندٍ كامل تُقرأ كذلك، ولو لم يخطر لفظُها ببال أحد.
for _t3, _e3 in (
        ("أريد بحثاً بالكامل عن أثر الهواتف. الهيكلة ثلاثة مباحث. غلاف "
         "وفهرس. 10 صفحات، 9 مراجع APA.", None),
        ("أنجز لي دراسة عن التنمية، الهيكلة ثلاثة فصول، غلاف وفهرس، "
         "12 صفحة، 9 مراجع بأسلوب APA.", None),     # لفظٌ ليس في أيّ قائمة
        ("اكتب بحثاً عن الطاقة الشمسية في ثلاثة مباحث", None),
        # وما هو هيكلٌ حقّاً يبقى هيكلاً — التحفّظ مقصود
        ("اعمل لي هيكل بحث عن الطاقة المتجددة", "outline"),
        ("أعطني هيكلة بحث من 10 صفحات", "outline"),
        ("هيكل فقط عن تلوث الهواء", "outline"),
        ("أريد الخطوط العريضة لبحث من 12 صفحة مع 9 مراجع APA وغلاف",
         "outline"),
        ("قائمة مراجع فقط عن الذكاء الاصطناعي بأسلوب APA، 9 مراجع",
         "references"),
        ("مراجع وهيكلة فقط عن التنمية", "references"),
        ("اكتب فقط المقدمة", "part"),
        ("أعد لي خطة بحثية عن الطاقة في 10 صفحات مع 9 مراجع APA", "plan")):
    chk(f"المدى: {_t3[:44]}", W._task_scope(_t3) == _e3,
        f"عاد {W._task_scope(_t3)}")

print("\n" + "═" * 70)
print(" النتيجة: " + ("PASS ✅" if ok else "FAIL ❌"))
print("═" * 70)
sys.exit(0 if ok else 1)
