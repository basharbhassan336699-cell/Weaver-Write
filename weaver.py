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
QUESTION = "\033[38;5;173m"   # earthy terracotta orange for question titles
CARET = "\033[38;5;215m"      # highlighted (selected) option
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


def banner(clear=True):
    if clear:
        _clear()
    o, r = (ORANGE, RESET) if _supports_color() else ("", "")
    rule = "═" * 50
    print(f"{o}{rule}{r}")
    print(_BANNER.format(o=o, r=r))
    b = BOLD if _supports_color() else ""
    print(f"        {b}Hello — Weaver Write{r}")
    print(f"{o}{rule}{r}\n")


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


# ── interactive core ─────────────────────────────────────────
# Works even under `curl | bash` (stdin is the pipe): reads the controlling
# terminal /dev/tty directly, so questions are answerable and the key can be
# typed. One question at a time on a cleared screen, with back navigation.
def _clear():
    if _supports_color():
        try:
            sys.stdout.write("\033[2J\033[3J\033[H")
            sys.stdout.flush()
        except Exception:
            pass


_TTY = None
def _tty():
    """Controlling-terminal fd (int), or False if unavailable. Prefers stdin
    when it's already a terminal (direct run), otherwise opens /dev/tty — so
    prompts work both directly and under `curl | bash` (stdin is a pipe)."""
    global _TTY
    if _TTY is None:
        _TTY = False
        try:
            if os.isatty(0):
                _TTY = 0
        except Exception:
            pass
        if _TTY is False:
            try:
                _TTY = os.open("/dev/tty", os.O_RDWR | os.O_NOCTTY)
            except Exception:
                _TTY = False
    return _TTY


def cmd_diag(args):
    """Print why the interactive menu is or isn't available (for support)."""
    import platform
    print("Weaver Write — interactive diagnostics")
    print(f"  platform     : {platform.system()} / {platform.machine()}")
    print(f"  python       : {sys.version.split()[0]}")
    print(f"  stdout.isatty: {sys.stdout.isatty()}")
    print(f"  stdin.isatty : {os.isatty(0) if hasattr(os,'isatty') else '?'}")
    print(f"  TERM         : {os.environ.get('TERM')!r}")
    print(f"  supports_color: {_supports_color()}")
    tty = _tty()
    print(f"  tty fd       : {tty!r}")
    try:
        import termios, tty as _t  # noqa: F401
        print("  termios/tty  : available")
    except Exception as e:
        print(f"  termios/tty  : MISSING ({e})")
    print(f"  interactive  : {_interactive()}  "
          f"({'arrow-key menu' if _interactive() else 'numbered fallback'})")


def _interactive():
    """True when an arrow-key menu can be driven on this terminal."""
    if not _supports_color() or _tty() is False:
        return False
    try:
        import termios  # noqa: F401
        import tty  # noqa: F401
    except Exception:
        return False
    return True


def _read_key(fd):
    """Read one keypress from tty fd in cbreak mode. Returns
    'up'/'down'/'right'/'back'/'enter'/'esc' or the literal character.
    Uses raw os.read on the fd — robust on Termux/Android."""
    import termios, tty as _ttymod
    old = termios.tcgetattr(fd)
    try:
        _ttymod.setcbreak(fd)
        b = os.read(fd, 1)
        if b == b"\x1b":
            rest = os.read(fd, 2)
            return {b"[A": "up", b"[B": "down", b"[C": "right",
                    b"[D": "back"}.get(rest, "esc")
        if b in (b"\r", b"\n"):
            return "enter"
        if b in (b"\x7f", b"\x08"):
            return "back"
        if b in (b"\x03", b"\x04"):
            raise KeyboardInterrupt
        return b.decode("utf-8", "ignore")
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)


def _menu(title, options, allow_back=False, hint=None):
    """Arrow-key menu: earthy-orange title, caret on the highlighted option,
    the WEAVER banner and a cleared screen on every question. Returns the
    chosen index, or 'BACK'."""
    if not _interactive():
        return _menu_numeric(title, options, allow_back, hint)
    fd = _tty()
    sel = 0
    while True:
        banner()
        print(f"{QUESTION}{BOLD}{title}{RESET}\n")
        for i, opt in enumerate(options):
            if i == sel:
                print(f"  {CARET}▸ {opt}{RESET}")
            else:
                print(f"    {DIM}{opt}{RESET}")
        nav = "↑/↓ move · Enter select"
        if allow_back:
            nav += " · ← back"
        print(f"\n{DIM}{nav}{RESET}")
        if hint:
            print(f"{DIM}{hint}{RESET}")
        sys.stdout.flush()
        try:
            k = _read_key(fd)
        except KeyboardInterrupt:
            print()
            sys.exit(0)
        except Exception:
            return _menu_numeric(title, options, allow_back, hint)
        if k == "up":
            sel = (sel - 1) % len(options)
        elif k == "down":
            sel = (sel + 1) % len(options)
        elif k == "enter":
            return sel
        elif k == "back" and allow_back:
            return "BACK"
        elif k and k.isdigit() and 1 <= int(k) <= len(options):
            return int(k) - 1


def _menu_numeric(title, options, allow_back=False, hint=None):
    """Fallback when arrow keys aren't available — still shows the banner and
    the earthy-orange title so the look is consistent."""
    banner()
    if _supports_color():
        print(f"{QUESTION}{BOLD}{title}{RESET}\n")
    else:
        print(f"\n{title}")
    for i, opt in enumerate(options, 1):
        print(f"  {i}) {opt}")
    if allow_back:
        print("  b) ← back")
    if hint:
        print(f"{DIM}{hint}{RESET}" if _supports_color() else f"  {hint}")
    while True:
        c = _prompt_line("Choose")
        if c is None:
            return 0
        c = c.strip().lower()
        if allow_back and c in ("b", "back"):
            return "BACK"
        if c.isdigit() and 1 <= int(c) <= len(options):
            return int(c) - 1


def _prompt_line(prompt, default=None):
    """Read a line from the controlling terminal (falls back to stdin)."""
    suffix = f" [{default}]" if default else ""
    msg = (f"{QUESTION}{prompt}{RESET}{suffix}: " if _supports_color()
           else f"{prompt}{suffix}: ")
    fd = _tty()
    if fd is not False:
        try:
            os.write(fd, msg.encode("utf-8", "replace"))
            data = os.read(fd, 4096)
            if data == b"":
                raise EOFError
            return data.decode("utf-8", "replace").strip() or default
        except (EOFError, KeyboardInterrupt):
            print()
            return default
        except Exception:
            pass
    try:
        return input(msg).strip() or default
    except (EOFError, KeyboardInterrupt):
        print()
        return default


def _ask(prompt, default=None):
    return _prompt_line(prompt, default)


def _choose(prompt, options):
    r = _menu(prompt, options)
    return 0 if r == "BACK" else r


# ── commands ─────────────────────────────────────────────────
def cmd_install(args):
    _clear()
    cfg = load_config()
    st = {}
    step = "type"
    # step machine so ← back can revisit an earlier question
    while True:
        if step == "type":
            st["type"] = _menu("Quick install, or restore a previous account?",
                               ["Quick install (fresh)",
                                "Restore a previous account"])
            step = "restore" if st["type"] == 1 else "key_yesno"
        elif step == "restore":
            st["token"] = _prompt_line("Paste your restore token / account ID")
            step = "key_yesno"
        elif step == "key_yesno":
            r = _menu("Set up your AI API key now?",
                      ["Yes, add my key", "Skip for now"], allow_back=True)
            if r == "BACK":
                step = "type"
                continue
            step = "provider" if r == 0 else "finish"
        elif step == "provider":
            r = _select_provider_and_key(allow_back=True)
            if r == "BACK":
                step = "key_yesno"
                continue
            step = "finish"
        elif step == "finish":
            break

    if st.get("type") == 1:
        cfg["account"] = st.get("token") or "restored"
        cfg["restored"] = True
    else:
        cfg["account"] = "local"
        cfg["restored"] = False
    save_config(cfg)

    # final screen
    banner()
    b, r = (BOLD, RESET) if _supports_color() else ("", "")
    print(f"{b}Setup complete.{r}\n")
    print(f"Your Weaver Write web interface:\n    {ORANGE}{WEB_URL}{r}\n")
    print(f"{DIM}Note: the link only opens while the server is running.{r}")
    go = _menu("Open the web interface now?",
               ["Start it now", "Later (run:  weaver serve)"])
    if go == 0 and _tty():
        print(f"\nStarting… open {WEB_URL} in your browser. Press Ctrl+C to stop.\n")
        cmd_serve(args)
    else:
        print("\nStart it any time with:  weaver serve")


# friendly labels for the built-in provider registry
_PROVIDER_LABELS = {
    "anthropic": "Anthropic (Claude)", "openai": "OpenAI (GPT)",
    "deepseek": "DeepSeek", "google": "Google Gemini",
    "groq": "Groq (fast, free tier)", "openrouter": "OpenRouter (many models)",
    "mistral": "Mistral", "xai": "xAI (Grok)", "perplexity": "Perplexity",
    "together": "Together AI", "fireworks": "Fireworks AI",
    "cerebras": "Cerebras", "nvidia": "NVIDIA NIM", "ollama": "Ollama (local)",
}


def _do_add_key():
    _select_provider_and_key()


def _select_provider_and_key(allow_back=False):
    """List every provider in the registry (plus a custom option), take the
    key, auto-detect the model, and save it (synced to the web UI).
    Returns True on success, False on cancel, or 'BACK'."""
    import sys as _sys, os as _os
    _here = _os.path.dirname(_os.path.abspath(__file__))
    if _here not in _sys.path:
        _sys.path.insert(0, _here)
    try:
        from config import providers as _P
        registry = _P.load_registry()
    except Exception:
        registry = [{"name": n} for n in ("anthropic", "openai", "deepseek")]

    names = [p["name"] for p in registry]
    labels = [_PROVIDER_LABELS.get(n, n) for n in names]
    labels.append("Other / custom (enter platform URL)")
    idx = _menu("Which provider is your AI key for?", labels, allow_back=allow_back,
                hint="Any OpenAI-compatible platform works — pick “Other / custom” "
                     "for anything not listed.")
    if idx == "BACK":
        return "BACK"
    if idx == len(labels) - 1:
        return bool(_do_add_custom_provider())
    return _connect_named_provider(names[idx],
                                   registry[idx].get("base_url", ""))


def _connect_named_provider(name, base_url):
    key = _prompt_line(f"Paste your {name} API key")
    if not key:
        print("No key entered — you can add one later with:  weaver keys add")
        return False
    model = ""
    try:
        from config import providers as _P
        res = _P.connect_custom_provider(base_url, key, name=name)
        models = res.get("models") or []
        if models:
            shown = models[:30]
            mi = _menu(f"Choose the model for {name}:", shown, allow_back=True)
            model = res.get("model", shown[0]) if mi == "BACK" else shown[mi]
        else:
            model = res.get("model", "")
    except Exception:
        model = ""
    try:
        from config.keysync import set_api_key
        applied = set_api_key(key, provider=name, base_url=base_url, model=model)
        prov = applied.get("WEAVER_PROVIDER", name)
        mdl = applied.get("WEAVER_MODEL") or "(auto)"
        _remember_key(name, key)
        print(f"Saved. Weaver Write will run on your {prov} key "
              f"(model: {mdl}, synced to the web UI).")
    except Exception:
        _remember_key(name, key)
        print(f"Saved your {name} key.")
    return True


def _remember_key(name, key):
    keys = load_keys()
    keys[name] = key
    keys["active"] = name
    save_keys(keys)


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
        return False
    key = _ask("Paste the API key for this platform")
    if not key:
        print("No key entered — cancelled.")
        return False

    print("Detecting available models from the platform...")
    try:
        from config import providers
        res = providers.connect_custom_provider(base_url, key, name=name)
    except Exception as e:
        print(f"Could not connect: {e}")
        return False

    if res.get("error") or not res.get("models"):
        print(f"Couldn't list models ({res.get('error', 'unknown')}).")
        model = _ask("Enter the model name to use manually (optional)")
        res["model"] = model or ""
        if not model:
            return False
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
        return True
    except Exception as e:
        print(f"Saved detection, but sync failed: {e}")
        return False


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
    port = getattr(args, "port", None) or WEB_PORT
    here = os.path.dirname(os.path.abspath(__file__))
    if here not in sys.path:
        sys.path.insert(0, here)
    import errno
    try:
        try:
            from web.server import serve
            serve(port)
        except ImportError:
            # fallback: static file server if web.server isn't importable
            webdir = os.path.join(here, "web")
            if not os.path.isdir(webdir):
                print(f"No web/ directory found at {webdir}")
                return
            import http.server, socketserver, functools
            handler = functools.partial(http.server.SimpleHTTPRequestHandler,
                                        directory=webdir)
            class _Reuse(socketserver.TCPServer):
                allow_reuse_address = True
            with _Reuse(("127.0.0.1", port), handler) as httpd:
                print(f"Weaver Write web UI at http://127.0.0.1:{port}")
                print("Press Ctrl+C to stop.")
                httpd.serve_forever()
    except OSError as e:
        if e.errno in (errno.EADDRINUSE, 98):
            print(f"\nWeaver Write is already running at http://127.0.0.1:{port}")
            print("Open that address in your browser.")
            print(f"To stop it:  pkill -f weaver.py   (then run: weaver serve)")
        else:
            print(f"Could not start the web server: {e}")
    except KeyboardInterrupt:
        print("\nStopped.")

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


def _load_chat():
    """Import the shared chat function used by the web server."""
    here = os.path.dirname(os.path.abspath(__file__))
    if here not in sys.path:
        sys.path.insert(0, here)
    from web.server import _chat
    return _chat


def cmd_test(args):
    """End-to-end self-test of the AI connection, straight from the terminal —
    shows exactly why a reply would fail (no key / bad key / no credit / net)."""
    banner()
    try:
        from config.keysync import get_settings
        s = get_settings()
    except Exception as e:
        print(f"Could not read settings: {e}")
        return
    key = s.get("WEAVER_API_KEY", "")
    masked = (key[:4] + "…" + key[-4:]) if len(key) > 8 else ("(none)" if not key else "…")
    print("Connection check")
    print(f"  key      : {masked}")
    print(f"  provider : {s.get('WEAVER_PROVIDER') or '(none)'}")
    print(f"  model    : {s.get('WEAVER_MODEL') or '(none)'}")
    print(f"  base url : {s.get('WEAVER_BASE_URL') or '(none)'}")
    if not key:
        print("\n>>> No API key set. Add one with:  weaver keys add")
        return
    if not s.get("WEAVER_BASE_URL"):
        print("\n>>> No provider URL. Re-add your key:  weaver keys add")
        return
    print("\nContacting the provider (say 'OK')…")
    try:
        chat = _load_chat()
    except Exception as e:
        print(f"Could not load chat module: {e}")
        return
    r = chat("Reply with just: OK", timeout=60)
    if r.get("error"):
        print(f"\n>>> FAILED: {r.get('error')}")
        if r.get("message"):
            print(f"    {r.get('message')}")
        print("\nWhat it means:")
        print("  http_error 401/403 -> the API key is wrong or revoked")
        print("  http_error 402/429 -> no credit / rate limited on the provider")
        print("  request_failed     -> no internet, or the provider URL is wrong")
        print("  no_key/no_provider -> add your key again:  weaver keys add")
    else:
        print(f"\n>>> SUCCESS. Provider replied: {(r.get('reply') or '').strip()[:200]}")
        print("The AI connection works. If the web UI shows nothing, restart it:")
        print("  pkill -f weaver.py ; weaver serve   (then hard-refresh the page)")


def cmd_ask(args):
    """Ask the model from the terminal — routed through the FULL pipeline
    (WeaverOrchestrator): understand → route → research → write → clean →
    verify → export. Any output file is written to the project's outputs/."""
    q = " ".join(args.text) if getattr(args, "text", None) else ""
    if not q:
        q = _prompt_line("Your message")
    if not q:
        return
    try:
        from config.keysync import get_settings
        if not (get_settings().get("WEAVER_API_KEY") or "").strip():
            print("No API key set. Add one with:  weaver keys add")
            return
    except Exception:
        pass
    here = os.path.dirname(os.path.abspath(__file__))
    if here not in sys.path:
        sys.path.insert(0, here)
    # Quick question → fast direct answer; document task → full pipeline.
    try:
        from pipeline.orchestrator import is_document_task
        _is_task = is_document_task(q)
    except Exception:
        _is_task = True
    if not _is_task:
        try:
            chat = _load_chat()
            r = chat(q, timeout=120)
        except Exception as e:
            print(f"Could not load chat: {e}")
            return
        if r.get("error"):
            print(f"[error: {r.get('error')}] {r.get('message','')}")
        else:
            print("\n" + (r.get("reply") or "").strip() + "\n")
        return
    try:
        from pipeline.orchestrator import run_pipeline_sync
        res = run_pipeline_sync(q)
    except Exception as e:
        print(f"[pipeline error] {e}")
        return
    reply = (res.get("reply") or "").strip()
    if reply:
        print("\n" + reply + "\n")
    if res.get("output_path"):
        print(f"📄 الملف: {res['output_path']}")
    if not reply and not res.get("output_path"):
        print("(no reply — check your key with:  weaver keys add)")


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
    sub.add_parser("diag", help="show interactive-menu diagnostics")
    sub.add_parser("test", help="test the AI connection and show any error")
    ap = sub.add_parser("ask", help="ask the model a question from the terminal")
    ap.add_argument("text", nargs="*", help="the message")
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
    elif cmd == "diag":
        cmd_diag(args)
    elif cmd == "test":
        cmd_test(args)
    elif cmd == "ask":
        cmd_ask(args)
    elif cmd == "doctor":
        cmd_doctor(args)
    elif cmd == "version":
        cmd_version(args)
    else:
        # no subcommand -> show banner + install flow
        cmd_install(args)


if __name__ == "__main__":
    main()
