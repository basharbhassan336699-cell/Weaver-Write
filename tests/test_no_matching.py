# -*- coding: utf-8 -*-
"""الكواشفُ الثمانية صارت احتياطاً صامتاً — النموذج يقرأ الطلب ويقرّر.

سبعةُ مواضعَ كانت تحكم مباشرةً: `if <عبارة في النصّ>` فتُضبط الخيارُ خارج أيّ
أسبقية، قبل أن يقول النموذجُ شيئاً. فصياغةٌ لم تخطر ببال كاتب القائمة لم تكن
موجودةً أصلاً — وهذا هو الشهرُ كلُّه في جملة.

وحزمةُ openclaw لا تحمل مصنّفَ نيّةٍ واحداً: كتالوجٌ يُطبع، والنموذجُ يقرأ
المعنى. هذه الاختبارات تثبت أن الأسبقية صارت هكذا هنا، وأن الاحتياطيّ يعمل
حين يصمت النموذجُ أو يتعذّر — لا فوقه."""
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
print(" ١) لا كاشفَ يحكم — كلُّها تحت النموذج أو داخل احتياطٍ صريح")
print("═" * 70)
_src = inspect.getsource(W)
_names = ("_task_action", "_task_scopes", "_wants_table", "_wants_chart",
          "_wants_toc", "_is_recency_query", "_sourcing_mode",
          "_requested_citation_style")
_lines = _src.split("\n")
for f in _names:
    bad = []
    for i, ln in enumerate(_lines):
        if f"self.{f}(" not in ln and f"cls.{f}(" not in ln:
            continue
        ctx = " ".join(_lines[max(0, i - 6):i + 2])
        # سياقاتٌ تعني أن النداء احتياطيٌّ لا حاكم: داخل _settle كقيمةِ
        # fallback، أو بعد سؤال النموذج (_opt.get / _det)، أو في فرع else،
        # أو داخل _recency_now التي تقرأ البطاقةَ أولاً (recency_intent).
        if any(w in ctx for w in ("_settle", "_opt.get", "_det(", "else:",
                                  "_recency_now", "recency_intent")):
            continue
        bad.append(i + 1)
    chk(f"{f}", not bad, f"مواضعُ حكمٍ مباشر: {bad}" if bad else "احتياطيّ فقط")

print("\n" + "═" * 70)
print(" ٢) كتالوجُ الخيارات يُطبع للنموذج")
print("═" * 70)
_keys = {n for n, _ in W._OPTIONS}
chk(f"فيه الخيارات السبعة: {len(W._OPTIONS)}", len(W._OPTIONS) == 7)
for want in ("scope", "want_chart", "want_data", "cover", "toc", "recency",
             "citation_style"):
    chk(f"  {want}", want in _keys)
chk("ولكلٍّ وصفٌ يقرأه النموذج",
    all(d and len(d) > 10 for _, d in W._OPTIONS))


class _Model:
    """نموذجٌ يفهم المعنى ويعيد رأيه في الخيارات."""

    def __init__(self, answer):
        self.answer = answer
        self.saw_request = ""
        self.saw_catalogue = False
        self.calls = 0

    def __call__(self, prompt, **kw):
        self.calls += 1
        self.saw_request = prompt
        self.saw_catalogue = "citation_style" in prompt and "scope" in prompt
        return json.dumps(self.answer, ensure_ascii=False)


print("\n" + "═" * 70)
print(" ٣) صياغةٌ لا تحويها أيُّ قائمة — النموذج يفهمها")
print("═" * 70)
# «ورقة علمية … وحطّ لي صفحة عناوين» — لا «بحث» ولا «فهرس» ولا «جدول محتويات»
ODD = "أبغى ورقة علمية عن أثر النوم، وحطّ لي صفحة عناوين في أولها"
chk("الكاشفُ النصّيُّ لا يرى فهرساً", not W._wants_toc(ODD))
o = W.__new__(W)
o.llm_fn = _Model({"toc": True, "scope": None})
o.system_main = None
res = o._decide_options(ODD, "ar")
chk("والنموذجُ رأى الطلب حرفياً", ODD[:20] in o.llm_fn.saw_request)
chk("ورأى الكتالوج", o.llm_fn.saw_catalogue)
chk("وأجاب: فهرسٌ مطلوب", res.get("toc") is True, str(res))

print("\n" + "═" * 70)
print(" ٤) والنتيجة تُقرأ ثلاثيّةً: نعم / لا / بلا رأي")
print("═" * 70)
for v, want in ((True, True), (False, False), ("true", True), ("لا", False),
                ("نعم", True), (None, None), ("ربما", None), (0, None)):
    chk(f"  {v!r} ⟶ {want!r}", W._tri_opt(v) is want)

print("\n" + "═" * 70)
print(" ٥) والاحتياطيُّ يعمل حين يصمت النموذج أو يتعذّر")
print("═" * 70)
o2 = W.__new__(W)
o2.llm_fn = None
o2.system_main = None
chk("بلا نموذج ⟶ لا رأي، فيتولّى الكاشف", o2._decide_options(ODD, "ar") == {})


class _Broken:
    def __call__(self, prompt, **kw):
        raise ConnectionError("403")


o3 = W.__new__(W)
o3.llm_fn = _Broken()
o3.system_main = None
chk("ونموذجٌ يرفض بـ403 ⟶ {} لا انهيار", o3._decide_options(ODD, "ar") == {})


class _Garbage:
    def __call__(self, prompt, **kw):
        return "ليس JSON"


o4 = W.__new__(W)
o4.llm_fn = _Garbage()
o4.system_main = None
chk("وردٌّ غيرُ صالح ⟶ {}", o4._decide_options(ODD, "ar") == {})


class _Invents:
    def __call__(self, prompt, **kw):
        return json.dumps({"خيار_مخترَع": True, "toc": True})


o5 = W.__new__(W)
o5.llm_fn = _Invents()
o5.system_main = None
_r5 = o5._decide_options(ODD, "ar")
chk("ومفتاحٌ مخترَعٌ يُرفض", "خيار_مخترَع" not in _r5 and _r5.get("toc") is True)

o6 = W.__new__(W)
o6.llm_fn = _Model({"toc": True})
o6.system_main = None
o6._decide_options(ODD, "ar")
o6._decide_options(ODD, "ar")
chk("ولا يُنادى النموذج مرّتين لنفس الطلب (تخزين)", o6.llm_fn.calls == 1)

print("\n" + "═" * 70)
print(" ٦) وقرارُ الحداثة يُقرأ من البطاقة لا يُعاد كشفُه")
print("═" * 70)
chk("البطاقة تقول False ⟶ False مهما قال النصّ",
    W._recency_now({"recency_intent": False}, "آخر الأخبار 2026 أحدث") is False)
chk("والبطاقة تقول True ⟶ True", W._recency_now({"recency_intent": True}, "") is True)
chk("وصامتةٌ ⟶ الكاشف يتولّى",
    W._recency_now({}, "ما آخر التطورات في 2026؟") ==
    bool(W._is_recency_query("ما آخر التطورات في 2026؟")))

print("\n" + "═" * 70)
print(" النتيجة: " + ("PASS ✅" if ok else "FAIL ❌"))
print("═" * 70)
sys.exit(0 if ok else 1)
