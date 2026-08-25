"""
web/server_sync.py — web-side API-key sync (reference module)
============================================================
The web server uses config/keysync.py as the single source of truth, exactly
like the terminal. GET /api/settings reads from .env; POST /api/settings
writes via save_env(), so a key changed in the web UI instantly appears in the
terminal (and vice-versa).

Wire these handlers into the actual web server when the web UI is added.
"""

"""
أكواد ربط API Key في خادم الويب — WeaverCode
المصدر: web/server.py
"""

# ══════════════════════════════════════════════
# 1. _read_env — قراءة config/.env
# ══════════════════════════════════════════════
def _read_env() -> dict:
    env = {}
    f = WEAVER_ROOT / "config" / ".env"
    if f.exists():
        for line in f.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.strip().startswith("#"):
                k, _, v = line.partition("=")
                env[k.strip()] = v.strip()
    return env


def _write_env(updates: dict):
    f = WEAVER_ROOT / "config" / ".env"
    lines = f.read_text(encoding="utf-8").splitlines() if f.exists() else []
    for key, value in updates.items():
        done = False
        for i, line in enumerate(lines):
            if line.startswith(f"{key}=") or line.startswith(f"# {key}="):
                lines[i] = f"{key}={value}"
                done = True
                break
        if not done:
            lines.append(f"{key}={value}")
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text("\n".join(lines) + "\n", encoding="utf-8")


# ══════════════════════════════════════════════
# 2. _write_env — الكتابة في config/.env (من الويب → الطرفية)
# ══════════════════════════════════════════════
def _write_env(updates: dict):
    f = WEAVER_ROOT / "config" / ".env"
    lines = f.read_text(encoding="utf-8").splitlines() if f.exists() else []
    for key, value in updates.items():
        done = False
        for i, line in enumerate(lines):
            if line.startswith(f"{key}=") or line.startswith(f"# {key}="):
                lines[i] = f"{key}={value}"
                done = True
                break
        if not done:
            lines.append(f"{key}={value}")
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _stats() -> dict:
    """Placeholder stats (filled when the web UI is wired)."""
    return {}


# ══════════════════════════════════════════════
# 3. _api_status — حالة المفتاح (key_set)
# ══════════════════════════════════════════════
def _api_status() -> dict:
    env = _read_env()
    key = env.get("WEAVER_API_KEY", "").strip()
    return {
        "daemon": st.read_status(),
        "model": env.get("WEAVER_MODEL", "غير محدد"),
        "provider": env.get("WEAVER_BASE_URL", "").split("//")[-1].split("/")[0],
        "key_set": bool(key) and len(key) > 5 and "YOUR_" not in key.upper(),
        "stats": _stats(),
        "queue": len(st.read_queue()),
    }





# ═══════════════════════════════════════════════════════════
# Web endpoint: connect a custom provider (URL + key -> models list)
# ═══════════════════════════════════════════════════════════
def api_connect_custom_provider(payload: dict) -> dict:
    """
    POST /api/providers/custom
    Body: {"name","base_url","key","model"(optional)}
    Returns: {"name","base_url","models":[...],"model","error"}

    Same logic as the terminal's custom-provider flow, so the web UI and CLI
    behave identically. On success the key/model are written to config/.env,
    so the terminal instantly sees them too.
    """
    import sys, os
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if root not in sys.path:
        sys.path.insert(0, root)
    from config import providers
    from config.keysync import set_api_key

    base_url = (payload.get("base_url") or "").strip()
    key = (payload.get("key") or "").strip()
    name = (payload.get("name") or "custom").strip()
    model = (payload.get("model") or "").strip()
    if not base_url or not key:
        return {"error": "base_url and key are required", "models": []}

    res = providers.connect_custom_provider(base_url, key, name=name, model=model)
    if not res.get("error") and res.get("model"):
        # sync to .env so the terminal sees it
        set_api_key(key, provider=res["name"], base_url=res["base_url"],
                    model=res["model"])
    return res


def api_list_models(payload: dict) -> dict:
    """
    POST /api/providers/models
    Body: {"base_url","key","auth"(optional)}
    Returns: {"models":[...],"error"}
    Lets the web UI populate a model dropdown for any platform.
    """
    import sys, os
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if root not in sys.path:
        sys.path.insert(0, root)
    from config import providers
    models, err = providers.list_models_for(
        payload.get("base_url", ""), payload.get("key", ""),
        payload.get("auth", "bearer"))
    return {"models": models, "error": err}
