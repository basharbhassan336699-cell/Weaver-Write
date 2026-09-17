# -*- coding: utf-8 -*-
"""الوكيلُ العامّ: أيُّ سؤالٍ بأيّ صياغة — لا طبقات ولا تصنيفَ نيّة.

العُدّةُ منقولةٌ بأسمائها من سجلّ أوبن كلاو الرسميّ:
    openclaw/dist/core-tool-factory-descriptors-DvHWmRcY.mjs
        [base-coding]  read، write، edit، ls
        [shell]        exec، apply_patch، process
        [openclaw]     web_search، web_fetch … (والباقي خاصٌّ بمنصّته)

ولا أداةَ اسمُها «ابحث عن مراجع» ولا «اكتب بحثاً». النموذجُ يُركِّب."""
import sys, os, json, tempfile, shutil
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
for k in list(os.environ):
    if k.startswith("WEAVER_"):
        os.environ.pop(k)
from pipeline import agent as AG, agent_tools as AT
ok = True


def chk(label, good, detail=""):
    global ok
    ok &= bool(good)
    print(f"   {'✅' if good else '❌'} {label}" + (f" — {detail}" if detail else ""))


T = {t.name: t for t in AT.core_tools(None)}
tmp = tempfile.mkdtemp()

print("═" * 70)
print(" ١) العُدّةُ هي عُدّةُ أوبن كلاو الأساسية")
print("═" * 70)
for n in ("read", "write", "edit", "ls", "exec", "web_fetch", "web_search"):
    chk(f"{n}", n in T)
chk("ولكلٍّ وصفٌ ومخطَّطُ معاملات",
    all(t.description and t.parameters.get("properties") for t in T.values()))
chk("والكاتبةُ متسلسلةٌ لا متوازية (executionMode)",
    all(T[n].execution_mode == "sequential" for n in ("write", "edit", "exec")))
chk("والقارئةُ متوازية",
    all(T[n].execution_mode == "parallel" for n in ("read", "ls", "web_fetch")))
chk("ولا أداةَ تخصُّ بحثاً ولا أدباً ولا أكاديميا",
    not any(w in t.name for t in T.values()
            for w in ("research", "essay", "outline", "reference")))

print("\n" + "═" * 70)
print(" ٢) والأدواتُ تعمل فعلاً على القرص")
print("═" * 70)
p = os.path.join(tmp, "a", "note.txt")
chk("write يكتب ويُنشئ المجلّد",
    "wrote" in T["write"].execute({"path": p, "content": "سطر١\nسطر٢\n"})
    and os.path.isfile(p))
out = T["read"].execute({"path": p})
chk("read يقرأ مرقّماً", "1\tسطر١" in out and "2\tسطر٢" in out, out[:30])
chk("edit يستبدل حرفياً",
    "replaced 1" in T["edit"].execute(
        {"path": p, "old_string": "سطر٢", "new_string": "سطر٣"})
    and "سطر٣" in open(p, encoding="utf-8").read())
chk("ls يسرد", "file note.txt" in T["ls"].execute({"path": os.path.dirname(p)}))

print("\n" + "═" * 70)
print(" ٣) وكلُّ خطأٍ يعود نصّاً إلى النموذج — لا انهيار")
print("═" * 70)
chk("ملفٌّ غيرُ موجود", T["read"].execute({"path": "/nope/x"}).startswith("error:"))
chk("مجلّدٌ غيرُ موجود", T["ls"].execute({"path": "/nope"}).startswith("error:"))
chk("نصٌّ غيرُ موجودٍ في edit",
    "not found" in T["edit"].execute(
        {"path": p, "old_string": "لا وجود له", "new_string": "x"}))
T["write"].execute({"path": p, "content": "س\nس\n"})
chk("ونصٌّ متكرّرٌ يُرفض حتى يُصرَّح",
    "2 times" in T["edit"].execute(
        {"path": p, "old_string": "س", "new_string": "ص"}))
chk("ويُقبل بـreplace_all",
    "replaced 2" in T["edit"].execute(
        {"path": p, "old_string": "س", "new_string": "ص",
         "replace_all": True}))
chk("ورابطٌ غيرُ صالح", T["web_fetch"].execute({"url": "ftp://x"}).startswith("error:"))
chk("و exec مطفأةٌ ما لم يُؤذَن",
    "WEAVER_EXEC=1" in T["exec"].execute({"command": "echo hi"}))
os.environ["WEAVER_EXEC"] = "1"
_r = AT.make_exec().execute({"command": "echo مرحبا"})
chk("وتعمل حين يُؤذَن", "مرحبا" in _r and "exit=0" in _r, _r[:40])
os.environ.pop("WEAVER_EXEC")

print("\n" + "═" * 70)
print(" ٤) والوضعُ الآمن: قراءةٌ فقط")
print("═" * 70)
os.environ["WEAVER_AGENT_RO"] = "1"
_, ro_tools, _sys = AG.build(llm_fn=lambda *a, **k: "")
_names = [t.name for t in ro_tools]
chk("بلا write ولا edit", "write" not in _names and "edit" not in _names)
chk("والقراءةُ باقية", "read" in _names and "web_fetch" in _names)
os.environ.pop("WEAVER_AGENT_RO")

print("\n" + "═" * 70)
print(" ٥) والنموذجُ يقرّر: يجيب مباشرةً، أو يستعمل أداة")
print("═" * 70)


class Fake:
    def __init__(self, plan):
        self.plan, self.i, self.last = plan, 0, ""

    def __call__(self, prompt, **kw):
        self.i += 1
        self.last = prompt
        return self.plan[min(self.i - 1, len(self.plan) - 1)]


f = Fake([json.dumps({"done": True, "answer": "٤٫٥٤ مليار سنة"},
                     ensure_ascii=False)])
r = AG.ask("كم عمر الأرض؟", llm_fn=f)
chk("سؤالُ معرفةٍ ⟶ بلا أداةٍ إطلاقاً",
    r["steps"] == 1 and not [m for m in r["messages"] if m.get("role") == "tool"])
chk("والجوابُ جوابُه", r["answer"] == "٤٫٥٤ مليار سنة")

f2 = Fake([json.dumps({"tool_calls": [{"name": "ls", "arguments": {"path": tmp}}]}),
           json.dumps({"done": True, "answer": "فيه مجلّد a"}, ensure_ascii=False)])
r2 = AG.ask("وش فيه بالمجلد " + tmp, llm_fn=f2)
chk("وطلبٌ يحتاج الواقعَ ⟶ استعمل الأداة",
    [m["name"] for m in r2["messages"] if m.get("role") == "tool"] == ["ls"])
chk("ونتيجةُ الأداة عادت إليه قبل أن يجيب", "dir  a" in f2.last)

print("\n" + "═" * 70)
print(" ٦) ولا تصنيفَ نيّةٍ في الكود — الصياغةُ لا تُغيّر المسار")
print("═" * 70)
import inspect
_src = inspect.getsource(AG) + inspect.getsource(AT)
chk("لا قائمةَ عباراتٍ تُطابَق بنصّ المستخدم",
    "بحث" not in _src.replace("ابحث في", "").replace("بحثٌ", "")
    or "if " not in _src.split("SYSTEM_AR")[0])
_langs = [q for q in ("كم عمر الأرض؟", "اكتب لي كود", "ترجم هذا",
                      "شوف لي وش في الملف", "احسب ٢+٢")]
_paths = set()
for q in _langs:
    fq = Fake([json.dumps({"done": True, "answer": "x"})])
    rq = AG.ask(q, llm_fn=fq)
    _paths.add(rq["stopped_by"])
chk(f"خمسُ صياغاتٍ مختلفةٍ تماماً ⟶ مسارٌ واحد: {_paths}", _paths == {"model"})
chk("واللغةُ تُقاس من السؤال لا تُفترض",
    AG._is_ar("كم عمر الأرض") and not AG._is_ar("how old is earth"))

print("\n" + "═" * 70)
print(" ٧) وتدهورٌ آمن")
print("═" * 70)
chk("بلا نموذج ⟶ يُقال ولا ينهار",
    AG.ask("س", llm_fn=False)["stopped_by"] == "no_model")


class Broken:
    def __call__(self, p, **k):
        raise ConnectionError("403")


chk("ونموذجٌ يرفض ⟶ توقّفٌ معلَّل",
    AG.ask("س", llm_fn=Broken())["stopped_by"].startswith("model_error"))
chk("والمُنسِّقُ اختياريّ — تعمل الأدواتُ بدونه",
    len(AT.core_tools(None)) >= 7)

shutil.rmtree(tmp, ignore_errors=True)
print("\n" + "═" * 70)
print(" النتيجة: " + ("PASS ✅" if ok else "FAIL ❌"))
print("═" * 70)
sys.exit(0 if ok else 1)
