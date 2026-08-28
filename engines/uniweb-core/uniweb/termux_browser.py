"""
uniweb/termux_browser.py — adapt browser_use (Chromium) for phones / Termux
===========================================================================
Full Chromium on a phone is heavy and fragile. This module makes browser_use
run as reliably as possible on Termux/Android — and degrade cleanly when a
browser isn't available (the pipeline then falls back to curl_impersonate).

It provides:
  * is_termux()            — are we on Termux/Android?
  * detect_chromium()      — path to a usable Chromium, or None
  * mobile_chrome_args()   — phone-safe Chromium launch flags
  * build_browser_profile()— a browser_use BrowserProfile wired for the phone
"""
from __future__ import annotations
import os
import glob
import shutil

# A modern mobile Chrome UA so sites serve the mobile layout.
MOBILE_UA = ("Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 "
             "(KHTML, like Gecko) Chrome/122.0.0.0 Mobile Safari/537.36")


def is_termux() -> bool:
    if "com.termux" in (os.environ.get("PREFIX", "") or ""):
        return True
    return os.path.isdir("/data/data/com.termux/files/usr")


def detect_chromium() -> str | None:
    """Find a Chromium/Chrome executable usable on this device. Honors explicit
    overrides first, then Termux/Playwright/system locations, then PATH."""
    # 1) explicit overrides
    for env in ("WEAVER_CHROMIUM", "CHROME_BIN", "BROWSER_EXECUTABLE",
                "PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH"):
        p = os.environ.get(env)
        if p and os.path.exists(p):
            return p
    cands = []
    # 2) Termux prefix
    pref = os.environ.get("PREFIX", "")
    if pref:
        cands += [os.path.join(pref, "bin", n) for n in
                  ("chromium", "chromium-browser", "chrome", "google-chrome")]
    cands.append("/data/data/com.termux/files/usr/bin/chromium")
    # 3) Playwright-managed browsers
    pw = os.environ.get("PLAYWRIGHT_BROWSERS_PATH")
    if pw:
        for pat in ("chromium*/chrome-linux/chrome",
                    "chromium*/chrome-linux/headless_shell",
                    "chromium*/chrome-linux*/chrome"):
            cands += glob.glob(os.path.join(pw, pat))
    # 4) common system paths
    cands += ["/usr/bin/chromium", "/usr/bin/chromium-browser",
              "/usr/bin/google-chrome", "/usr/bin/google-chrome-stable"]
    for c in cands:
        if c and os.path.exists(c):
            return c
    # 5) PATH
    for n in ("chromium", "chromium-browser", "google-chrome",
              "google-chrome-stable", "chrome"):
        w = shutil.which(n)
        if w:
            return w
    return None


def mobile_chrome_args() -> list:
    """Chromium flags that let it start inside Termux/Android (no root, no
    zygote, limited /dev/shm and memory) and render headless."""
    single = os.environ.get("WEAVER_CHROME_SINGLE_PROCESS", "1") != "0"
    args = [
        "--headless=new",
        "--no-sandbox",
        "--disable-setuid-sandbox",
        "--no-zygote",
        "--disable-dev-shm-usage",
        "--disable-gpu",
        "--disable-software-rasterizer",
        "--disable-extensions",
        "--disable-background-networking",
        "--disable-features=Translate,BackForwardCache",
        "--window-size=390,844",
        "--js-flags=--max-old-space-size=256",
        "--user-agent=" + MOBILE_UA,
    ]
    if single:
        args.append("--single-process")   # needed on Termux (no zygote/sandbox)
    return args


def build_browser_profile(**overrides):
    """A browser_use BrowserProfile wired for the phone (executable + safe
    flags + headless). Returns None if browser_use isn't importable."""
    BrowserProfile = None
    try:
        from browser_use import BrowserProfile  # type: ignore
    except Exception:
        try:
            from browser_use.browser.profile import BrowserProfile  # type: ignore
        except Exception:
            return None
    kw = {"headless": True, "args": mobile_chrome_args()}
    exe = detect_chromium()
    if exe:
        kw["executable_path"] = exe
    kw.update(overrides)
    try:
        return BrowserProfile(**kw)
    except Exception:
        # older/newer field names — try the minimal safe subset
        try:
            return BrowserProfile(headless=True)
        except Exception:
            return None
