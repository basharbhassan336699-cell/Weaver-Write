#!/usr/bin/env python3
"""
tools/test_vision.py — decisive check of whether the CONFIGURED provider/model
can actually "see" images (vision), run against your own key on your device.

It sends two tiny solid-color images (red, then blue) to the provider using the
OpenAI-compatible vision message format and asks for the dominant color in one
word. Verdict:

  • both correct            → VISION WORKS (the model can read images)
  • an explicit image error  → NO VISION (provider/model is text-only)
  • wrong / evasive answers  → NO VISION (model can't really see them)

Usage (in the project root, with your key already saved in config/.env):
    python tools/test_vision.py

No new dependencies; uses the same provider settings as the app.
"""
from __future__ import annotations
import json
import os
import sys
import urllib.request
import urllib.error

# tiny 48x48 solid PNGs (no deps needed to produce them here)
_RED = ("iVBORw0KGgoAAAANSUhEUgAAADAAAAAwCAIAAADYYG7QAAAAOklEQVR42u3OMQ0AAAgD"
        "sImYf2WIwQXhaFIBzbSvREhISEhISEhISEhISEhISEhISEhISEhISEjozgLL0SSIMo/"
        "dHQAAAABJRU5ErkJggg==")
_BLUE = ("iVBORw0KGgoAAAANSUhEUgAAADAAAAAwCAIAAADYYG7QAAAAO0lEQVR42u3OQQ0AAAgE"
         "oAthCPvnMYwtnA82ApDqeSVCQkJCQkJCQkJCQkJCQkJCQkJCQkJCQkJCQncWKm/YiMbi"
         "bpkAAAAASUVORK5CYII=")


def _load_settings():
    """Read provider base URL / key / model exactly like the web server does."""
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "config"))
    try:
        import keysync  # type: ignore
        s = keysync.get_settings()
    except Exception:
        s = {k: os.environ.get(k, "") for k in
             ("WEAVER_API_KEY", "WEAVER_BASE_URL", "WEAVER_MODEL")}
    key = (s.get("WEAVER_API_KEY") or "").strip()
    base = (s.get("WEAVER_BASE_URL") or "").strip().rstrip("/")
    model = (s.get("WEAVER_MODEL") or "").strip()
    if not base and key:
        try:
            det = keysync.detect_provider(key)  # type: ignore
            if det:
                base = (det[0] or "").rstrip("/")
                model = model or det[1]
        except Exception:
            pass
    return key, base, model


def _ask_color(base, key, model, b64, timeout=60):
    """Send one image + a one-word color question. Returns (reply, error)."""
    payload = json.dumps({
        "model": model,
        "max_tokens": 40,
        "temperature": 0,
        "messages": [{
            "role": "user",
            "content": [
                {"type": "text",
                 "text": ("What is the dominant color of this image? "
                          "Answer with ONE English word only.")},
                {"type": "image_url",
                 "image_url": {"url": "data:image/png;base64," + b64}},
            ],
        }],
    }).encode("utf-8")
    req = urllib.request.Request(
        base + "/chat/completions", data=payload, method="POST",
        headers={"Content-Type": "application/json",
                 "Authorization": "Bearer " + key, "x-api-key": key,
                 "anthropic-version": "2023-06-01"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            detail = e.read().decode("utf-8")[:300]
        except Exception:
            detail = str(e)
        return "", f"HTTP {e.code}: {detail}"
    except Exception as e:
        return "", str(e)
    try:
        return (data["choices"][0]["message"]["content"] or ""), None
    except Exception:
        c = data.get("content")
        if isinstance(c, list):
            return "".join(p.get("text", "") for p in c
                           if isinstance(p, dict)), None
        if isinstance(c, str):
            return c, None
    return "", "unexpected response shape: " + json.dumps(data)[:300]


def main():
    key, base, model = _load_settings()
    if not key or not base:
        print("✗ لا يوجد مفتاح/مزوّد مضبوط. أضِف مفتاحك أولاً من قسم Keys.")
        return 2
    print(f"المزوّد: {base}\nالنموذج: {model or '(افتراضي)'}\n")
    checks = [("أحمر", "red", _RED), ("أزرق", "blue", _BLUE)]
    got = 0
    hard_error = None
    for ar, en, b64 in checks:
        reply, err = _ask_color(base, key, model, b64)
        if err:
            print(f"• صورة {ar}: خطأ ← {err}")
            low = err.lower()
            if any(w in low for w in ("image", "vision", "multimodal",
                                      "not support", "invalid", "content")):
                hard_error = err
            continue
        ok = en in reply.lower() or ar in reply
        print(f"• صورة {ar}: ردّ النموذج = {reply.strip()!r} → "
              + ("صحيح ✅" if ok else "غير صحيح ❌"))
        if ok:
            got += 1
    print()
    if got == len(checks):
        print("النتيجة: ✅ النموذج يرى الصور (Vision يعمل). يمكننا تفعيل الصور.")
        return 0
    if hard_error:
        print("النتيجة: ❌ النموذج لا يدعم الصور (رفضها المزوّد صراحةً). "
              "الصور تحتاج نموذج رؤية أو OCR منفصلاً.")
        return 1
    print("النتيجة: ❌ النموذج لم يقرأ الصور بشكل صحيح — الأرجح أنه نصّي فقط. "
          "الصور تحتاج نموذج رؤية أو OCR منفصلاً.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
