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


# ── reasoning-family registry (the "smart, single-place" detection) ──────────
# A small DATA table of reasoning-model families. Each row maps a provider/model
# match to how that family turns its hidden reasoning OFF (so `content` fills
# fast instead of the whole token budget going to hidden reasoning and returning
# empty). Adding a NEW family later = ONE row here, NOT new logic anywhere.
#
# Only DeepSeek is listed today, because it is the one family VERIFIED against a
# live model. That is deliberate and safe: the universal safety net in llm_fn
# (retry-on-empty + reading the reasoning field) already stops ANY model —
# listed or not — from returning nothing, so an unlisted new family degrades
# gracefully (never breaks); adding its row later just makes it fast/clean.
# The "off"/"on" fragments are merged verbatim into the request payload.
REASONING_FAMILIES = [
    {
        "name": "deepseek",              # DeepSeek v3/r1/v4-flash/pro/reasoner
        "match": ("deepseek",),          # provider name, base URL, or model id
        "off": {"thinking": {"type": "disabled"}},
        "on": {"thinking": {"type": "enabled"}},
    },
    # Future families (add one row each, from that provider's docs, when you
    # actually connect a model of that family — leave commented until tested):
    #   {"name": "qwen", "match": ("qwen", "qwq"),
    #    "off": {"enable_thinking": False}, "on": {"enable_thinking": True}},
]


def detect_reasoning_family(provider, base, model):
    """Return the REASONING_FAMILIES row matching this provider/base/model, or
    None for a plain (non-reasoning) or unlisted model. Matches on a case-folded
    haystack of all three, so detection works whether the family shows up in the
    provider name, the base URL, or the model id."""
    hay = " ".join([(provider or ""), (base or ""), (model or "")]).lower()
    for fam in REASONING_FAMILIES:
        if any(tok in hay for tok in fam.get("match", ())):
            return fam
    return None


def reasoning_payload(provider, base, model):
    """Return the payload fragment that switches a reasoning model's hidden
    thinking OFF (default) or ON, per its family in the registry. Returns {} for
    any non-reasoning / unlisted model, so those payloads stay byte-for-byte
    unchanged. Direction is controlled by WEAVER_THINKING (disabled by default,
    matching OpenClaw's default of thinking:{type:"disabled"})."""
    fam = detect_reasoning_family(provider, base, model)
    if not fam:
        return {}
    think = os.environ.get("WEAVER_THINKING", "disabled").strip().lower()
    on = think in ("enabled", "on", "1", "true")
    return dict(fam["on"] if on else fam["off"])


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
               timeout=None, on_delta=None):
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
            # Reasoning models (e.g. DeepSeek deepseek-v4-flash/pro/reasoner)
            # spend the ENTIRE token budget on hidden reasoning and return an EMPTY
            # `content` (finish_reason=length, reasoning_tokens=all) unless thinking
            # is turned OFF. That is exactly what OpenClaw does by default:
            #   params.thinking = { type: reasoningEffort ? "enabled" : "disabled" }
            # so the model answers directly — fast, and `content` is actually
            # filled. We look the model's family up in the REASONING_FAMILIES
            # registry above and merge its "off" fragment; a non-reasoning /
            # unlisted model gets {} so its payload is unchanged. Adding a new
            # reasoning family later is ONE row there, not a change here.
            payload.update(reasoning_payload(provider, base, model))
        body = json.dumps(payload).encode("utf-8")
        # per-call timeout wins; otherwise WEAVER_TIMEOUT (default 180s) — slow
        # on-device models need more than 120s for long generations.
        try:
            _to = int(timeout or os.environ.get("WEAVER_TIMEOUT", "180") or 180)
        except Exception:
            _to = 180

        # LIVE STREAMING (opt-in): when a caller passes on_delta, stream the reply
        # token-by-token (stream:true) and hand each content piece to on_delta as
        # it arrives — exactly what makes OpenClaw feel instant. Returns the full
        # accumulated text (same contract as the non-stream path). Only for
        # openai-compatible providers; anthropic and on_delta=None keep the plain
        # path below untouched. On any streaming error we fall through to the
        # non-stream request, so nothing regresses.
        if on_delta is not None and not anthropic:
            _sp = dict(payload)
            _sp["stream"] = True
            _sbody = json.dumps(_sp).encode("utf-8")
            _acc = []
            try:
                _req = urllib.request.Request(url, data=_sbody, headers=headers,
                                              method="POST")
                with urllib.request.urlopen(_req, timeout=_to) as r:
                    for _raw in r:
                        _line = _raw.decode("utf-8", "ignore").strip()
                        if not _line or not _line.startswith("data:"):
                            continue
                        _d = _line[5:].strip()
                        if _d == "[DONE]":
                            break
                        try:
                            _chunk = json.loads(_d)
                            _delta = _chunk["choices"][0]["delta"]
                        except (ValueError, KeyError, IndexError, TypeError):
                            continue
                        _piece = _delta.get("content") or ""
                        if _piece:
                            _acc.append(_piece)
                            try:
                                on_delta(_piece)
                            except Exception:
                                pass
            except Exception:
                _acc = []          # streaming failed → fall back to non-stream
            _full = "".join(_acc)
            if _full.strip():
                return _full
            # nothing streamed → fall through to the robust non-stream path

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
