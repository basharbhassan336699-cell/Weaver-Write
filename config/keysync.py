"""
config/keysync.py — API-key sync between terminal and web (working)
==================================================================
Single source of truth for the API key and provider settings:

    config/.env  ←→  WEAVER_API_KEY, WEAVER_BASE_URL, WEAVER_MODEL, ...

The terminal (weaver.py) and the web UI (web/server.py) both read and write
this one file, so changing the key in EITHER place updates the other:

  terminal → web:  `weaver keys change` writes .env → the web UI reads the
                   new key on its next GET /api/settings.
  web → terminal:  the web UI's save writes the same .env → the terminal's
                   reload_env() (or next start) picks it up.

Providers and platform auto-detection come from config/providers.py (17
providers + prefix/probe detection), extensible via config/providers.json.

Refined for Weaver Write: WEAVER_* keys, config/ paths, single-key operation
(one AI key runs the whole system; PaperQA uses local embeddings).
"""
from __future__ import annotations
import os
from pathlib import Path

_CONF_DIR = Path(__file__).resolve().parent
_ENV_FILE = _CONF_DIR / ".env"

# the settings kept in sync between terminal and web (source of truth = .env)
SYNC_KEYS = ("WEAVER_API_KEY", "WEAVER_BASE_URL", "WEAVER_MODEL",
             "WEAVER_MAX_TOKENS", "WEAVER_TEMPERATURE", "WEAVER_PROVIDER")


# ── load .env at startup ─────────────────────────────────────
def load_env():
    """
    Load config/.env into os.environ if present. Uses setdefault so real
    environment variables and CLI flags keep priority over the file.
    Supports 'export KEY=VALUE' and quoted values.
    """
    if not _ENV_FILE.exists():
        return
    for raw in _ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[len("export "):].strip()
        key, _, val = line.partition("=")
        key, val = key.strip(), val.strip()
        if len(val) >= 2 and val[0] == val[-1] and val[0] in ("'", '"'):
            val = val[1:-1]
        if key:
            os.environ.setdefault(key, val)


# ── write updates back to .env (atomic-ish) ──────────────────
def save_env(updates: dict) -> None:
    """
    Merge `updates` into config/.env and into os.environ, preserving other
    lines/comments. This is what makes terminal and web stay in sync: whoever
    writes, both read the same file afterward.
    """
    _CONF_DIR.mkdir(parents=True, exist_ok=True)
    existing = {}
    order = []
    if _ENV_FILE.exists():
        for raw in _ENV_FILE.read_text(encoding="utf-8").splitlines():
            s = raw.strip()
            if not s or s.startswith("#") or "=" not in s:
                order.append(("raw", raw))
                continue
            line = s[len("export "):].strip() if s.startswith("export ") else s
            k, _, v = line.partition("=")
            k = k.strip()
            existing[k] = v.strip()
            order.append(("kv", k))

    for k, v in updates.items():
        if k not in existing:
            order.append(("kv", k))
        existing[k] = str(v)

    lines = []
    seen = set()
    for kind, payload in order:
        if kind == "raw":
            lines.append(payload)
        else:
            k = payload
            if k in seen:
                continue
            seen.add(k)
            lines.append(f"{k}={existing[k]}")
    # any brand-new keys not already appended
    for k in existing:
        if k not in seen:
            lines.append(f"{k}={existing[k]}")

    tmp = _ENV_FILE.with_suffix(".env.tmp")
    tmp.write_text("\n".join(lines) + "\n", encoding="utf-8")
    os.replace(tmp, _ENV_FILE)
    try:
        os.chmod(_ENV_FILE, 0o600)  # keep the key private
    except Exception:
        pass

    # reflect immediately in this process
    for k, v in updates.items():
        os.environ[k] = str(v)


def reload_env() -> dict:
    """Re-read .env fresh (used by the terminal to pick up web-side changes)."""
    result = {}
    if not _ENV_FILE.exists():
        return result
    for raw in _ENV_FILE.read_text(encoding="utf-8").splitlines():
        s = raw.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        line = s[len("export "):].strip() if s.startswith("export ") else s
        k, _, v = line.partition("=")
        k, v = k.strip(), v.strip()
        if len(v) >= 2 and v[0] == v[-1] and v[0] in ("'", '"'):
            v = v[1:-1]
        if k:
            result[k] = v
            os.environ[k] = v
    return result


# ── provider detection (delegates to config/providers.py) ────
def detect_provider(key: str):
    """
    Detect the platform from an API key: returns (base_url, model, name) or
    None. Uses prefix match first (offline); the web/terminal can additionally
    probe /models via providers.resolve_platform when a network call is ok.
    """
    try:
        from config import providers
    except Exception:
        try:
            import providers  # fallback if run in-dir
        except Exception:
            return None
    e = providers.detect_by_prefix(key)
    if e:
        return (e["base_url"], e.get("model", ""), e["name"])
    return None


def set_api_key(key: str, provider: str = "", base_url: str = "",
                model: str = "") -> dict:
    """
    High-level: set the API key and (auto-detected) provider settings, writing
    them to .env so BOTH terminal and web see them. Returns the applied dict.
    """
    updates = {"WEAVER_API_KEY": key}
    detected = detect_provider(key)
    if detected:
        d_url, d_model, d_name = detected
        updates["WEAVER_BASE_URL"] = base_url or d_url
        updates["WEAVER_MODEL"] = model or d_model
        updates["WEAVER_PROVIDER"] = provider or d_name
    else:
        if base_url:
            updates["WEAVER_BASE_URL"] = base_url
        if model:
            updates["WEAVER_MODEL"] = model
        if provider:
            updates["WEAVER_PROVIDER"] = provider
    save_env(updates)
    return updates


def get_settings() -> dict:
    """Return the current synced settings (read fresh from .env)."""
    reload_env()
    return {k: os.environ.get(k, "") for k in SYNC_KEYS}


if __name__ == "__main__":
    # demo (no network): set a fake key and show sync file behavior
    print("Before:", get_settings())
    set_api_key("sk-ant-demo1234567890", provider="", base_url="", model="")
    print("After set:", get_settings())
    print(f"\n.env written at: {_ENV_FILE}")
