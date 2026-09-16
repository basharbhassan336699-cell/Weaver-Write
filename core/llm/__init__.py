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


# ── WHEN THE PROVIDER ITSELF REFUSES ────────────────────────────────────────
# A run came back with fourteen headings and 28 words of body. The cause was
# not in any layer: every model call was returning «HTTP Error 403: Forbidden»
# — an expired key, a spent balance, a model the account may not use. Each
# call site caught the exception on its own and carried on with a fallback, so
# the pipeline walked the whole way down with no model at all and exported a
# shell with a green tick on every step. A refusal by the provider is not a
# per-call hiccup to absorb; it is a fact about the WHOLE run, and something
# has to remember it across call sites. This list is that memory: the layers
# read it and say plainly that the document could not be written, instead of
# each of them quietly degrading in its own corner.
PROVIDER_REFUSAL_CODES = (401, 402, 403, 407, 429)
_PROVIDER_ERRORS: list = []


def record_provider_error(code, reason="", where=""):
    """Remember a provider-level refusal. Bounded; never raises."""
    try:
        e = {"code": int(code), "reason": str(reason)[:200],
             "where": str(where)[:80]}
        _PROVIDER_ERRORS.append(e)
        del _PROVIDER_ERRORS[:-50]
    except Exception:
        pass


def provider_errors():
    """The refusals seen so far in this process (oldest first)."""
    return list(_PROVIDER_ERRORS)


def clear_provider_errors():
    """Start a fresh run with a clean slate."""
    try:
        _PROVIDER_ERRORS.clear()
    except Exception:
        pass


def provider_refusal_summary():
    """One short Arabic line naming the refusal, or "" when there was none."""
    try:
        errs = [e for e in _PROVIDER_ERRORS
                if e.get("code") in PROVIDER_REFUSAL_CODES]
        if not errs:
            return ""
        last = errs[-1]
        c = last.get("code")
        why = {401: "مفتاحٌ غير مقبول أو منتهٍ",
               402: "الرصيد نفد",
               403: "المزوّد رفض الطلب (مفتاح، أو رصيد، أو نموذجٌ غير متاح للحساب)",
               407: "الوسيط يطلب استيثاقاً",
               429: "تجاوزت حدّ النداءات"}.get(c, "رفضٌ من المزوّد")
        return f"HTTP {c} — {why} ({len(errs)} نداءً مرفوضاً)"
    except Exception:
        return ""


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
# marks a reply that is the model's hidden reasoning rather than its answer,
# so the retry loop can tell the two apart. Never reaches a caller.
_REASONING_MARK = "\x00weaver-reasoning\x00"

# Endpoints that REJECTED the reasoning switches, remembered for this process.
# A table of known providers can only ever grow, and a gateway nobody has listed
# yet would be a code change and a release. This is the other half: send the
# switches, and if the endpoint refuses the request because of them, drop them,
# retry, and never send them there again. Try, and adapt when refused — so an
# unknown endpoint works on its FIRST call, not after someone patches a table.
_REASONING_REFUSED = set()


def _reasoning_key(base, model):
    return (str(base or "").strip().lower(), str(model or "").strip().lower())

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


# Routers (OpenRouter, and any gateway added later) read their OWN parameter
# name, not the upstream family's. Sending the family's name alone left thinking
# ON: measured on a live run, the model spent its budget reasoning and was cut
# off before it could close its JSON. These rows sit BESIDE the families and
# both are merged, so each endpoint reads the one it knows.
REASONING_ROUTERS = [
    {
        "name": "openrouter",
        "match": ("openrouter",),
        "off": {"reasoning": {"enabled": False, "exclude": True}},
        "on": {"reasoning": {"enabled": True}},
    },
]

# config/reasoning.json — THE SAME TABLES AS DATA, editable without touching
# code. A row whose "name" already exists REPLACES the built-in one; a new name
# is appended. So connecting a new provider, router or family is a line YOU
# write, not a release you wait for. A missing or malformed file changes
# nothing: the built-in tables stand.
_REASONING_CONF_LOADED = [False]


def _reasoning_conf_path():
    return os.path.join(os.path.dirname(os.path.dirname(
        os.path.dirname(os.path.abspath(__file__)))), "config", "reasoning.json")


def _merge_rows(base_rows, extra):
    out = list(base_rows)
    by_name = {str(r.get("name", "")).lower(): i for i, r in enumerate(out)}
    for r in (extra or []):
        if not isinstance(r, dict) or not r.get("match"):
            continue
        row = {"name": str(r.get("name") or "")[:40],
               "match": tuple(str(m).lower() for m in r.get("match") or ()),
               "off": dict(r.get("off") or {}),
               "on": dict(r.get("on") or {})}
        if not row["match"]:
            continue
        k = row["name"].lower()
        if k and k in by_name:
            out[by_name[k]] = row
        else:
            by_name[k] = len(out)
            out.append(row)
    return out


def load_reasoning_config(force=False):
    """Merge config/reasoning.json into the tables. Called once, lazily."""
    global REASONING_FAMILIES, REASONING_ROUTERS
    if _REASONING_CONF_LOADED[0] and not force:
        return
    _REASONING_CONF_LOADED[0] = True
    try:
        path = os.environ.get("WEAVER_REASONING_CONF") or _reasoning_conf_path()
        if not os.path.isfile(path):
            return
        with open(path, encoding="utf-8") as fh:
            conf = json.load(fh)
        if not isinstance(conf, dict):
            return
        REASONING_FAMILIES = _merge_rows(REASONING_FAMILIES,
                                         conf.get("families"))
        REASONING_ROUTERS = _merge_rows(REASONING_ROUTERS, conf.get("routers"))
    except Exception:
        pass                      # a bad file must never break a model call


def detect_reasoning_family(provider, base, model):
    """Return the REASONING_FAMILIES row matching this provider/base/model, or
    None for a plain (non-reasoning) or unlisted model. Matches on a case-folded
    haystack of all three, so detection works whether the family shows up in the
    provider name, the base URL, or the model id."""
    load_reasoning_config()
    hay = " ".join([(provider or ""), (base or ""), (model or "")]).lower()
    for fam in REASONING_FAMILIES:
        if any(tok in hay for tok in fam.get("match", ())):
            return fam
    return None


def _openrouter_reasoning(provider, base, model):
    """OpenRouter's own switch for hidden reasoning.

    The registry fragment below is each MODEL FAMILY's native parameter — what
    DeepSeek's own API accepts. Routed through OpenRouter, that parameter is not
    the one OpenRouter reads, so thinking stayed ON: measured in a real run, the
    model spent its budget reasoning in English and was cut off before it could
    emit `{"keep": …}`, and its reasoning reached the user's chat verbatim.
    OpenRouter reads `reasoning`, so send that too when the call is routed
    there. Sending both is deliberate: each endpoint reads the one it knows.
    WEAVER_THINKING=enabled turns reasoning back on for both."""
    load_reasoning_config()
    hay = " ".join([(provider or ""), (base or ""), (model or "")]).lower()
    think = os.environ.get("WEAVER_THINKING", "disabled").strip().lower()
    on = think in ("enabled", "on", "1", "true")
    out = {}
    for row in REASONING_ROUTERS:
        if any(tok in hay for tok in row.get("match", ())):
            out.update(row.get("on" if on else "off") or {})
    return out


def reasoning_payload(provider, base, model):
    """Return the payload fragment that switches a reasoning model's hidden
    thinking OFF (default) or ON, per its family in the registry. Returns {} for
    any non-reasoning / unlisted model, so those payloads stay byte-for-byte
    unchanged. Direction is controlled by WEAVER_THINKING (disabled by default,
    matching OpenClaw's default of thinking:{type:"disabled"})."""
    out = _openrouter_reasoning(provider, base, model)
    fam = detect_reasoning_family(provider, base, model)
    if not fam:
        return out
    think = os.environ.get("WEAVER_THINKING", "disabled").strip().lower()
    on = think in ("enabled", "on", "1", "true")
    out.update(fam["on"] if on else fam["off"])
    return out


# ── OFFLINE TEST MODEL (costs nothing, needs no key, makes no request) ──────
# Testing a fix used to mean a PAID live run: every round of diagnosis spent
# real credit, and a round that only proved "the call came back empty" spent it
# for nothing. With WEAVER_LLM=offline the whole pipeline runs end to end — the
# model-judgement paths included — against a deterministic stand-in.
#
# It answers JSON prompts in the SHAPE THE PROMPT ITSELF ASKS FOR: the caller
# always shows a template like {"keep":[1],"drop":[2]}, so the stand-in parses
# that template out of the prompt and fills it. No per-caller rules to keep in
# sync, so a new model call added later is covered the day it is written.
#
# It is a TEST DOUBLE: the text it writes is filler. It proves the wiring — who
# is asked, what comes back, which branch runs, what the document ends up
# containing — never the quality of the prose.
_OFFLINE_FILLER = (
    "هذه فقرةٌ من النموذج البديل لغرض الاختبار دون تكلفة. تشرح الفكرة "
    "المطروحة في القسم وتربطها بما قبلها، ثم تمهّد لما بعدها. "
)


def _offline_json_template(prompt):
    """Pull the JSON template the prompt is asking for and fill it in. Returns a
    JSON string, or None when the prompt is not asking for JSON."""
    txt = prompt or ""
    if "JSON" not in txt and "json" not in txt:
        return None
    best = None
    for i, ch in enumerate(txt):
        if ch != "{":
            continue
        depth = 0
        for j in range(i, len(txt)):
            if txt[j] == "{":
                depth += 1
            elif txt[j] == "}":
                depth -= 1
                if depth == 0:
                    cand = txt[i:j + 1]
                    try:
                        obj = json.loads(cand.replace("…", "").replace("...", ""))
                    except Exception:
                        break
                    if isinstance(obj, dict) and (best is None
                                                  or len(cand) > best[0]):
                        best = (len(cand), obj)
                    break
    if best is None:
        return None

    counter = [0]

    def fill(v, key=""):
        if isinstance(v, dict):
            return {k: fill(x, k) for k, x in v.items()}
        if isinstance(v, list):
            # keep the ELEMENT TYPE the template showed: a list of titles must
            # come back as strings, not as the integer placeholder.
            proto = v[0] if v else 1
            if isinstance(proto, str) and not proto.strip():
                proto = "نصّ"
            return [fill(proto, key)]
        if isinstance(v, bool):
            return v
        if isinstance(v, (int, float)):
            # sibling numeric slots get DISTINCT values, so a template like
            # {"keep":[1],"drop":[2]} does not answer with the same index twice.
            counter[0] += 1
            return counter[0]
        return f"قيمة اختبارية ({key})" if key else "قيمة اختبارية"
    return json.dumps(fill(best[1]), ensure_ascii=False)


def offline_llm_fn(prompt, system=None, temperature=0.7, max_tokens=None,
                   timeout=None, on_delta=None):
    """Deterministic stand-in for a real model. Never touches the network."""
    j = _offline_json_template(prompt)
    if j is not None:
        if on_delta:
            try:
                on_delta(j)
            except Exception:
                pass
        return j
    # prose: roughly one filler paragraph per 120 requested tokens, bounded
    try:
        n = max(1, min(int((max_tokens or 600) // 120), 12))
    except Exception:
        n = 4
    out = "\n\n".join(_OFFLINE_FILLER * 2 for _ in range(n))
    if on_delta:
        try:
            on_delta(out)
        except Exception:
            pass
    return out


def get_llm_fn():
    """Return llm_fn(prompt, system=None, temperature=0.7, max_tokens=None)->str
    built from config/.env. Returns None if no key is configured (callers must
    handle that by staying in placeholder mode)."""
    keysync.load_env()
    # WEAVER_LLM=offline → the free stand-in above. Checked BEFORE the key so a
    # test run can never reach the network or spend credit by accident.
    if os.environ.get("WEAVER_LLM", "").strip().lower() in ("offline", "mock",
                                                           "fake", "test"):
        return offline_llm_fn
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
        # an endpoint that already refused these switches never sees them again
        _rk = _reasoning_key(base, model)
        _extra_keys = [k for k in reasoning_payload(provider, base, model)
                       if k in payload]
        if _rk in _REASONING_REFUSED:
            for k in _extra_keys:
                payload.pop(k, None)
            _extra_keys = []
        body = json.dumps(payload).encode("utf-8")

        def _drop_reasoning_and_retry():
            """Strip the reasoning switches, remember, return the new body —
            or None when there was nothing to strip."""
            if not _extra_keys:
                return None
            _REASONING_REFUSED.add(_rk)
            _p = dict(payload)
            for k in _extra_keys:
                _p.pop(k, None)
            return json.dumps(_p).encode("utf-8")
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
                try:
                    _r0 = urllib.request.urlopen(_req, timeout=_to)
                except urllib.error.HTTPError as _he:
                    if _he.code in PROVIDER_REFUSAL_CODES:
                        record_provider_error(_he.code, getattr(_he, "reason", ""),
                                              "stream")
                    if _he.code not in (400, 422):
                        raise
                    _nb = _drop_reasoning_and_retry()
                    if _nb is None:
                        raise
                    _sp2 = dict(json.loads(_nb.decode("utf-8")))
                    _sp2["stream"] = True
                    _req = urllib.request.Request(
                        url, data=json.dumps(_sp2).encode("utf-8"),
                        headers=headers, method="POST")
                    _r0 = urllib.request.urlopen(_req, timeout=_to)
                with _r0 as r:
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
            # A reasoning model that emitted only hidden reasoning and no final
            # text. Promoting that to the answer IMMEDIATELY is what put English
            # chain-of-thought into a user's document («We need answer user: …»)
            # and what made a JSON call return prose. The promotion stays as a
            # last resort — returning nothing is worse — but it is marked, so
            # the retry loop below tries for a real answer first and only falls
            # back to it once every attempt is spent.
            _r = (msg.get("reasoning_content") or msg.get("reasoning")
                  or msg.get("reasoning_text") or "")
            return (_REASONING_MARK + _r) if (_r or "").strip() else ""

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
        _thought = ""
        for _i in range(_tries):
            req = urllib.request.Request(url, data=body, headers=headers,
                                         method="POST")
            # a network/timeout error propagates immediately (callers handle it,
            # and a big generation must not be retried into a multi-minute wait).
            # The ONE exception is a 400/422 while the reasoning switches are in
            # the payload: that is an endpoint saying it does not know them, so
            # they are dropped and the call is retried once, immediately, and
            # this endpoint is remembered. No table to maintain, no release to
            # wait for — and every other error still propagates untouched.
            try:
                _resp = urllib.request.urlopen(req, timeout=_to)
            except urllib.error.HTTPError as _he:
                if _he.code in PROVIDER_REFUSAL_CODES:
                    record_provider_error(_he.code, getattr(_he, "reason", ""),
                                          "call")
                if _he.code not in (400, 422):
                    raise
                _nb = _drop_reasoning_and_retry()
                if _nb is None:
                    raise
                body = _nb
                req = urllib.request.Request(url, data=body, headers=headers,
                                             method="POST")
                _resp = urllib.request.urlopen(req, timeout=_to)
            with _resp as r:
                data = json.loads(r.read().decode("utf-8"))
            content = _extract(data)
            if content.startswith(_REASONING_MARK):
                # hidden reasoning only — keep it aside and ask again
                _thought = content[len(_REASONING_MARK):]
                content = ""
            if content and content.strip():
                return content
            # EMPTY completion (provider quirk under load) → retry; empties come
            # back fast so this is cheap, and it is the one thing that otherwise
            # silently degrades rich generations to a thin fallback.
            last = content or ""
            if _i < _tries - 1:
                time.sleep(1.0 * (_i + 1))
        # every attempt produced no final text: the reasoning is all there is.
        return last or _thought

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
