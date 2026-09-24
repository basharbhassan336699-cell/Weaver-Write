# -*- coding: utf-8 -*-
"""أيُّ منصّةٍ وأيُّ نموذج — عبر المحرّك.

العطبُ الذي رآه المستخدمُ بعد تغيير مفتاحه:

    Unknown model: deepseek/deepseek-v4-pro

المحرّكُ يكتبها `Unknown model: ${provider}/${modelId}` — طُلب منه مزوّدٌ اسمُه
`deepseek` وليس فيه مزوّدٌ بهذا الاسم (مزوّدٌ خارجيٌّ غيرُ مركَّب). فكانت كلُّ
منصّةٍ لا إضافةَ لها في المحرّك تفشل، وتسقط الواجهةُ إلى نداءٍ مباشرٍ بلا أدوات.

والحلُّ آليّةُ المحرّك نفسِه (docs/gateway/config-tools/custom-providers.md،
onboard-custom-config applyCustomApiConfig): مزوّدٌ مخصَّصٌ في
`models.providers.weaver` برابطِك ونموذجِك. وهذه الفحوصُ تمنع عودةَ العطب.
"""
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

from pipeline import weaver_core as W   # noqa: E402
from config import keysync              # noqa: E402

P = F = 0


def ok(name, cond, extra=""):
    global P, F
    if cond:
        P += 1
        print(f"  ✓ {name}")
    else:
        F += 1
        print(f"  ✗ {name}" + (f"   — {extra}" if extra else ""))


_KEYS = ("WEAVER_PROVIDER", "WEAVER_BASE_URL", "WEAVER_MODEL",
         "WEAVER_API_KEY", "WEAVER_ENGINE_ROUTE", "WEAVER_ENGINE_API",
         "WEAVER_MAX_TOKENS")
_SAVED_ENV = {k: os.environ.get(k) for k in _KEYS}
# الإعدادُ يُقرأ من config/.env ثمّ البيئة — فيُعزَل الملفُّ عن الفحص.
_real_load = W._load_settings
W._load_settings = lambda: {k: os.environ[k] for k in _KEYS
                            if os.environ.get(k)}

# خريطةُ مزوّداتٍ ثابتة — بشكل ما يقرؤه `bundled_providers()` من الإضافات —
# كي لا يتعلّق الفحصُ بوجود المحرّك على الجهاز.
_real_bundled = W.bundled_providers
_MAP = {
    "openrouter": {"hosts": set(), "suffixes": ["openrouter.ai"]},
    "openai": {"hosts": {"api.openai.com", "chatgpt.com"},
               "suffixes": [".api.openai.com", ".openai.azure.com"]},
    "anthropic": {"hosts": {"api.anthropic.com"}, "suffixes": []},
    "google": {"hosts": {"generativelanguage.googleapis.com"},
               "suffixes": []},
    "xai": {"hosts": {"api.x.ai"}, "suffixes": []},
    "vllm": {"hosts": set(), "suffixes": []},
}
W.bundled_providers = lambda refresh=False: _MAP
W.key_env_name = (lambda provider=None, _o=W.key_env_name:
                  W._PROVIDER_ENV.get((provider or W.provider_id()
                                       or "").lower(), ""))


def setenv(**kw):
    for k in _KEYS:
        os.environ.pop(k, None)
    for k, v in kw.items():
        if v:
            os.environ[k] = v


try:
    print("\n— ما رآه المستخدم: منصّةٌ بلا مزوّدٍ مدمج —")
    setenv(WEAVER_PROVIDER="deepseek", WEAVER_BASE_URL="https://api.deepseek.com",
           WEAVER_MODEL="deepseek-v4-pro", WEAVER_API_KEY="sk-abcd1234")
    r = W.engine_route()
    ok("deepseek المباشرُ يصير مزوّداً مخصَّصاً", r.get("mode") == "custom",
       str(r))
    ok("  ⟵ والنموذجُ `weaver/deepseek-v4-pro` لا `deepseek/…` المرفوض",
       W.model_id() == "weaver/deepseek-v4-pro", W.model_id())
    ok("  ⟵ و`model_ref` مطابقٌ له (ما يُكتب في primary)",
       W.model_ref() == W.model_id())
    ok("  ⟵ والمفتاحُ باسمنا لا باسم مزوّدٍ غير مركَّب",
       W.credentials() == {W.CUSTOM_KEY_ENV: "sk-abcd1234"},
       str(list(W.credentials())))
    ok("  ⟵ ويصل بيئةَ المحرّك",
       W.engine_env().get(W.CUSTOM_KEY_ENV) == "sk-abcd1234")

    t = W.custom_provider_tree()
    pv = t["models"]["providers"]["weaver"]
    ok("الشجرة: baseUrl رابطُك كما هو", pv["baseUrl"] == "https://api.deepseek.com")
    ok("الشجرة: openai-completions (افتراضُ المحرّك للمخصَّص)",
       pv["api"] == "openai-completions")
    ok("الشجرة: المفتاحُ إشارةٌ لا نصٌّ صريح",
       pv["apiKey"] == "${WEAVER_PLATFORM_API_KEY}"
       and "sk-abcd1234" not in str(t))
    ok("الشجرة: النموذجُ مُدرَج", pv["models"][0]["id"] == "deepseek-v4-pro")
    ok("الشجرة: max_tokens (تفهمه المنصّاتُ المتوافقةُ كلُّها)",
       pv["models"][0].get("compat", {}).get("maxTokensField") == "max_tokens")
    ok("الشجرة: سياقٌ 128000 كمعالج المحرّك",
       pv["models"][0]["contextWindow"] == 128000)
    ok("الشجرة: بلا maxTokens ما لم تضبطه (المحرّكُ يقرّر)",
       "maxTokens" not in pv["models"][0])
    os.environ["WEAVER_MAX_TOKENS"] = "16000"
    ok("  ⟵ وWEAVER_MAX_TOKENS تُحترم",
       W.custom_provider_tree()["models"]["providers"]["weaver"]
       ["models"][0].get("maxTokens") == 16000)
    os.environ.pop("WEAVER_MAX_TOKENS")

    print("\n— ما يعمل يبقى كما كان —")
    setenv(WEAVER_PROVIDER="openrouter",
           WEAVER_BASE_URL="https://openrouter.ai/api/v1",
           WEAVER_MODEL="deepseek/deepseek-v4-flash", WEAVER_API_KEY="sk-or-1")
    ok("OpenRouter: مزوّدٌ مدمج", W.engine_route().get("mode") == "bundled")
    ok("  ⟵ نفسُ المرجع السابق حرفاً",
       W.model_id() == "openrouter/deepseek/deepseek-v4-flash", W.model_id())
    ok("  ⟵ ونفسُ اسم المفتاح",
       W.credentials() == {"OPENROUTER_API_KEY": "sk-or-1"})
    ok("  ⟵ ولا مزوّدَ مخصَّصاً يُكتب", W.custom_provider_tree() == {})
    os.environ["WEAVER_MODEL"] = "openrouter/some/model"
    ok("  ⟵ ولا سابقةَ مزدوجة", W.model_id() == "openrouter/some/model")
    setenv(WEAVER_PROVIDER="openrouter", WEAVER_MODEL="x/y",
           WEAVER_API_KEY="sk-or-1")
    ok("OpenRouter بلا رابط: مدمجٌ أيضاً",
       W.model_id() == "openrouter/x/y")
    setenv(WEAVER_BASE_URL="https://openrouter.ai/api/v1", WEAVER_MODEL="a/b",
           WEAVER_API_KEY="sk-or-1")
    ok("OpenRouter من الرابط وحده", W.model_id() == "openrouter/a/b")
    setenv(WEAVER_PROVIDER="anthropic",
           WEAVER_BASE_URL="https://api.anthropic.com/v1",
           WEAVER_MODEL="claude-opus-5", WEAVER_API_KEY="sk-ant-1")
    ok("أنثروبيك: مدمج", W.model_id() == "anthropic/claude-opus-5")

    print("\n— المضيفُ هو الحَكَم لا الاسم —")
    setenv(WEAVER_PROVIDER="openai",
           WEAVER_BASE_URL="https://api.groq.com/openai/v1",
           WEAVER_MODEL="llama", WEAVER_API_KEY="gsk_1")
    ok("«openai» برابط Groq ⟵ مخصَّص (لا يُرسَل إلى api.openai.com)",
       W.engine_route().get("mode") == "custom", str(W.engine_route()))
    setenv(WEAVER_PROVIDER="openai",
           WEAVER_BASE_URL="https://openai.proxy.example/v1",
           WEAVER_MODEL="m", WEAVER_API_KEY="k")
    ok("مضيفٌ فيه كلمةُ openai وليس لها ⟵ مخصَّص",
       W.engine_route().get("mode") == "custom")
    setenv(WEAVER_PROVIDER="gemini",
           WEAVER_BASE_URL=("https://generativelanguage.googleapis.com"
                            "/v1beta/openai"),
           WEAVER_MODEL="gemini-2.0-flash", WEAVER_API_KEY="AIza1")
    ok("رابطُ Gemini المتوافق ⟵ google (كان يُنسَب إلى openai لمساره)",
       W.model_id() == "google/gemini-2.0-flash", W.model_id())
    setenv(WEAVER_PROVIDER="vllm", WEAVER_BASE_URL="http://127.0.0.1:8000/v1",
           WEAVER_MODEL="qwen", WEAVER_API_KEY="x")
    ok("مزوّدٌ مدمجٌ بلا مضيفٍ مُعلَن ورابطٌ محلّي ⟵ مخصَّص يعمل",
       W.engine_route().get("mode") == "custom")

    print("\n— أيُّ منصّةٍ أخرى —")
    for prov, base in (("groq", "https://api.groq.com/openai/v1"),
                       ("mistral", "https://api.mistral.ai/v1"),
                       ("", "https://llm.example.com/v1"),
                       ("custom", "http://192.168.1.5:1234/v1")):
        setenv(WEAVER_PROVIDER=prov, WEAVER_BASE_URL=base,
               WEAVER_MODEL="some/model", WEAVER_API_KEY="k1")
        ok("%-8s ⟵ weaver/some/model" % (prov or "(بلا اسم)"),
           W.model_id() == "weaver/some/model", W.model_id())
    setenv(WEAVER_PROVIDER="deepseek",
           WEAVER_BASE_URL="https://api.deepseek.com/anthropic",
           WEAVER_MODEL="m", WEAVER_API_KEY="k")
    ok("رابطٌ متوافقٌ مع أنثروبيك ⟵ anthropic-messages",
       W.engine_route().get("api") == "anthropic-messages")
    os.environ["WEAVER_ENGINE_API"] = "openai-responses"
    ok("WEAVER_ENGINE_API تفرض المحوِّل",
       W.engine_route().get("api") == "openai-responses")
    os.environ.pop("WEAVER_ENGINE_API")
    setenv(WEAVER_MODEL="weaver/m", WEAVER_BASE_URL="https://x.example/v1",
           WEAVER_API_KEY="k")
    ok("ولا سابقةَ مزدوجة للمخصَّص", W.model_id() == "weaver/m")

    print("\n— ولا ادّعاءَ بلا دليل —")
    setenv(WEAVER_MODEL="m", WEAVER_API_KEY="k")
    ok("لا مزوّدَ ولا رابط ⟵ لا نموذجَ ولا مفتاح",
       W.model_id() == "" and W.credentials() == {})
    setenv(WEAVER_PROVIDER="openrouter", WEAVER_API_KEY="k")
    ok("لا نموذج ⟵ لا طريق", W.engine_route().get("mode") == "")

    print("\n— configure_model: كتابةٌ واحدة، والمزوّدُ يُستبدَل كاملاً —")
    _calls = []
    _real_patch = W.config_patch
    _real_save = W._save_fingerprint
    W.config_patch = lambda tree, timeout=180, replace_paths=(): (
        _calls.append((tree, list(replace_paths))) or (True, "ok"))
    W._save_fingerprint = lambda fp: _calls.append(("saved", fp))
    setenv(WEAVER_PROVIDER="deepseek", WEAVER_BASE_URL="https://api.deepseek.com",
           WEAVER_MODEL="deepseek-v4-pro", WEAVER_API_KEY="sk-abcd1234")
    rows = W.configure_model()
    tree, rep = _calls[0]
    ok("نداءُ patch واحد", len([c for c in _calls if c[0] != "saved"]) == 1)
    ok("primary = weaver/deepseek-v4-pro",
       tree["agents"]["defaults"]["model"]["primary"]
       == "weaver/deepseek-v4-pro")
    ok("والمزوّدُ في الكتابة نفسِها",
       "weaver" in tree.get("models", {}).get("providers", {}))
    ok("والمفتاحُ في env.vars باسمنا",
       tree["env"]["vars"].get(W.CUSTOM_KEY_ENV) == "sk-abcd1234")
    ok("--replace-path للمزوّد وحده (المحرّكُ يرفض استبدالَ المصفوفة بدونه)",
       rep == ["models.providers.weaver"], str(rep))
    ok("والبصمةُ تُحفَظ بعد النجاح", any(c[0] == "saved" for c in _calls))
    ok("والصفوفُ لا تطبع المفتاح",
       all("sk-abcd1234" not in n for n, _o, _w in rows))
    _calls.clear()
    setenv(WEAVER_PROVIDER="openrouter",
           WEAVER_BASE_URL="https://openrouter.ai/api/v1",
           WEAVER_MODEL="deepseek/deepseek-v4-flash", WEAVER_API_KEY="sk-or-1")
    W.configure_model()
    tree, rep = _calls[0]
    ok("OpenRouter: بلا models ولا replace — كما كان",
       "models" not in tree and rep == [])
    W.config_patch = _real_patch
    W._save_fingerprint = _real_save

    print("\n— model_sync: يتبع الواجهةَ بلا أمرٍ يدويّ —")
    _st = {"applied": {}, "cfg": 0, "stop": 0, "alive": True}
    _real = {n: getattr(W, n) for n in (
        "available", "_applied_fingerprint", "configure_model",
        "gateway_health", "gateway_stop", "_record_run")}
    W.available = lambda: True
    W._applied_fingerprint = lambda: dict(_st["applied"])

    def _fake_cfg():
        _st["cfg"] += 1
        _st["applied"] = W._model_fingerprint()
        return [("x", True, "")]
    W.configure_model = _fake_cfg
    W.gateway_health = lambda timeout=2: _st["alive"]
    W.gateway_stop = lambda: _st.__setitem__("stop", _st["stop"] + 1)
    setenv(WEAVER_PROVIDER="deepseek", WEAVER_BASE_URL="https://api.deepseek.com",
           WEAVER_MODEL="a", WEAVER_API_KEY="k-1")
    ch, _w = W.model_sync()
    ok("أوّلَ مرّة ⟵ يُكتب، وتُعاد البوّابة", ch and _st["cfg"] == 1
       and _st["stop"] == 1, str(_st))
    ch, _w = W.model_sync()
    ok("بلا تغيير ⟵ لا كتابةَ ولا إعادة", (not ch) and _st["cfg"] == 1
       and _st["stop"] == 1)
    os.environ["WEAVER_MODEL"] = "b"
    ch, _w = W.model_sync()
    ok("النموذجُ وحده ⟵ يُكتب بلا إعادة إقلاع", ch and _st["cfg"] == 2
       and _st["stop"] == 1, str(_st))
    os.environ["WEAVER_API_KEY"] = "k-2"
    W.model_sync()
    ok("مفتاحٌ جديد ⟵ يُكتب وتُعاد البوّابة (المفتاحُ في بيئتها)",
       _st["cfg"] == 3 and _st["stop"] == 2, str(_st))
    os.environ["WEAVER_BASE_URL"] = "https://api.groq.com/openai/v1"
    W.model_sync()
    ok("منصّةٌ أخرى ⟵ يُكتب وتُعاد البوّابة",
       _st["cfg"] == 4 and _st["stop"] == 3, str(_st))
    _st["alive"] = False
    os.environ["WEAVER_API_KEY"] = "k-3"
    W.model_sync()
    ok("وبوّابةٌ مطفأة ⟵ يُكتب فقط، ولا إطفاءَ لما لا يعمل",
       _st["cfg"] == 5 and _st["stop"] == 3)
    _rec = []
    W.configure_model = lambda: [("x", False, "Refusing to replace …")]
    W._record_run = lambda a, c, o, e: _rec.append((a, e))
    os.environ["WEAVER_API_KEY"] = "k-4"
    ch, why = W.model_sync()
    ok("فشلُ الكتابة لا يُبتلَع ⟵ يُسجَّل لـ--last",
       (not ch) and _rec and _rec[0][0] == ["model-sync"]
       and "Refusing" in why, str(_rec))
    for n, f in _real.items():
        setattr(W, n, f)

    fp = W._model_fingerprint()
    ok("البصمةُ لا تحمل المفتاح", "k-4" not in str(fp))

    print("\n— المواضع في الكود —")
    _src = open(os.path.join(_ROOT, "pipeline", "weaver_core.py"),
                encoding="utf-8").read()
    _ask = _src[_src.index("def ask("):_src.index("def ask(") + 6000]
    ok("ask() تُزامن قبل الإقلاع",
       _ask.index("model_sync()") < _ask.index("gateway_start()"))
    _gs = _src[_src.index("def gateway_start("):]
    _gs = _gs[:_gs.index("\ndef ")]
    ok("gateway_start تكتب المنصّةَ المتغيّرةَ قبل Popen",
       _gs.index("configure_model()") < _gs.index("subprocess.Popen("))

    print("\n— الإضافاتُ الحقيقيّة (إن كان المحرّكُ مركَّباً) —")
    W.bundled_providers = _real_bundled
    real = _real_bundled(refresh=True)
    if real:
        ok("openrouter مدمج", "openrouter" in real)
        ok("deepseek ليس مدمجاً (وهذا أصلُ العطب)", "deepseek" not in real)
        ok("مضيفُ openai مُعلَن",
           "api.openai.com" in real.get("openai", {}).get("hosts", ()))
    else:
        print("  (المحرّك غير مركَّب هنا — تُخطّى)")

    print("\n— keysync: بادئةُ المفتاح أصدقُ من قائمةٍ على منصّةٍ أخرى —")
    ok("sk-or- والقائمةُ على deepseek برابطها الافتراضيّ ⟵ تُتبَع البادئة",
       keysync._other_known_platform("deepseek", "https://api.deepseek.com/v1",
                                     "openrouter"))
    ok("  ⟵ وبلا رابطٍ أيضاً",
       keysync._other_known_platform("deepseek", "", "openrouter"))
    ok("رابطٌ كتبه المستخدم (وسيط) ⟵ لا يُمَسّ",
       not keysync._other_known_platform("deepseek",
                                         "https://my-proxy.example/v1",
                                         "openrouter"))
    ok("نفسُ المنصّة ⟵ لا تغيير",
       not keysync._other_known_platform("openrouter",
                                         "https://openrouter.ai/api/v1",
                                         "openrouter"))
    ok("منصّةٌ غيرُ معروفة ⟵ لا تغيير",
       not keysync._other_known_platform("__nope__", "", "openrouter"))
    _saved = {}
    _real_save_env = keysync.save_env
    keysync.save_env = lambda u: _saved.update(u)
    try:
        keysync.set_api_key("sk-or-v1-TEST", provider="deepseek",
                            base_url="https://api.deepseek.com/v1", model="")
        ok("set_api_key: مفتاحُ OpenRouter يذهب إلى OpenRouter",
           _saved.get("WEAVER_PROVIDER") == "openrouter"
           and "openrouter.ai" in _saved.get("WEAVER_BASE_URL", ""), str(
               {k: v for k, v in _saved.items() if k != "WEAVER_API_KEY"}))
        _saved.clear()
        keysync.set_api_key("sk-or-v1-TEST", provider="openrouter",
                            base_url="https://openrouter.ai/api/v1",
                            model="deepseek/deepseek-v4-flash")
        ok("  ⟵ والاختيارُ الصحيحُ يبقى كما هو",
           _saved.get("WEAVER_MODEL") == "deepseek/deepseek-v4-flash"
           and _saved.get("WEAVER_PROVIDER") == "openrouter")
        _saved.clear()
        keysync.set_api_key("sk-plain-deepseek", provider="deepseek",
                            base_url="https://api.deepseek.com/v1",
                            model="deepseek-v4-pro")
        ok("  ⟵ ومفتاحٌ بلا بادئةٍ معروفة يتبع اختيارَك",
           _saved.get("WEAVER_PROVIDER") == "deepseek"
           and _saved.get("WEAVER_MODEL") == "deepseek-v4-pro")
    finally:
        keysync.save_env = _real_save_env
finally:
    W._load_settings = _real_load
    W.bundled_providers = _real_bundled
    for k, v in _SAVED_ENV.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v

print("\n" + "=" * 62)
print(f" RESULT: {'PASS' if F == 0 else 'FAIL'}   ({P}/{P + F})")
print("=" * 62)
sys.exit(1 if F else 0)
