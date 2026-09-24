"""
providers.py — سجل مزوّدين مدفوع بالبيانات + كشف المنصة تلقائياً من المفتاح
==========================================================================

حل عام لا يخصّ منصة بعينها: أي منصة تُدخل مفتاحها يُكتشف رابطها وتُعرَض نماذجها.

آليتان متكاملتان:
  1) كشف بالبادئة  — للمنصات ذات بادئة مفتاح مميّزة (nvapi-/sk-ant-/gsk_/…).
  2) سبر تلقائي    — يجرّب نقاط /models لمزوّدي السجل بالمفتاح؛ أول من يُرجع
                     نماذج = المنصة. يغطّي المنصات ذات المفاتيح العامة (sk-…).

السجل **مدفوع بالبيانات**: افتراضي مدمج + `config/providers.json` قابل للتوسيع،
فتُضاف أي منصة بلا تعديل كود. لا يمسّ هذا الملف مصادقة provider.py.

EN: Data-driven provider registry + automatic platform detection from an API key
(prefix match, then probing /models). Extensible via config/providers.json.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Callable, List, Optional, Tuple

_ROOT = Path(__file__).resolve().parent.parent  # weaver-write root
_USER_REGISTRY = Path(__file__).resolve().parent / "providers.json"

# سجل افتراضي — كل مدخل: name, base_url, model, prefixes[], auth(bearer|x-api-key)
# قابل للتوسيع/التجاوز عبر config/providers.json (لا تخصيص في المنطق).
_DEFAULT: List[dict] = [
    {"name": "openai", "base_url": "https://api.openai.com/v1",
     "model": "gpt-4o", "prefixes": ["sk-proj-"], "auth": "bearer"},
    {"name": "anthropic", "base_url": "https://api.anthropic.com/v1",
     "model": "claude-opus-4-8", "prefixes": ["sk-ant-"], "auth": "x-api-key"},
    {"name": "groq", "base_url": "https://api.groq.com/openai/v1",
     "model": "llama-3.3-70b-versatile", "prefixes": ["gsk_"], "auth": "bearer"},
    {"name": "openrouter", "base_url": "https://openrouter.ai/api/v1",
     "model": "anthropic/claude-sonnet-4-6", "prefixes": ["sk-or-"], "auth": "bearer"},
    {"name": "nvidia", "base_url": "https://integrate.api.nvidia.com/v1",
     "model": "meta/llama-3.1-70b-instruct", "prefixes": ["nvapi-"], "auth": "bearer"},
    {"name": "xai", "base_url": "https://api.x.ai/v1",
     "model": "grok-2-latest", "prefixes": ["xai-"], "auth": "bearer"},
    {"name": "perplexity", "base_url": "https://api.perplexity.ai",
     "model": "sonar", "prefixes": ["pplx-"], "auth": "bearer"},
    {"name": "fireworks", "base_url": "https://api.fireworks.ai/inference/v1",
     "model": "accounts/fireworks/models/llama-v3p1-70b-instruct",
     "prefixes": ["fw_"], "auth": "bearer"},
    {"name": "cerebras", "base_url": "https://api.cerebras.ai/v1",
     "model": "llama3.1-70b", "prefixes": ["csk-"], "auth": "bearer"},
    {"name": "google", "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
     "model": "gemini-2.0-flash", "prefixes": ["AIza"], "auth": "bearer"},
    {"name": "deepseek", "base_url": "https://api.deepseek.com/v1",
     "model": "deepseek-chat", "prefixes": [], "auth": "bearer"},
    {"name": "together", "base_url": "https://api.together.xyz/v1",
     "model": "meta-llama/Llama-3.3-70B-Instruct-Turbo", "prefixes": [], "auth": "bearer"},
    {"name": "mistral", "base_url": "https://api.mistral.ai/v1",
     "model": "mistral-large-latest", "prefixes": [], "auth": "bearer"},
    {"name": "aerolink", "base_url": "https://capi.aerolink.lat/v1",
     "model": "claude-fable-5", "prefixes": [], "auth": "bearer"},
    {"name": "ollama", "base_url": "http://localhost:11434/v1",
     "model": "llama3.2", "prefixes": [], "auth": "bearer"},
]


# ── منصّاتُ أوبن كلاو ─────────────────────────────────────────────────────
#
# من المحرّك نفسِه لا من الذاكرة: مزوّداتُه المدمجة
# (dist/extensions/*/openclaw.plugin.json) والخارجيّةُ الرسميّة
# (official-external-provider-catalog)، وكلُّ رابطٍ منقولٌ من صفحة توثيقه
# (docs/providers/<name>.md) — «Base URL» المتوافقُ مع OpenAI حرفاً.
#
# والنموذجُ الافتراضيُّ حيث تنصّ الصفحةُ على «Default model» لنموذج محادثة،
# وإلّا فارغٌ: يُختار من «استكشاف النماذج» (الأحدثُ أوّلاً).
#
# ولا بادئاتِ مفاتيح: لم يوثّقها المحرّكُ لهذه المنصّات، وبادئةٌ مخمَّنةٌ
# توجّه مفتاحاً إلى غير منصّته. وتعمل كلُّها عبر المحرّك بمزوّده المخصَّص
# (أو المدمج حيث وُجد) — pipeline/weaver_core.py  engine_route().
#
# ولم يُضَف ما لا يصلح لمفتاحٍ ورابطٍ ثابت: Bedrock وVertex (اعتمادُ سحابة)،
# وCloudflare AI Gateway (رابطٌ بحسابك)، وSynthetic (أنثروبيك فقط)، وOpenCode
# Zen (واجهاتٌ مختلفةٌ لكلّ نموذج)، وGitHub Copilot وMiniMax Portal (OAuth)،
# ومنصّاتُ الصوت والصورة والفيديو والتضمين (ComfyUI، PixVerse، Vydra، Voyage،
# fal)، وخططُ الاشتراك المستقلّة (Token Plan / Coding Plan) عدا Kimi Coding.
_OPENCLAW: List[dict] = [
    # مدمجةٌ في المحرّك
    {"name": "huggingface", "base_url": "https://router.huggingface.co/v1",
     "model": "", "prefixes": [], "auth": "bearer"},
    {"name": "minimax", "base_url": "https://api.minimax.io/v1",
     "model": "", "prefixes": [], "auth": "bearer"},
    {"name": "opencode-go", "base_url": "https://opencode.ai/zen/go/v1",
     "model": "", "prefixes": [], "auth": "bearer"},
    {"name": "lmstudio", "base_url": "http://localhost:1234/v1",
     "model": "", "prefixes": [], "auth": "bearer"},
    {"name": "vllm", "base_url": "http://127.0.0.1:8000/v1",
     "model": "", "prefixes": [], "auth": "bearer"},
    {"name": "sglang", "base_url": "http://127.0.0.1:30000/v1",
     "model": "", "prefixes": [], "auth": "bearer"},
    {"name": "litellm", "base_url": "http://localhost:4000",
     "model": "", "prefixes": [], "auth": "bearer"},
    # خارجيّةٌ رسميّة (تعمل هنا بلا تركيب إضافتها)
    {"name": "arcee", "base_url": "https://api.arcee.ai/api/v1",
     "model": "", "prefixes": [], "auth": "bearer"},
    {"name": "baseten", "base_url": "https://inference.baseten.co/v1",
     "model": "thinkingmachines/inkling", "prefixes": [], "auth": "bearer"},
    {"name": "chutes", "base_url": "https://llm.chutes.ai/v1",
     "model": "", "prefixes": [], "auth": "bearer"},
    {"name": "cohere", "base_url": "https://api.cohere.ai/compatibility/v1",
     "model": "command-a-plus-05-2026", "prefixes": [], "auth": "bearer"},
    {"name": "deepinfra", "base_url": "https://api.deepinfra.com/v1/openai",
     "model": "", "prefixes": [], "auth": "bearer"},
    {"name": "featherless", "base_url": "https://api.featherless.ai/v1",
     "model": "Qwen/Qwen3-32B", "prefixes": [], "auth": "bearer"},
    {"name": "gmi", "base_url": "https://api.gmi-serving.com/v1",
     "model": "openai/gpt-5.6-sol", "prefixes": [], "auth": "bearer"},
    {"name": "kilocode", "base_url": "https://api.kilo.ai/api/gateway",
     "model": "", "prefixes": [], "auth": "bearer"},
    {"name": "kimi-coding", "base_url": "https://api.kimi.com/coding/v1",
     "model": "", "prefixes": [], "auth": "bearer"},
    {"name": "longcat", "base_url": "https://api.longcat.chat/openai",
     "model": "LongCat-2.0", "prefixes": [], "auth": "bearer"},
    {"name": "meta", "base_url": "https://api.meta.ai/v1",
     "model": "muse-spark-1.3", "prefixes": [], "auth": "bearer"},
    {"name": "moonshot", "base_url": "https://api.moonshot.ai/v1",
     "model": "", "prefixes": [], "auth": "bearer"},
    {"name": "moonshot-cn", "base_url": "https://api.moonshot.cn/v1",
     "model": "", "prefixes": [], "auth": "bearer"},
    {"name": "novita", "base_url": "https://api.novita.ai/openai/v1",
     "model": "deepseek/deepseek-v4-pro", "prefixes": [], "auth": "bearer"},
    {"name": "qianfan", "base_url": "https://qianfan.baidubce.com/v2",
     "model": "deepseek-v4-pro", "prefixes": [], "auth": "bearer"},
    {"name": "qwen", "base_url":
     "https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
     "model": "", "prefixes": [], "auth": "bearer"},
    {"name": "qwen-cn", "base_url":
     "https://dashscope.aliyuncs.com/compatible-mode/v1",
     "model": "", "prefixes": [], "auth": "bearer"},
    {"name": "stepfun", "base_url": "https://api.stepfun.ai/v1",
     "model": "", "prefixes": [], "auth": "bearer"},
    {"name": "stepfun-cn", "base_url": "https://api.stepfun.com/v1",
     "model": "", "prefixes": [], "auth": "bearer"},
    {"name": "tencent-tokenhub", "base_url": "https://tokenhub.tencentmaas.com/v1",
     "model": "hy4-preview", "prefixes": [], "auth": "bearer"},
    {"name": "venice", "base_url": "https://api.venice.ai/api/v1",
     "model": "", "prefixes": [], "auth": "bearer"},
    {"name": "volcengine", "base_url": "https://ark.cn-beijing.volces.com/api/v3",
     "model": "", "prefixes": [], "auth": "bearer"},
    {"name": "xiaomi", "base_url": "https://api.xiaomimimo.com/v1",
     "model": "mimo-v2.5", "prefixes": [], "auth": "bearer"},
    {"name": "zai", "base_url": "https://api.z.ai/api/paas/v4",
     "model": "glm-5.2", "prefixes": [], "auth": "bearer"},
    {"name": "zai-cn", "base_url": "https://open.bigmodel.cn/api/paas/v4",
     "model": "glm-5.2", "prefixes": [], "auth": "bearer"},
]


def load_registry() -> List[dict]:
    """السجل الفعّال: الافتراضي مدموجاً مع config/providers.json (يُحدِّث/يضيف)."""
    reg = {p["name"]: dict(p) for p in _DEFAULT}
    for p in _OPENCLAW:                      # إضافةٌ فقط: لا يُمَسّ ما سبق
        reg.setdefault(p["name"], dict(p))
    if _USER_REGISTRY.exists():
        try:
            data = json.loads(_USER_REGISTRY.read_text(encoding="utf-8"))
            for p in data.get("providers", data if isinstance(data, list) else []):
                if isinstance(p, dict) and p.get("name") and p.get("base_url"):
                    base = reg.get(p["name"], {})
                    merged = {**base, "prefixes": [], "auth": "bearer",
                              "model": "", **p}
                    # `add_provider` يكتب `prefixes: []` لكلّ ما يحفظه، فكان وصلُ
                    # OpenRouter من الطرفيّة يمحو `sk-or-` من السجلّ — فلا تُكشف
                    # مفاتيحُه بعدها. قائمةٌ فارغةٌ لا تمحو بادئةً موثّقة.
                    if not merged.get("prefixes") and base.get("prefixes"):
                        merged["prefixes"] = list(base["prefixes"])
                    reg[p["name"]] = merged
        except Exception:
            pass
    return list(reg.values())


def add_provider(name: str, base_url: str, model: str = "",
                 prefixes: Optional[List[str]] = None, auth: str = "bearer") -> bool:
    """يضيف/يحدّث مزوّداً في config/providers.json (توسيع لأي منصة بلا كود)."""
    name = (name or "").strip()
    base_url = (base_url or "").strip().rstrip("/")
    if not name or not base_url:
        return False
    existing = {}
    if _USER_REGISTRY.exists():
        try:
            existing = json.loads(_USER_REGISTRY.read_text(encoding="utf-8"))
        except Exception:
            existing = {}
    providers = existing.get("providers", []) if isinstance(existing, dict) else []
    providers = [p for p in providers if p.get("name") != name]
    providers.append({"name": name, "base_url": base_url, "model": model or "",
                      "prefixes": prefixes or [], "auth": auth})
    _USER_REGISTRY.parent.mkdir(parents=True, exist_ok=True)
    _USER_REGISTRY.write_text(json.dumps({"providers": providers},
                                         ensure_ascii=False, indent=2), encoding="utf-8")
    return True


def provider_names() -> List[str]:
    return [p["name"] for p in load_registry()]


def get_provider(name: str) -> Optional[dict]:
    name = (name or "").strip().lower()
    for p in load_registry():
        if p["name"].lower() == name:
            return p
    return None


def detect_by_prefix(key: str) -> Optional[dict]:
    """يطابق بادئة المفتاح مع السجل → مدخل المزوّد أو None."""
    key = (key or "").strip()
    if not key:
        return None
    for p in load_registry():
        for pref in p.get("prefixes", []):
            if pref and key.startswith(pref):
                return p
    return None


def headers_for(entry: dict, key: str) -> dict:
    """ترويسات المصادقة حسب نوع المزوّد (Bearer أو x-api-key)."""
    if entry.get("auth") == "x-api-key":
        return {"x-api-key": key, "anthropic-version": "2023-06-01",
                "Content-Type": "application/json", "User-Agent": "WeaverCode"}
    return {"Authorization": f"Bearer {key}",
            "Content-Type": "application/json", "User-Agent": "WeaverCode"}


def models_urls(base_url: str) -> List[str]:
    """نقاط /models المرشّحة لرابط مزوّد."""
    base = base_url.rstrip("/")
    root = base[:-3].rstrip("/") if base.lower().endswith("/v1") else base
    urls, seen = [], set()
    for u in (root + "/v1/models", root + "/models", base + "/models"):
        if u not in seen:
            seen.add(u)
            urls.append(u)
    return urls


def _created_ts(m) -> Optional[float]:
    """تاريخُ إصدار النموذج كما تُعلنه المنصّة — أو None.

    OpenAI وOpenRouter وGroq وغيرُها: `created` (ثوانٍ منذ ١٩٧٠).
    أنثروبيك: `created_at` بصيغة ISO."""
    if not isinstance(m, dict):
        return None
    c = m.get("created")
    if isinstance(c, (int, float)) and not isinstance(c, bool) and c > 0:
        return float(c / 1000.0 if c > 1e12 else c)   # ميلي‌ثانية ⟶ ثانية
    ca = m.get("created_at") or m.get("createdAt")
    if isinstance(ca, str) and ca:
        try:
            from datetime import datetime
            return datetime.fromisoformat(ca.replace("Z", "+00:00")).timestamp()
        except Exception:
            return None
    return None


def _models_from_response(data) -> list:
    """معرّفاتُ النماذج — **الأحدثُ أوّلاً**، بلا تكرار.

    كانت تُرتَّب أبجدياً (`sorted(set(...))`) ثمّ تعرض الواجهةُ أوّلَ ١٠٠:
    فعلى منصّةٍ فيها مئاتُ النماذج (OpenRouter) لا يظهر إلا ما يبدأ اسمُه
    بأوائل الحروف — وأكثرُه قديم — ويُقصّ الأحدثُ لأنّ اسمَ مطوّره متأخّرٌ
    في الأبجديّة. فالآن: تاريخُ الإصدار إن أعلنته المنصّةُ لأكثر نماذجها،
    وإلّا ترتيبُ المنصّة نفسِها كما أرسلته."""
    items = (data.get("data", data.get("models")) if isinstance(data, dict) else data)
    if not isinstance(items, list):
        return []
    rows, seen = [], set()
    for m in items:
        mid = ((m.get("id") or m.get("name")) if isinstance(m, dict)
               else (m if isinstance(m, str) else None))
        if mid and str(mid) not in seen:
            seen.add(str(mid))
            rows.append((str(mid), _created_ts(m)))
    dated = sum(1 for _mid, ts in rows if ts is not None)
    if rows and dated * 2 >= len(rows):
        # ترتيبٌ ثابت: المتساوي يبقى بترتيب المنصّة، وغيرُ المؤرَّخ آخراً.
        rows.sort(key=lambda r: -(r[1] if r[1] is not None else float("-inf")))
    return [mid for mid, _ts in rows]


HttpGet = Callable[[str, dict, int], Tuple[object, Optional[str]]]


def resolve_platform(key: str, http_get: HttpGet, current_base: str = "",
                     timeout: int = 8) -> Optional[dict]:
    """يحدّد منصة المفتاح: بادئة أولاً، ثم سبر نقاط /models للسجل.

    http_get(url, headers, timeout) -> (data|None, error|None).
    يُرجع مدخل المزوّد المطابق (مع 'models' مضافة) أو None. لا يبدّل شيئاً إن كان
    الرابط الحالي يعمل بالمفتاح أصلاً (فلا يُكسَر إعداد قائم مثل aerolink).
    """
    key = (key or "").strip()
    if not key:
        return None
    registry = load_registry()

    def _try(entry) -> Optional[dict]:
        headers = headers_for(entry, key)
        for url in models_urls(entry["base_url"]):
            data, err = http_get(url, headers, timeout)
            if not err:
                models = _models_from_response(data)
                if models:
                    e = dict(entry)
                    e["models"] = models       # الأحدثُ أوّلاً، لا أبجدياً
                    e["source"] = url
                    return e
        return None

    # 1) كشف بالبادئة (سريع، بلا تسريب) ثم تأكيد بالنماذج
    pref = detect_by_prefix(key)
    if pref:
        got = _try(pref)
        if got:
            return got

    # 2) إن كان الرابط الحالي يعمل بالمفتاح → أبقِه (لا تبديل غير ضروري)
    cur = current_base.strip().rstrip("/")
    if cur:
        cur_entry = next((p for p in registry if p["base_url"].rstrip("/") == cur), None)
        cur_entry = cur_entry or {"name": "الحالي", "base_url": cur,
                                  "model": "", "auth": "bearer"}
        got = _try(cur_entry)
        if got:
            return None  # الرابط الحالي صالح، لا حاجة للتبديل

    # 3) سبر بقية مزوّدي السجل (يغطّي المفاتيح العامة بلا بادئة)
    for entry in registry:
        if pref and entry["name"] == pref["name"]:
            continue
        got = _try(entry)
        if got:
            return got
    return None


# ═══════════════════════════════════════════════════════════
# Custom provider: connect ANY platform by URL + key, then list its models
# ═══════════════════════════════════════════════════════════
def _default_http_get(url: str, headers: dict, timeout: int = 8):
    """Minimal HTTP GET returning (json_data|None, error|None). Uses urllib
    so there's no hard dependency; works on Termux/Windows/macOS/Linux."""
    import json as _json
    import urllib.request
    import urllib.error
    try:
        req = urllib.request.Request(url, headers=headers or {})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", "replace")
        return _json.loads(raw), None
    except urllib.error.HTTPError as e:
        return None, f"HTTP {e.code}"
    except Exception as e:
        return None, str(e)


def list_models_for(base_url: str, key: str, auth: str = "bearer",
                    http_get: HttpGet = None, timeout: int = 8):
    """
    Fetch the available model IDs from a platform's /models endpoint.
    Returns (models_list, error). Works for any OpenAI-compatible API.
    """
    http_get = http_get or _default_http_get
    entry = {"base_url": base_url, "auth": auth}
    headers = headers_for(entry, key)
    last_err = None
    for url in models_urls(base_url):
        data, err = http_get(url, headers, timeout)
        if err:
            last_err = err
            continue
        models = _models_from_response(data)
        if models:
            return models, None          # الأحدثُ أوّلاً، لا أبجدياً
    return [], (last_err or "no models endpoint responded")


def connect_custom_provider(base_url: str, key: str, name: str = "custom",
                            auth: str = "bearer", model: str = "",
                            http_get: HttpGet = None, persist: bool = True):
    """
    Connect ANY provider outside the built-in list by giving its platform URL
    and API key. Auto-detects the available models so the user can pick one.

    Returns:
      {"name","base_url","auth","models":[...],"model":<chosen or first>,
       "error":<str|None>}

    If `persist` is True and it succeeds, the provider is saved to
    config/providers.json so it's remembered next time.
    """
    base_url = (base_url or "").strip().rstrip("/")
    if not base_url:
        return {"error": "base_url required", "models": []}
    # try both common auth schemes if the given one fails
    for try_auth in ([auth] + [a for a in ("bearer", "x-api-key") if a != auth]):
        models, err = list_models_for(base_url, key, try_auth, http_get)
        if models:
            chosen = model or (models[0] if models else "")
            result = {"name": name, "base_url": base_url, "auth": try_auth,
                      "models": models, "model": chosen, "error": None}
            if persist:
                try:
                    add_provider(name, base_url, chosen, prefixes=[], auth=try_auth)
                except Exception:
                    pass
            return result
    return {"name": name, "base_url": base_url, "auth": auth,
            "models": [], "model": "", "error": err or "could not list models"}
