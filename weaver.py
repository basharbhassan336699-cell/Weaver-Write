#!/usr/bin/env python3
"""
weaver — Weaver Write command-line interface
============================================
First-run interface: shows a pixel-style banner, then guides the user through
quick install or restoring a previous account, API-key setup, and finally
prints the (unique) local web-UI URL.

Cross-platform: works on Termux/Android, Windows PowerShell/Terminal, macOS,
and Linux. Pure-Python (only the standard library for the CLI itself).

Subcommands:
  weaver install        quick setup (or restore a previous account)
  weaver keys           add / change / show API keys
  weaver serve          start the local web UI
  weaver restore        restore state after a shutdown
  weaver doctor         diagnose problems and suggest fixes
  weaver update         pull latest and reinstall deps
  weaver version
"""
from __future__ import annotations
import os
import sys
import json
import argparse

# ── paths ────────────────────────────────────────────────────
HOME = os.path.expanduser("~")
CONF_DIR = os.path.join(HOME, ".weaver-write")
CONF_FILE = os.path.join(CONF_DIR, "config.json")
KEYS_FILE = os.path.join(CONF_DIR, "keys.json")

# unique local port for Weaver Write (different from WeaverCode/CoBWeaverClaw)
WEB_PORT = 8848
WEB_URL = f"http://127.0.0.1:{WEB_PORT}"

ORANGE = "\033[38;5;208m"
DIM = "\033[2m"
BOLD = "\033[1m"
RESET = "\033[0m"


# ── pixel banner (matches the WEAVER logo style) ─────────────
_BANNER = r"""
{o}██     ██ ███████  █████  ██    ██ ███████ ██████ {r}
{o}██     ██ ██      ██   ██ ██    ██ ██      ██   ██{r}
{o}██  █  ██ █████   ███████ ██    ██ █████   ██████ {r}
{o}██ ███ ██ ██      ██   ██  ██  ██  ██      ██   ██{r}
{o} ███ ███  ███████ ██   ██   ████   ███████ ██   ██{r}
"""


def _supports_color():
    return sys.stdout.isatty() and os.environ.get("TERM") != "dumb"


def banner():
    o, r = (ORANGE, RESET) if _supports_color() else ("", "")
    print(_BANNER.format(o=o, r=r))
    b = BOLD if _supports_color() else ""
    print(f"        {b}Hello — Weaver Write{r}\n")


# ── config helpers ───────────────────────────────────────────
def _ensure_dir():
    os.makedirs(CONF_DIR, exist_ok=True)


def load_config():
    try:
        with open(CONF_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_config(cfg):
    _ensure_dir()
    with open(CONF_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


def load_keys():
    try:
        with open(KEYS_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_keys(keys):
    _ensure_dir()
    with open(KEYS_FILE, "w", encoding="utf-8") as f:
        json.dump(keys, f, ensure_ascii=False, indent=2)
    try:
        os.chmod(KEYS_FILE, 0o600)  # keep keys private
    except Exception:
        pass


def _ask(prompt, default=None):
    suffix = f" [{default}]" if default else ""
    try:
        val = input(f"{prompt}{suffix}: ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return default
    return val or default


def _choose(prompt, options):
    print(prompt)
    for i, opt in enumerate(options, 1):
        print(f"  {i}) {opt}")
    while True:
        c = _ask("Choose")
        if c and c.isdigit() and 1 <= int(c) <= len(options):
            return int(c) - 1
        if c is None:
            return 0


# ── commands ─────────────────────────────────────────────────
def cmd_install(args):
    banner()
    # 1) quick install or restore
    choice = _choose("Quick install, or restore a previous account?",
                     ["Quick install (fresh)",
                      "Restore a previous account"])
    cfg = load_config()
    if choice == 1:
        token = _ask("Paste your restore token / account ID")
        cfg["account"] = token or "restored"
        cfg["restored"] = True
        print("Restoring your previous account and settings...")
    else:
        cfg["account"] = "local"
        cfg["restored"] = False
        print("Setting up a fresh Weaver Write install...")
    save_config(cfg)

    # 2) API keys
    setup_keys = _choose("Set up your API key now?",
                         ["Yes, add my key", "Skip for now"])
    if setup_keys == 0:
        _do_add_key()

    # 3) show the web UI URL (unique to Weaver Write)
    print("\n" + "-" * 48)
    print(f"{BOLD if _supports_color() else ''}Setup complete.{RESET if _supports_color() else ''}")
    print(f"Your Weaver Write web interface:\n    {WEB_URL}")
    print("Start it any time with:  weaver serve")
    print("-" * 48)


def _do_add_key():
    keys = load_keys()
    provider = _choose("Which provider is your AI key for?",
                       ["Anthropic (Claude)", "OpenAI", "DeepSeek",
                        "Other / custom (enter platform URL)"])
    names = ["anthropic", "openai", "deepseek", "custom"]
    if provider == 3:
        return _do_add_custom_provider()
    key = _ask(f"Paste your {names[provider]} API key")
    if key:
        keys[names[provider]] = key
        keys["active"] = names[provider]
        save_keys(keys)
        # ALSO write to config/.env so the WEB UI sees the same key (sync)
        try:
            import sys as _sys, os as _os
            _here = _os.path.dirname(_os.path.abspath(__file__))
            if _here not in _sys.path:
                _sys.path.insert(0, _here)
            from config.keysync import set_api_key
            applied = set_api_key(key, provider=names[provider])
            prov = applied.get("WEAVER_PROVIDER", names[provider])
            print(f"Saved. Weaver Write will run on your {prov} key "
                  f"(synced to the web UI).")
        except Exception:
            print(f"Saved. Weaver Write will run on your {names[provider]} key.")
    else:
        print("No key entered — you can add one later with:  weaver keys add")


def _do_add_custom_provider():
    """Connect any provider outside the built-in list: URL + key, then pick a
    model from the platform's auto-detected list."""
    import sys as _sys, os as _os
    _here = _os.path.dirname(_os.path.abspath(__file__))
    if _here not in _sys.path:
        _sys.path.insert(0, _here)

    name = _ask("Give this provider a short name", "custom") or "custom"
    base_url = _ask("Platform API base URL (e.g. https://api.example.com/v1)")
    if not base_url:
        print("No URL entered — cancelled.")
        return
    key = _ask("Paste the API key for this platform")
    if not key:
        print("No key entered — cancelled.")
        return

    print("Detecting available models from the platform...")
    try:
        from config import providers
        res = providers.connect_custom_provider(base_url, key, name=name)
    except Exception as e:
        print(f"Could not connect: {e}")
        return

    if res.get("error") or not res.get("models"):
        print(f"Couldn't list models ({res.get('error', 'unknown')}).")
        model = _ask("Enter the model name to use manually (optional)")
        res["model"] = model or ""
        if not model:
            return
    else:
        models = res["models"]
        print(f"Found {len(models)} models.")
        shown = models[:30]
        idx = _choose("Choose the model to use:", shown)
        res["model"] = shown[idx]

    try:
        from config.keysync import set_api_key
        set_api_key(key, provider=res["name"], base_url=res["base_url"],
                    model=res["model"])
        keys = load_keys()
        keys[res["name"]] = key
        keys["active"] = res["name"]
        save_keys(keys)
        print(f"Connected '{res['name']}' with model '{res['model']}' "
              f"(synced to the web UI).")
    except Exception as e:
        print(f"Saved detection, but sync failed: {e}")


def cmd_keys(args):
    action = args.action or "show"
    keys = load_keys()
    if action == "add":
        _do_add_key()
    elif action == "change":
        _do_add_key()  # same flow overwrites
        print("Key changed.")
    elif action == "show":
        # also show the synced provider/model from .env
        try:
            from config.keysync import get_settings
            s = get_settings()
            if s.get("WEAVER_PROVIDER"):
                print(f"  synced provider: {s['WEAVER_PROVIDER']} "
                      f"(model: {s.get('WEAVER_MODEL','?')})")
        except Exception:
            pass
        if not keys:
            print("No keys stored yet. Add one with:  weaver keys add")
        else:
            active = keys.get("active", "?")
            for name, val in keys.items():
                if name == "active":
                    continue
                masked = (val[:4] + "…" + val[-4:]) if len(val) > 8 else "…"
                star = " (active)" if name == active else ""
                print(f"  {name}: {masked}{star}")
    elif action == "remove":
        prov = _ask("Which provider key to remove")
        if prov in keys:
            del keys[prov]
            save_keys(keys)
            print(f"Removed {prov}.")


def cmd_serve(args):
    """Start the local web UI (serves web/index.html + API, synced with .env)."""
    port = args.port or WEB_PORT
    here = os.path.dirname(os.path.abspath(__file__))
    if here not in sys.path:
        sys.path.insert(0, here)
    try:
        from web.server import serve
        serve(port)
    except ImportError:
        # fallback: static file server if web.server isn't importable
        webdir = os.path.join(here, "web")
        if os.path.isdir(webdir):
            import http.server, socketserver, functools
            handler = functools.partial(http.server.SimpleHTTPRequestHandler,
                                        directory=webdir)
            with socketserver.TCPServer(("127.0.0.1", port), handler) as httpd:
                print(f"Weaver Write web UI at http://127.0.0.1:{port}")
                print("Press Ctrl+C to stop.")
                try:
                    httpd.serve_forever()
                except KeyboardInterrupt:
                    print("\nStopped.")
        else:
            print(f"No web/ directory found at {webdir}")

def cmd_restore(args):
    """Restore running state after a device shutdown."""
    cfg = load_config()
    print("Restoring Weaver Write state...")
    # re-open the memory DB, re-check services; safe no-ops if absent
    db = os.environ.get("WEAVER_DB", os.path.join(CONF_DIR, "weaver_memory.db"))
    print(f"  memory DB: {db} {'(found)' if os.path.exists(db) else '(will be created)'}")
    print(f"  account: {cfg.get('account', 'local')}")
    print("State restored. Start the UI with:  weaver serve")


def cmd_doctor(args):
    """Diagnose common problems and suggest fixes."""
    banner()
    print("Running diagnostics...\n")
    problems = 0

    # python version
    v = sys.version_info
    ok = v >= (3, 9)
    print(f"[{'OK' if ok else 'X'}] Python {v.major}.{v.minor} "
          f"({'>=3.9' if ok else 'need >= 3.9'})")
    problems += 0 if ok else 1

    # key present
    keys = load_keys()
    has_key = bool(keys) and keys.get("active")
    print(f"[{'OK' if has_key else 'X'}] API key "
          f"({'configured' if has_key else 'missing — run: weaver keys add'})")
    problems += 0 if has_key else 1

    # core python deps
    for mod in ["docx", "pptx", "openpyxl", "matplotlib"]:
        try:
            __import__(mod)
            print(f"[OK] {mod}")
        except ImportError:
            print(f"[X] {mod} missing — run: weaver install-deps")
            problems += 1

    # optional services
    for svc, env in [("SearXNG (web search)", "WEAVER_SEARXNG_URL"),
                     ("Tesseract (OCR)", None)]:
        val = os.environ.get(env) if env else None
        if env and not val:
            print(f"[--] {svc}: not configured (optional)")

    print(f"\n{problems} problem(s) found." if problems else
          "\nAll good — no problems found.")


def cmd_version(args):
    print("Weaver Write 1.0")


def build_parser():
    p = argparse.ArgumentParser(prog="weaver",
                                description="Weaver Write CLI")
    sub = p.add_subparsers(dest="command")

    sub.add_parser("install", help="quick setup or restore an account")

    kp = sub.add_parser("keys", help="manage API keys")
    kp.add_argument("action", nargs="?",
                    choices=["add", "change", "show", "remove"], default="show")

    sp = sub.add_parser("serve", help="start the local web UI")
    sp.add_argument("--port", type=int, default=None)

    sub.add_parser("restore", help="restore state after shutdown")
    sub.add_parser("doctor", help="diagnose and fix problems")
    sub.add_parser("version", help="show version")
    return p


def main(argv=None):
    # load synced settings from config/.env first (shared with the web UI)
    try:
        import sys as _s, os as _o
        _h = _o.path.dirname(_o.path.abspath(__file__))
        if _h not in _s.path:
            _s.path.insert(0, _h)
        from config.keysync import load_env
        load_env()
    except Exception:
        pass
    parser = build_parser()
    args = parser.parse_args(argv)
    cmd = args.command
    if cmd == "install":
        cmd_install(args)
    elif cmd == "keys":
        cmd_keys(args)
    elif cmd == "serve":
        cmd_serve(args)
    elif cmd == "restore":
        cmd_restore(args)
    elif cmd == "doctor":
        cmd_doctor(args)
    elif cmd == "version":
        cmd_version(args)
    else:
        # no subcommand -> show banner + install flow
        cmd_install(args)


if __name__ == "__main__":
    main()
