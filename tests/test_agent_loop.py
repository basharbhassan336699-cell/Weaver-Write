# -*- coding: utf-8 -*-
"""حلقةُ الوكيل: منقولةٌ من برمجة أوبن كلاو، ومُثبَتةٌ بندٍ بندا.

    openclaw/dist/agent-core-B_87jlHI.mjs:541          الحلقة
    openclaw/dist/agent-core-B_87jlHI.mjs:612          شرطُ الدوران
    openclaw/dist/agent-core-B_87jlHI.mjs:711/770      تنفيذُ النداءات
    openclaw/dist/tool-loop-detection-CJSZExqJ.mjs:501 كشفُ الدوران
    openclaw/dist/tool-loop-detection-CJSZExqJ.mjs:215 CRITICAL_THRESHOLD = 20
    openclaw/dist/tool-loop-detection-CJSZExqJ.mjs:216 GLOBAL_...         = 30"""
import sys, os, json
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
for k in list(os.environ):
    if k.startswith("WEAVER_"):
        os.environ.pop(k)
from pipeline import agent_loop as AL
ok = True


def chk(label, good, detail=""):
    global ok
    ok &= bool(good)
    print(f"   {'✅' if good else '❌'} {label}" + (f" — {detail}" if detail else ""))


print("═" * 70)
print(" ١) العتباتُ بأرقامها كما هي في أوبن كلاو")
print("═" * 70)
chk("CRITICAL_THRESHOLD = 20", AL.CRITICAL_THRESHOLD == 20)
chk("GLOBAL_CIRCUIT_BREAKER_THRESHOLD = 30",
    AL.GLOBAL_CIRCUIT_BREAKER_THRESHOLD == 30)
chk("WARNING_THRESHOLD = 10", AL.WARNING_THRESHOLD == 10)

print("\n" + "═" * 70)
print(" ٢) الحلقةُ تدور ما دام النموذجُ يطلب أداة — لا عدّادَ خطوات")
print("═" * 70)
calls = []
T = AL.Tool("search", "ابحث", {"type": "object", "properties": {}},
            lambda a: calls.append(a.get("q")) or f"نتيجة {len(calls)}")


class Script:
    """نموذجٌ يطلب ثلاثَ مرّاتٍ ثمّ يقف — الحلقةُ يجب أن تتبعه لا تسبقه."""

    def __init__(self, plan):
        self.plan, self.i = plan, 0

    def __call__(self, prompt, **kw):
        self.i += 1
        self.last = prompt
        return self.plan[min(self.i - 1, len(self.plan) - 1)]


m = Script([json.dumps({"tool_calls": [{"name": "search", "arguments": {"q": "أ"}}]}),
            json.dumps({"tool_calls": [{"name": "search", "arguments": {"q": "ب"}}]}),
            json.dumps({"tool_calls": [{"name": "search", "arguments": {"q": "ج"}}]}),
            json.dumps({"done": True, "answer": "تسعةُ مراجع"})])
r = AL.run_agent(m, "جِد ٩ مراجع", [T], lang="ar")
chk(f"دارت {r['steps']} خطواتٍ لأن النموذجَ طلب ثلاثاً", r["steps"] == 4)
chk(f"ونُفِّذت الأدواتُ الثلاث: {calls}", calls == ["أ", "ب", "ج"])
chk("ووقفت حين قال هو انتهيت", r["stopped_by"] == "model")
chk("وعادت بجوابه", r["answer"] == "تسعةُ مراجع")
chk("والنموذجُ رأى كتالوجَ الأدوات", "search: ابحث" in m.last)
chk("ورأى نتائجَ ما نفّذ", "نتيجة 1" in m.last)

print("\n" + "═" * 70)
print(" ٣) وعدّةُ أدواتٍ في نداءٍ واحدٍ تُنفَّذ معاً (executeToolCallGroups)")
print("═" * 70)
seen = []
A = AL.Tool("a", "أ", None, lambda x: seen.append("a") or "A")
B = AL.Tool("b", "ب", None, lambda x: seen.append("b") or "B")
m2 = Script([json.dumps({"tool_calls": [{"name": "a", "arguments": {}},
                                        {"name": "b", "arguments": {}}]}),
             json.dumps({"done": True, "answer": "ok"})])
r2 = AL.run_agent(m2, "مهمّة", [A, B])
chk("نُفِّذتا كلتاهما في خطوةٍ واحدة", sorted(seen) == ["a", "b"] and r2["steps"] == 2)
chk("ونتيجتاهما عادتا إليه",
    sum(1 for x in r2["messages"] if x.get("role") == "tool") == 2)

print("\n" + "═" * 70)
print(" ٤) وحارسُ الدوران — بالعتبات نفسِها")
print("═" * 70)
st = {"tool_call_history": []}
h = AL.hash_tool_call("x", {"q": 1})
for i in range(9):
    st["tool_call_history"].append({"name": "x", "args_hash": h,
                                    "result_hash": "same", "unknown": False})
chk("٩ مرّاتٍ بلا تقدّم ⟶ لا شيء بعد",
    AL.detect_tool_call_loop(st, "x", {"q": 1})["stuck"] is False)
st["tool_call_history"].append({"name": "x", "args_hash": h,
                                "result_hash": "same", "unknown": False})
v = AL.detect_tool_call_loop(st, "x", {"q": 1})
chk("و١٠ ⟶ تحذير", v["stuck"] and v["level"] == "warning", str(v.get("count")))
for i in range(10):
    st["tool_call_history"].append({"name": "x", "args_hash": h,
                                    "result_hash": "same", "unknown": False})
v = AL.detect_tool_call_loop(st, "x", {"q": 1})
chk("و٢٠ ⟶ حرِج", v["level"] == "critical" and v["count"] >= 20)
chk("ونتيجةٌ مختلفةٌ تقطع السلسلة (تقدّمٌ لا دوران)",
    AL.get_no_progress_streak(
        st["tool_call_history"] + [{"name": "x", "args_hash": h,
                                    "result_hash": "OTHER"}],
        "x", h)["count"] == 1)

print("\n" + "═" * 70)
print(" ٥) والحارسُ يوقف الحلقةَ فعلاً — لا يُسجَّل فقط")
print("═" * 70)
n = {"i": 0}
L = AL.Tool("loop", "ل", None, lambda a: "ثابت")
m3 = Script([json.dumps({"tool_calls": [{"name": "loop", "arguments": {}}]})])
r3 = AL.run_agent(m3, "مهمّة", [L], max_steps=40)
chk(f"نموذجٌ لا يتوقّف ⟶ أوقفه الحارس بعد {r3['steps']} خطوة",
    r3["stopped_by"] == "loop_guard" and r3["steps"] < 40)
chk("ورسالةُ الإيقاف موجَّهةٌ إلى النموذج",
    any("CRITICAL" in str(x.get("content")) for x in r3["messages"]))

print("\n" + "═" * 70)
print(" ٦) وأداةٌ لا وجودَ لها، وأداةٌ تنهار — تعودان نتيجةً لا انهياراً")
print("═" * 70)
m4 = Script([json.dumps({"tool_calls": [{"name": "غير_موجودة", "arguments": {}}]}),
             json.dumps({"done": True, "answer": "ok"})])
r4 = AL.run_agent(m4, "مهمّة", [A])
chk("أداةٌ مجهولة ⟶ يُقال له وتُسمّى المتاحة",
    any("unknown tool" in str(x.get("content")) and "a" in str(x.get("content"))
        for x in r4["messages"]))
BAD = AL.Tool("bad", "ب", None, lambda x: 1 / 0)
m5 = Script([json.dumps({"tool_calls": [{"name": "bad", "arguments": {}}]}),
             json.dumps({"done": True, "answer": "ok"})])
r5 = AL.run_agent(m5, "مهمّة", [BAD])
chk("وأداةٌ ترفع استثناءً ⟶ الخطأُ يعود إليه",
    any(x.get("is_error") and "ZeroDivision" in str(x.get("content"))
        for x in r5["messages"]) and r5["stopped_by"] == "model")

print("\n" + "═" * 70)
print(" ٧) وتدهورٌ آمنٌ تامّ")
print("═" * 70)
chk("بلا نموذج ⟶ لا دوران", AL.run_agent(None, "م", [A])["stopped_by"] == "no_model")
chk("وبلا أدوات ⟶ لا دوران", AL.run_agent(m, "م", [])["stopped_by"] == "no_tools")


class Broken:
    def __call__(self, p, **k):
        raise ConnectionError("403")


chk("ونموذجٌ يرفض ⟶ توقّفٌ معلَّلٌ لا انهيار",
    AL.run_agent(Broken(), "م", [A])["stopped_by"].startswith("model_error"))
chk("وردٌّ غيرُ صالح ⟶ توقّف",
    AL.run_agent(Script(["ليس JSON"]), "م", [A])["stopped_by"] == "no_tool_call")
chk("وسقفٌ مطلقٌ موجود", AL.MAX_STEPS >= 8)

print("\n" + "═" * 70)
print(" ٨) والأدواتُ عامّةٌ — لا واحدةَ تعرف «المراجع العربية»")
print("═" * 70)
from pipeline import agent_tools as AT
from pipeline.orchestrator import WeaverOrchestrator as W
o = W.__new__(W)
tools = AT.reference_tools(o)
names = [t.name for t in tools]
chk(f"الأدوات: {names}", "web_fetch" in names and "scholarly_api" in names)
chk("ولا أداةَ اسمُها «ابحث عن مراجع عربية»",
    all("arabic" not in t.name.lower() and "عرب" not in t.description
        for t in tools))
_t = AT.reference_task("الإعجاز العلمي", "ar", 9, "ar")
chk("والمهمّةُ تقول ما المطلوب لا كيف يُفعل",
    "9" in _t and "افتح صفحةَ" in _t and "scholar.google" not in _t)
chk("وتنهاه عن الاختراع", "لا تخترع" in _t)

print("\n" + "═" * 70)
print(" النتيجة: " + ("PASS ✅" if ok else "FAIL ❌"))
print("═" * 70)
sys.exit(0 if ok else 1)
