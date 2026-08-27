"""
core/llm/__init__.py — the single LLM client (unblocks the whole pipeline)
==========================================================================
Every pipeline layer that needs the model (understand / write / verify) calls
ONE provider-agnostic function built from the synced settings in config/.env
(WEAVER_API_KEY / WEAVER_BASE_URL / WEAVER_MODEL / WEAVER_PROVIDER).

Two request shapes are supported, chosen automatically:
  - Anthropic  → POST {base}/messages        (x-api-key + anthropic-version)
  - OpenAI-compatible → POST {base}/chat/completions   (Bearer key)

If no key is configured, get_llm_fn() returns None and every layer keeps its
offline "placeholder" behaviour, so nothing crashes without a key.
"""
from __future__ import annotations
import os
import json
import urllib.request
import urllib.error

try:
    from config import keysync
except Exception:  # pragma: no cover - fallback when run in-dir
    import sys
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__)))))
    from config import keysync


def _is_anthropic(provider: str, base: str) -> bool:
    """Anthropic uses /messages; detect from the provider name or base URL."""
    p = (provider or "").strip().lower()
    if p in ("anthropic", "claude"):
        return True
    return "anthropic.com" in (base or "").lower()


def get_llm_fn():
    """Return llm_fn(prompt, system=None, temperature=0.7, max_tokens=None)->str
    built from config/.env. Returns None if no key is configured (callers must
    handle that by staying in placeholder mode)."""
    keysync.load_env()
    key = os.environ.get("WEAVER_API_KEY", "").strip()
    if not key:
        return None
    base = os.environ.get("WEAVER_BASE_URL", "https://api.anthropic.com/v1").strip()
    model = os.environ.get("WEAVER_MODEL", "claude-opus-4-8").strip()
    provider = os.environ.get("WEAVER_PROVIDER", "").strip()
    anthropic = _is_anthropic(provider, base)

    def llm_fn(prompt, system=None, temperature=0.7, max_tokens=None):
        if anthropic:
            url = base.rstrip("/") + "/messages"
            headers = {"x-api-key": key, "anthropic-version": "2023-06-01",
                       "content-type": "application/json"}
            payload = {"model": model, "max_tokens": max_tokens or 4096,
                       "temperature": temperature,
                       "messages": [{"role": "user", "content": prompt}]}
            if system:
                payload["system"] = system
        else:  # openai-compatible (openai, deepseek, groq, openrouter, custom…)
            url = base.rstrip("/") + "/chat/completions"
            headers = {"authorization": f"Bearer {key}",
                       "content-type": "application/json"}
            msgs = ([{"role": "system", "content": system}] if system else []) + \
                   [{"role": "user", "content": prompt}]
            payload = {"model": model, "temperature": temperature,
                       "max_tokens": max_tokens or 4096, "messages": msgs}
        req = urllib.request.Request(
            url, data=json.dumps(payload).encode("utf-8"),
            headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=120) as r:
            data = json.loads(r.read().decode("utf-8"))
        if anthropic:
            return "".join(b.get("text", "") for b in data.get("content", [])
                           if isinstance(b, dict))
        return data["choices"][0]["message"]["content"]

    return llm_fn


def get_vision_fn():
    """Optional: return vision_fn(prompt, image_bytes)->str, or None.
    Only some providers support vision; layers fall back to core/ocr."""
    return None  # wire per provider later; layers must fall back to OCR


def extract_json(text: str):
    """Best-effort: parse the first {...} JSON object found in model output.
    Returns a dict, or raises ValueError if none is parseable."""
    if not text:
        raise ValueError("empty text")
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ValueError("no JSON object found")
    return json.loads(text[start:end + 1])
