# -*- coding: utf-8 -*-
"""لا جدولَ يكبر إلى الأبد: أيّ وسيطٍ يعمل من أول نداء."""
import sys, os, json, io, tempfile, urllib.error
sys.path.insert(0, "/home/user/Weaver-Write")
for k in list(os.environ):
    if k.startswith("WEAVER_"): os.environ.pop(k)
import core.llm as L
ok = True

print("═" * 66)
print(" ١) الجدول صار بياناً: إضافة وسيطٍ بلا سطر كود")
print("═" * 66)
conf = {"routers": [{"name": "together", "match": ["together"],
                     "off": {"reasoning_effort": "none"}, "on": {}}],
        "families": [{"name": "qwen", "match": ["qwen", "qwq"],
                      "off": {"enable_thinking": False},
                      "on": {"enable_thinking": True}}]}
fp = os.path.join(tempfile.mkdtemp(), "reasoning.json")
io.open(fp, "w", encoding="utf-8").write(json.dumps(conf, ensure_ascii=False))
os.environ["WEAVER_REASONING_CONF"] = fp
L.load_reasoning_config(True)
for nm, b, m in [("together + qwen", "https://api.together.xyz/v1", "Qwen/Qwen3-72B"),
                 ("أوبن روتر (مدمج)", "https://openrouter.ai/api/v1", "deepseek/x"),
                 ("أنثروبيك", "https://api.anthropic.com/v1", "claude-opus-5")]:
    print(f"  {nm:20s} ⟶ {L.reasoning_payload('', b, m)}")
r = L.reasoning_payload("", "https://api.together.xyz/v1", "Qwen/Qwen3-72B")
good = (r.get("reasoning_effort") == "none" and r.get("enable_thinking") is False)
ok &= good
print(f"  ⟵ وسيطٌ وعائلةٌ جديدان من ملفٍ فقط: {'✅' if good else '❌'}")
os.environ.pop("WEAVER_REASONING_CONF"); L.load_reasoning_config(True)

print("\n" + "═" * 66)
print(" ٢) ملفٌّ خاطئ أو محذوف لا يكسر شيئاً")
print("═" * 66)
for nm, txt in [("JSON مشوّه", "{ليس json"), ("ليس كائناً", "[1,2]"),
                ("صفٌّ بلا match", '{"routers":[{"name":"x"}]}')]:
    fp2 = os.path.join(tempfile.mkdtemp(), "r.json")
    io.open(fp2, "w", encoding="utf-8").write(txt)
    os.environ["WEAVER_REASONING_CONF"] = fp2
    L.load_reasoning_config(True)
    r = L.reasoning_payload("", "https://openrouter.ai/api/v1", "deepseek/x")
    g = ("reasoning" in r)
    ok &= g
    print(f"  {nm:16s} ⟶ المدمج قائم {'✅' if g else '❌'}")
    os.environ.pop("WEAVER_REASONING_CONF")
os.environ["WEAVER_REASONING_CONF"] = "/nowhere/nope.json"
L.load_reasoning_config(True)
ok &= ("reasoning" in L.reasoning_payload("", "https://openrouter.ai/api/v1", "d"))
print(f"  {'ملفٌ غير موجود':16s} ⟶ المدمج قائم ✅")
os.environ.pop("WEAVER_REASONING_CONF"); L.load_reasoning_config(True)

print("\n" + "═" * 66)
print(" ٣) التعافي الذاتي: وسيطٌ مجهولٌ يرفض الحقول")
print("═" * 66)
os.environ["WEAVER_API_KEY"] = "k"
os.environ["WEAVER_BASE_URL"] = "https://gateway.unknown-vendor.test/v1"
os.environ["WEAVER_MODEL"] = "deepseek-v9"
import urllib.request
seen = []
class _Resp:
    def __init__(s, d): s._d = json.dumps(d).encode()
    def read(s): return s._d
    def __enter__(s): return s
    def __exit__(s, *a): return False
def fake_urlopen(req, timeout=None):
    body = json.loads(req.data.decode())
    seen.append(sorted(k for k in body if k in ("reasoning", "thinking")))
    if any(k in body for k in ("reasoning", "thinking")):
        raise urllib.error.HTTPError(req.full_url, 400, "Unknown parameter",
                                     {}, io.BytesIO(b'{"error":"unknown param"}'))
    return _Resp({"choices": [{"message": {"content": "تمام"}}]})
urllib.request.urlopen = fake_urlopen
L.keysync.load_env = lambda *a, **k: None
f = L.get_llm_fn()
out = f("اختبار")
print(f"  النداء ١ — ما أُرسل في كل محاولة: {seen}")
print(f"  الجواب: {out!r}")
g = (out == "تمام" and seen[0] and not seen[-1])
ok &= g
print(f"  ⟵ رُفض ⟶ حُذفت الحقول ⟶ نجح من أول نداء: {'✅' if g else '❌'}")
seen.clear()
out2 = f("اختبارٌ ثانٍ")
g2 = (out2 == "تمام" and seen == [[]])
ok &= g2
print(f"  النداء ٢ — ما أُرسل: {seen}  ⟵ لم تُرسَل ثانيةً {'✅' if g2 else '❌'}")

print("\n" + "═" * 66)
print(" ٤) خطأٌ آخر يمرّ كما هو، ولا يُلام على الحقول")
print("═" * 66)
L._REASONING_REFUSED.clear()
def fake_500(req, timeout=None):
    raise urllib.error.HTTPError(req.full_url, 500, "boom", {}, io.BytesIO(b"x"))
urllib.request.urlopen = fake_500
try:
    f("اختبار")
    ok = False; print("  ❌ ابتُلع الخطأ")
except urllib.error.HTTPError as e:
    g3 = (e.code == 500 and not L._REASONING_REFUSED)
    ok &= g3
    print(f"  500 ⟶ يُرفع كما هو، ولا شيء يُحظر: {'✅' if g3 else '❌'}")

print("\n" + ("PASS ✅" if ok else "FAIL ❌"))
sys.exit(0 if ok else 1)
