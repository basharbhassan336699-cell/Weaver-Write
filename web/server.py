#!/usr/bin/env python3
"""
web/server.py — Weaver Write local web server (working)
=======================================================
Serves the web UI (web/index.html) and exposes the API endpoints the page
needs, all backed by the SAME config/.env as the terminal — so the API key,
provider, and model stay in sync between the CLI and the web UI.

Endpoints:
  GET  /                     -> the web UI (index.html)
  GET  /api/settings         -> current synced settings (key masked)
  POST /api/settings         -> save key/provider/model (writes .env)
  GET  /api/providers        -> built-in + custom provider names
  POST /api/providers/models -> list models for a URL+key
  POST /api/providers/custom -> connect a custom provider (URL+key -> models)
  GET  /api/status           -> {key_set: bool, provider, model}

Pure standard-library HTTP server — no framework — so it runs anywhere
(Termux/Android, Windows, macOS, Linux). Bound to 127.0.0.1 only (local).
"""
from __future__ import annotations
import os
import sys
import json
import http.server
import socketserver
from urllib.parse import urlparse

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from config import keysync           # noqa: E402
from config import providers         # noqa: E402

PORT = int(os.environ.get("WEAVER_PORT", "8848"))


def _mask(key: str) -> str:
    if not key:
        return ""
    return (key[:4] + "…" + key[-4:]) if len(key) > 8 else "…"


class Handler(http.server.BaseHTTPRequestHandler):
    # ── helpers ──────────────────────────────────────────────
    def _json(self, obj, code=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _body(self) -> dict:
        try:
            n = int(self.headers.get("Content-Length", 0))
            raw = self.rfile.read(n).decode("utf-8") if n else "{}"
            return json.loads(raw or "{}")
        except Exception:
            return {}

    def log_message(self, *a):
        pass  # quiet

    # ── GET ──────────────────────────────────────────────────
    def do_GET(self):
        path = urlparse(self.path).path

        if path == "/" or path == "/index.html":
            self._serve_file("index.html", "text/html; charset=utf-8")
            return
        if path == "/api/settings":
            s = keysync.get_settings()
            s_masked = dict(s)
            s_masked["WEAVER_API_KEY"] = _mask(s.get("WEAVER_API_KEY", ""))
            self._json(s_masked)
            return
        if path == "/api/status":
            s = keysync.get_settings()
            self._json({"key_set": bool(s.get("WEAVER_API_KEY")),
                        "provider": s.get("WEAVER_PROVIDER", ""),
                        "model": s.get("WEAVER_MODEL", "")})
            return
        if path == "/api/providers":
            self._json({"providers": providers.provider_names()})
            return
        # static files (js/css/img) from web/
        safe = path.lstrip("/").replace("..", "")
        if safe and os.path.exists(os.path.join(_HERE, safe)):
            ctype = ("application/javascript" if safe.endswith(".js")
                     else "text/css" if safe.endswith(".css")
                     else "application/octet-stream")
            self._serve_file(safe, ctype)
            return
        self._json({"error": "not found"}, 404)

    # ── POST ─────────────────────────────────────────────────
    def do_POST(self):
        path = urlparse(self.path).path
        body = self._body()

        if path == "/api/settings":
            # save key/provider/model -> writes .env -> terminal sees it too
            key = (body.get("api_key") or body.get("WEAVER_API_KEY") or "").strip()
            updates = {}
            if key and "…" not in key:  # ignore the masked value echoed back
                applied = keysync.set_api_key(
                    key, provider=body.get("provider", ""),
                    base_url=body.get("base_url", ""),
                    model=body.get("model", ""))
                updates.update(applied)
            else:
                # allow changing model/provider without re-entering the key
                for src, dst in [("provider", "WEAVER_PROVIDER"),
                                 ("model", "WEAVER_MODEL"),
                                 ("base_url", "WEAVER_BASE_URL"),
                                 ("max_tokens", "WEAVER_MAX_TOKENS"),
                                 ("temperature", "WEAVER_TEMPERATURE")]:
                    if body.get(src):
                        updates[dst] = str(body[src])
                if updates:
                    keysync.save_env(updates)
            self._json({"ok": True, "saved": list(updates.keys())})
            return

        if path == "/api/providers/models":
            models, err = providers.list_models_for(
                body.get("base_url", ""), body.get("key", ""),
                body.get("auth", "bearer"))
            self._json({"models": models, "error": err})
            return

        if path == "/api/providers/custom":
            res = providers.connect_custom_provider(
                body.get("base_url", ""), body.get("key", ""),
                name=body.get("name", "custom"), model=body.get("model", ""))
            if not res.get("error") and res.get("model"):
                keysync.set_api_key(body.get("key", ""), provider=res["name"],
                                    base_url=res["base_url"], model=res["model"])
            self._json(res)
            return

        self._json({"error": "not found"}, 404)

    def _serve_file(self, name, ctype):
        fp = os.path.join(_HERE, name)
        if not os.path.exists(fp):
            self._json({"error": f"{name} not found"}, 404)
            return
        with open(fp, "rb") as f:
            data = f.read()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def serve(port=None):
    port = port or PORT
    keysync.load_env()  # load synced settings first
    with socketserver.TCPServer(("127.0.0.1", port), Handler) as httpd:
        print(f"Weaver Write web UI running at http://127.0.0.1:{port}")
        print("Press Ctrl+C to stop.")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nStopped.")


if __name__ == "__main__":
    p = int(sys.argv[1]) if len(sys.argv) > 1 else PORT
    serve(p)
