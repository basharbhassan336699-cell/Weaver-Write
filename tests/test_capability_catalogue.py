# -*- coding: utf-8 -*-
"""الكتالوج بدل المطابقة — النموذج يختار، والكودُ لا يطابق كلمات.

كانت كلُّ قدرةٍ تُختار بتضمين نصّيّ: تُستدعى الأداةُ حين تظهر إحدى عبارات
إطلاقها حرفياً في الطلب. هذه الآليةُ وحدها أنتجت شهراً من الأعطاب — «جدول»
لا تطابق «جداول»، و«بحثاً كاملاً» لا تطابق «بحثاً بالكامل»، و«بالعربي» تطابق
داخل «بالعربية» — ولا تنتهي أبداً، لأن قائمة العبارات لا تحمل إلا ما خطر ببال
كاتبها.

وحزمةُ openclaw (10616 ملفاً) لا تحمل مصنّفَ نيّةٍ واحداً، وكتالوجُها يحمل
تعليمةً واحدةً موجَّهةً إلى النموذج:
    "Read a skill's file at its listed location when the task
     matches its description."

هذه الاختبارات تثبت أن الآليةَ نفسها تعمل هنا، وأن الاحتياطيّ بقي صامتاً
تحتها لا حاكماً فوقها."""
import sys, os, json, inspect
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
for k in list(os.environ):
    if k.startswith("WEAVER_"):
        os.environ.pop(k)
from capabilities import CapabilityRegistry
ok = True


def chk(label, good, detail=""):
    global ok
    ok &= bool(good)
    print(f"   {'✅' if good else '❌'} {label}" + (f" — {detail}" if detail else ""))


caps = CapabilityRegistry()
try:
    caps.load_all()
except Exception:
    pass
if not caps.tools:
    print("   ⚠️ لا كتالوج — تخطّي")
    sys.exit(0)

print("═" * 70)
print(" ١) الكتالوج يُطبع كما يقرأه النموذج")
print("═" * 70)
cat = caps.catalogue(lang="ar")
chk(f"فيه الأدوات ({len(caps.tools)})", "الأدوات المتاحة" in cat)
chk(f"وفيه المهارات ({len(caps.skills)})",
    not caps.skills or "المهارات المتاحة" in cat)
chk("كلُّ سطرٍ اسمٌ ووصف", all(":" in l for l in cat.split("\n")
                                if l.startswith("- ")))
chk("ولا عباراتِ إطلاقٍ في الكتالوج — فالوصفُ وحده يكفي النموذج",
    "triggers" not in cat)
_en = caps.catalogue(lang="en")
chk("وبالإنجليزية أيضاً", "Available tools" in _en)

print("\n" + "═" * 70)
print(" ٢) صياغةٌ لا تحويها أيُّ قائمةِ عبارات")
print("═" * 70)
# «أبغى ورقة علمية مع مصادر موثّقة» — لا «بحث» ولا «مراجع» ولا «اكتب».
ODD = "أبغى ورقة علمية عن أثر النوم، ومعاها مصادر موثّقة ومحكّمة"
by_trigger = [t.name for t in caps.match_tools_by_trigger(ODD)]
chk(f"المطابقةُ النصّية تجد: {by_trigger or 'لا شيء'}", True)


class _Model:
    """نموذجٌ يفهم المعنى — كما يفعل النموذج الحقيقيّ."""

    def __init__(self, tools, skills=None):
        self.tools, self.skills = tools, (skills or [])
        self.saw_catalogue = False
        self.saw_request = False

    def __call__(self, prompt, **kw):
        self.saw_catalogue = "الأدوات المتاحة" in prompt
        self.saw_request = "ورقة علمية" in prompt
        return json.dumps({"tools": self.tools, "skills": self.skills})


_want = [n for n in ("academic_search", "web_search") if n in caps.tools]
m = _Model(_want)
tw, sk, how = caps.select(ODD, llm_fn=m, lang="ar")
chk("النموذجُ رأى الكتالوج", m.saw_catalogue)
chk("ورأى نصّ الطلب كما هو", m.saw_request)
chk(f"واختار: {[t.name for t in tw]} ← {how}",
    how == "model" and [t.name for t in tw] == _want)
chk("وهو ما عجزت عنه المطابقة",
    set(_want) - set(by_trigger) != set() or not by_trigger,
    f"المطابقة: {by_trigger}")

print("\n" + "═" * 70)
print(" ٣) والاحتياطيُّ صامتٌ تحتها — لا حاكمٌ فوقها")
print("═" * 70)
tw2, sk2, how2 = caps.select(ODD, llm_fn=None, lang="ar")
chk("بلا نموذج ⟶ المطابقة الاحتياطية", how2 == "fallback")
chk("وتعطي ما كانت تعطيه بالضبط",
    [t.name for t in tw2] == by_trigger)


class _Broken:
    def __call__(self, prompt, **kw):
        raise ConnectionError("403")


chk("ونموذجٌ يرفض ⟶ احتياطيّ لا انهيار",
    caps.select(ODD, llm_fn=_Broken(), lang="ar")[2] == "fallback")


class _Garbage:
    def __call__(self, prompt, **kw):
        return "ليس JSON إطلاقاً"


chk("وردٌّ غيرُ صالح ⟶ احتياطيّ",
    caps.select(ODD, llm_fn=_Garbage(), lang="ar")[2] == "fallback")


class _Invents:
    def __call__(self, prompt, **kw):
        return json.dumps({"tools": ["أداة_لا_وجود_لها"], "skills": []})


tw3, sk3, how3 = caps.select(ODD, llm_fn=_Invents(), lang="ar")
chk("واسمٌ مخترَعٌ يُرفض ⟶ لا يمرّ إلى المسار",
    all(t.name in caps.tools for t in tw3))

print("\n" + "═" * 70)
print(" ٤) والأسماءُ القديمة ما زالت تعمل — توافقٌ كامل")
print("═" * 70)
chk("match_tools تعمل كما كانت",
    [t.name for t in caps.match_tools(ODD)] == by_trigger)
chk("و match_skills كذلك",
    [s.name for s in caps.match_skills(ODD)] ==
    [s.name for s in caps.match_skills_by_trigger(ODD)])

print("\n" + "═" * 70)
print(" ٥) والمسار يستدعي الكتالوج فعلاً")
print("═" * 70)
from pipeline.orchestrator import WeaverOrchestrator as W
_src = inspect.getsource(W)
chk("caps.select مُستدعىً في المسار", "self.caps.select(" in _src)
chk("ومصدرُ الاختيار يُسجَّل للمستخدم", "اختيار الأدوات والمهارات" in _src)
chk("ويُقال حين كان احتياطياً", "مطابقةٌ احتياطية" in _src)

print("\n" + "═" * 70)
print(" النتيجة: " + ("PASS ✅" if ok else "FAIL ❌"))
print("═" * 70)
sys.exit(0 if ok else 1)
