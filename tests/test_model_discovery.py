# -*- coding: utf-8 -*-
"""استكشافُ النماذج: الأحدثُ أوّلاً، وكلُّها، وسجلُّ منصّاتٍ من أوبن كلاو.

شكوى المستخدم: «لا يطلع معي غير نماذج قديمة». والسبب في الكود:

    config/providers.py   list_models_for  ⟶ sorted(set(models))   أبجدياً
    web/index.html        r.models.slice(0,100)                    أوّلُ ١٠٠

فعلى منصّةٍ فيها مئاتُ النماذج يظهر ما يبدأ بـ«01-ai…» و«ai21…» ويُقصّ الأحدث.
مقيسٌ على خادمٍ وهميٍّ بـ٣٤٣ نموذجاً: الكودُ القديمُ لم يُظهر أيّاً من الأحدث.
"""
import json
import os
import sys
import tempfile
from pathlib import Path

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

from config import providers as P   # noqa: E402

P_ = F = 0


def ok(name, cond, extra=""):
    global P_, F
    if cond:
        P_ += 1
        print(f"  ✓ {name}")
    else:
        F += 1
        print(f"  ✗ {name}" + (f"   — {extra}" if extra else ""))


print("\n— الترتيب: الأحدثُ أوّلاً —")
old = [{"id": f"01-ai/old-{i}", "created": 1600000000 - i} for i in range(300)]
new = [{"id": "z-ai/glm-5.2", "created": 1790000000},
       {"id": "deepseek/deepseek-v4-pro", "created": 1789000000}]
got = P._models_from_response({"data": old + new})
ok("الأحدثُ في الأعلى ولو جاء آخراً وكان اسمُه متأخّراً أبجدياً",
   got[:2] == ["z-ai/glm-5.2", "deepseek/deepseek-v4-pro"], str(got[:3]))
ok("ولا يضيع شيء", len(got) == 302)
got = P._models_from_response({"data": [
    {"id": "a", "created_at": "2024-01-01T00:00:00Z"},
    {"id": "b", "created_at": "2026-06-01T00:00:00Z"}]})
ok("created_at بصيغة ISO (أنثروبيك)", got == ["b", "a"], str(got))
got = P._models_from_response({"data": [
    {"id": "old", "created": 1600000000000}, {"id": "new", "created": 1790000000000}]})
ok("طوابعُ بالميلي‌ثانية", got == ["new", "old"], str(got))
got = P._models_from_response({"data": [{"id": "m3"}, {"id": "m1"}, {"id": "m2"}]})
ok("بلا تواريخ ⟵ ترتيبُ المنصّة كما أرسلته (لا أبجدياً)",
   got == ["m3", "m1", "m2"], str(got))
got = P._models_from_response({"data": [
    {"id": "x", "created": 5}, {"id": "y"}, {"id": "z"}, {"id": "w"}]})
ok("تواريخُ قليلة ⟵ لا يُعاد الترتيب", got == ["x", "y", "z", "w"])
got = P._models_from_response({"data": [
    {"id": "d", "created": 10}, {"id": "e", "created": 10}, {"id": "f"}]})
ok("المتساوي يبقى بترتيب المنصّة، وغيرُ المؤرَّخ آخراً",
   got == ["d", "e", "f"], str(got))
got = P._models_from_response({"data": [{"id": "a"}, {"id": "a"}, {"id": "b"}]})
ok("بلا تكرار", got == ["a", "b"])
ok("قائمةُ نصوص (بعض المنصّات)",
   P._models_from_response(["q", "p"]) == ["q", "p"])
ok("مفتاحُ models بدل data",
   P._models_from_response({"models": [{"name": "g"}]}) == ["g"])
ok("ردٌّ غريب ⟵ قائمةٌ فارغة لا استثناء",
   P._models_from_response({"x": 1}) == [] and P._models_from_response(None) == [])


print("\n— list_models_for: لا sorted(set(...)) —")
def fake_get(url, headers, timeout):
    if url.endswith("/v1/models"):
        return {"data": old + new}, None
    return None, "HTTP 404"
models, err = P.list_models_for("https://example.test/v1", "k", http_get=fake_get)
ok("يعيد الأحدثَ أوّلاً", models[0] == "z-ai/glm-5.2" and err is None,
   str(models[:2]))
ok("وكلَّها — لا حدَّ", len(models) == 302)
res = P.connect_custom_provider("https://example.test/v1", "k", http_get=fake_get,
                                persist=False)
ok("وصلُ منصّةٍ مخصَّصة: الافتراضيُّ أحدثُ نموذج", res["model"] == "z-ai/glm-5.2")
_src = open(os.path.join(_ROOT, "config", "providers.py"), encoding="utf-8").read()
ok("لا ترتيبَ أبجدياً باقٍ", "sorted(set(models))" not in _src)


print("\n— الواجهة: كلُّ النماذج، وبحث —")
_html = open(os.path.join(_ROOT, "web", "index.html"), encoding="utf-8").read()
ok("لا قصَّ عند ١٠٠", "r.models.slice(0,100)" not in _html)
ok("حقلُ بحثٍ فوق القائمة", 'id="kModelFilter"' in _html
   and "function wvFilterModels" in _html)
ok("والعدّاد", 'id="kModelCount"' in _html)
ok("والحفظُ يقرأ من القائمة نفسِها كما كان",
   "document.getElementById('kModel').value" in _html)


print("\n— السجلّ: منصّاتُ أوبن كلاو، إضافةٌ فقط —")
reg = {p["name"]: p for p in P.load_registry()}
_orig = ["openai", "anthropic", "groq", "openrouter", "nvidia", "xai",
         "perplexity", "fireworks", "cerebras", "google", "deepseek",
         "together", "mistral", "aerolink", "ollama"]
ok("الخمسَ عشرةَ الأصليّةُ كلُّها باقية", all(n in reg for n in _orig))
_d = {p["name"]: p for p in P._DEFAULT}
ok("ولم يتغيّر فيها حرف",
   all(reg[n] == _d[n] for n in _orig if not P._USER_REGISTRY.exists()))
ok("والترتيبُ يبدأ بها (افتراضُ القائمة في الواجهة لم يتغيّر)",
   [p["name"] for p in P.load_registry()][:15] == _orig)
_new = [p["name"] for p in P._OPENCLAW]
ok("٣٢ منصّةً جديدة", len(_new) == 32, str(len(_new)))
ok("بلا تكرار أسماء", len(set(_new)) == len(_new)
   and not (set(_new) & set(_orig)))
ok("كلُّها بلا بادئاتِ مفاتيح (لا تخمين)",
   all(p["prefixes"] == [] for p in P._OPENCLAW))
_local = {"lmstudio", "vllm", "sglang", "litellm"}
ok("روابطُ https إلا المحلّية",
   all(p["base_url"].startswith("https://") for p in P._OPENCLAW
       if p["name"] not in _local)
   and all(p["base_url"].startswith("http://") for p in P._OPENCLAW
           if p["name"] in _local))
for n, url in (("deepinfra", "https://api.deepinfra.com/v1/openai"),
               ("zai", "https://api.z.ai/api/paas/v4"),
               ("moonshot", "https://api.moonshot.ai/v1"),
               ("qwen", "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"),
               ("cohere", "https://api.cohere.ai/compatibility/v1"),
               ("huggingface", "https://router.huggingface.co/v1")):
    ok(f"{n}: {url}", reg.get(n, {}).get("base_url") == url)
ok("كشفُ البادئة لم يتغيّر: sk-or- ⟵ openrouter",
   (P.detect_by_prefix("sk-or-v1-x") or {}).get("name") == "openrouter")
ok("  ⟵ gsk_ ⟵ groq", (P.detect_by_prefix("gsk_x") or {}).get("name") == "groq")
ok("  ⟵ مفتاحٌ عامّ ⟵ لا ادّعاء", P.detect_by_prefix("sk-plain") is None)

# ما وثّقه المحرّكُ مطابقٌ حرفاً — إن كان مركَّباً على هذا الجهاز
_docs = Path(_ROOT, "engines", "weaver-core", "runtime", "docs", "providers")
if _docs.is_dir():
    _map = {"arcee": "arcee", "baseten": "baseten", "chutes": "chutes",
            "cohere": "cohere", "deepinfra": "deepinfra",
            "featherless": "featherless", "gmi": "gmi", "longcat": "longcat",
            "meta": "meta", "moonshot": "moonshot", "moonshot-cn": "moonshot",
            "kimi-coding": "moonshot", "novita": "novita",
            "qianfan": "qianfan", "stepfun": "stepfun", "stepfun-cn": "stepfun",
            "tencent-tokenhub": "tencent", "venice": "venice",
            "xiaomi": "xiaomi", "zai": "zai", "zai-cn": "zai",
            "huggingface": "huggingface", "minimax": "minimax",
            "lmstudio": "lmstudio", "vllm": "vllm", "sglang": "sglang",
            "litellm": "litellm"}
    _miss = []
    for n, doc in _map.items():
        u = reg[n]["base_url"]
        txt = (_docs / (doc + ".md")).read_text(encoding="utf-8")
        if u.split("://", 1)[1].rstrip("/") not in txt:
            _miss.append(n)
    ok("كلُّ رابطٍ موجودٌ حرفاً في صفحة توثيقه عند المحرّك", not _miss,
       str(_miss))
else:
    print("  (توثيقُ المحرّك غير مركَّب هنا — تُخطّى المطابقةُ الحرفيّة)")


print("\n— providers.json لا يمحو بادئةً موثّقة —")
_real_user = P._USER_REGISTRY
with tempfile.TemporaryDirectory() as td:
    P._USER_REGISTRY = Path(td) / "providers.json"
    # ما يكتبه `add_provider` حين تصل OpenRouter من الطرفيّة
    P._USER_REGISTRY.write_text(json.dumps({"providers": [
        {"name": "openrouter", "base_url": "https://openrouter.ai/api/v1",
         "model": "deepseek/deepseek-v4-flash", "prefixes": [],
         "auth": "bearer"},
        {"name": "mine", "base_url": "https://x.example/v1", "model": "m",
         "prefixes": [], "auth": "bearer"}]}), encoding="utf-8")
    r2 = {p["name"]: p for p in P.load_registry()}
    ok("sk-or- باقٍ بعد حفظ OpenRouter", r2["openrouter"]["prefixes"] == ["sk-or-"],
       str(r2["openrouter"]["prefixes"]))
    ok("  ⟵ ونموذجُك المحفوظُ يعلو كما كان",
       r2["openrouter"]["model"] == "deepseek/deepseek-v4-flash")
    ok("  ⟵ وكشفُ المفتاح يعمل",
       (P.detect_by_prefix("sk-or-v1-x") or {}).get("name") == "openrouter")
    ok("منصّتُك المخصَّصةُ تُحفَظ كما هي", r2["mine"]["base_url"]
       == "https://x.example/v1" and r2["mine"]["prefixes"] == [])
    P._USER_REGISTRY.write_text(json.dumps({"providers": [
        {"name": "openrouter", "base_url": "https://openrouter.ai/api/v1",
         "prefixes": ["custom-"]}]}), encoding="utf-8")
    ok("بادئةٌ صريحةٌ منك تعلو",
       {p["name"]: p for p in P.load_registry()}["openrouter"]["prefixes"]
       == ["custom-"])
P._USER_REGISTRY = _real_user


print("\n— كلُّها تصل المحرّك (engine_route) —")
try:
    from pipeline import weaver_core as W
    _keys = ("WEAVER_PROVIDER", "WEAVER_BASE_URL", "WEAVER_MODEL",
             "WEAVER_API_KEY")
    _saved = {k: os.environ.get(k) for k in _keys}
    _real_load = W._load_settings
    W._load_settings = lambda: {k: os.environ[k] for k in _keys
                                if os.environ.get(k)}
    _bad = []
    for p in P.load_registry():
        os.environ.update(WEAVER_PROVIDER=p["name"],
                          WEAVER_BASE_URL=p["base_url"],
                          WEAVER_MODEL="some-model", WEAVER_API_KEY="k")
        if W.engine_route().get("mode") not in ("bundled", "custom"):
            _bad.append(p["name"])
    ok("كلُّ منصّةٍ في السجلّ لها طريقٌ إلى المحرّك", not _bad, str(_bad))
    W._load_settings = _real_load
    for k, v in _saved.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
except Exception as e:
    ok("engine_route متاح", False, str(e))


print("\n" + "=" * 62)
print(f" RESULT: {'PASS' if F == 0 else 'FAIL'}   ({P_}/{P_ + F})")
print("=" * 62)
sys.exit(1 if F else 0)
