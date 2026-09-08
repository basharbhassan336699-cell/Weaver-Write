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
import time
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

    def llm_fn(prompt, system=None, temperature=0.7, max_tokens=None,
               timeout=None):
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
            # DeepSeek "reasoning" models (deepseek-v4-flash/pro, deepseek-reasoner)
            # spend the ENTIRE token budget on hidden reasoning and return an EMPTY
            # `content` (finish_reason=length, reasoning_tokens=all) unless thinking
            # is turned OFF. That is exactly what OpenClaw does by default:
            #   params.thinking = { type: reasoningEffort ? "enabled" : "disabled" }
            # so the model answers directly — fast, and `content` is actually
            # filled. We mirror it here (DeepSeek only, so other providers are
            # untouched). Configurable via WEAVER_THINKING (disabled|enabled).
            _dsk = ("deepseek" in provider.lower()) or (
                "deepseek.com" in base.lower())
            if _dsk:
                _think = os.environ.get(
                    "WEAVER_THINKING", "disabled").strip().lower()
                payload["thinking"] = {
                    "type": "enabled"
                    if _think in ("enabled", "on", "1", "true") else "disabled"}
        body = json.dumps(payload).encode("utf-8")
        # per-call timeout wins; otherwise WEAVER_TIMEOUT (default 180s) — slow
        # on-device models need more than 120s for long generations.
        try:
            _to = int(timeout or os.environ.get("WEAVER_TIMEOUT", "180") or 180)
        except Exception:
            _to = 180

        def _extract(data):
            if anthropic:
                return "".join(b.get("text", "") for b in data.get("content", [])
                               if isinstance(b, dict))
            try:
                msg = data["choices"][0]["message"]
            except (KeyError, IndexError, TypeError):
                return ""
            if not isinstance(msg, dict):
                return ""
            content = msg.get("content") or ""
            if content and content.strip():
                return content
            # SAFETY NET: a reasoning model that emitted only hidden reasoning and
            # no final text (content empty). Fall back to the reasoning field so we
            # never return nothing — mirrors OpenClaw promoting thinking→text.
            return (msg.get("reasoning_content") or msg.get("reasoning")
                    or msg.get("reasoning_text") or "")

        # ROBUSTNESS: on-device servers intermittently return an EMPTY completion
        # (load/overflow), which otherwise surfaces as "(رد فارغ من المزوّد)" and
        # makes rich generations silently fall back. Retry a few times — an empty
        # reply comes back fast, so retries are cheap — and retry transient network
        # errors once. Non-empty replies are returned immediately (no behaviour
        # change). Bounded by WEAVER_LLM_RETRIES (default 3 attempts total).
        try:
            _tries = int(os.environ.get("WEAVER_LLM_RETRIES", "3") or 3)
        except Exception:
            _tries = 3
        _tries = max(1, min(_tries, 6))
        last = ""
        for _i in range(_tries):
            req = urllib.request.Request(url, data=body, headers=headers,
                                         method="POST")
            # a network/timeout error propagates immediately (callers handle it,
            # and a big generation must not be retried into a multi-minute wait).
            with urllib.request.urlopen(req, timeout=_to) as r:
                data = json.loads(r.read().decode("utf-8"))
            content = _extract(data)
            if content and content.strip():
                return content
            # EMPTY completion (provider quirk under load) → retry; empties come
            # back fast so this is cheap, and it is the one thing that otherwise
            # silently degrades rich generations to a thin fallback.
            last = content or ""
            if _i < _tries - 1:
                time.sleep(1.0 * (_i + 1))
        return last

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
