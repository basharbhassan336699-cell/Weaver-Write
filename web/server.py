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
import re
import time
import base64
import hashlib
import secrets
import urllib.parse
import urllib.request
import urllib.error
from urllib.parse import urlparse, parse_qs

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


# ── Connectors (real integrations from engines/open-connector-core) ──
_CONN_INDEX = None
_PROVIDERS_DIR = os.path.join(_ROOT, "engines", "open-connector-core",
                              "src", "providers")
_CONN_STATE = os.path.join(_ROOT, "config", "connectors.json")


def _prettify(cid: str) -> str:
    return cid.replace("_", " ").replace("-", " ").title()


def _connectors_index():
    """Scan the real connector definitions once and cache: id, display name,
    categories, auth types, homepage. ~1300 connectors."""
    global _CONN_INDEX
    if _CONN_INDEX is not None:
        return _CONN_INDEX
    items = []
    try:
        ids = sorted(os.listdir(_PROVIDERS_DIR))
    except OSError:
        ids = []
    for cid in ids:
        d = os.path.join(_PROVIDERS_DIR, cid)
        if not os.path.isdir(d):
            continue
        name, cats, auth, home = _prettify(cid), [], [], ""
        try:
            txt = open(os.path.join(d, "definition.ts"), encoding="utf-8").read()
            m = re.search(r'displayName:\s*"([^"]+)"', txt)
            if m:
                name = m.group(1)
            m = re.search(r'categories:\s*\[([^\]]*)\]', txt)
            if m:
                cats = re.findall(r'"([^"]+)"', m.group(1))
            m = re.search(r'authTypes:\s*\[([^\]]*)\]', txt)
            if m:
                auth = re.findall(r'"([^"]+)"', m.group(1))
            m = re.search(r'homepageUrl:\s*"([^"]+)"', txt)
            if m:
                home = m.group(1)
        except OSError:
            pass
        items.append({"id": cid, "name": name, "categories": cats,
                      "auth": auth, "homepage": home})
    _CONN_INDEX = items
    return items


# ── live OAuth (authorization-code + PKCE) for oauth2 connectors ──
_OAUTH_META = {}      # connector id -> {auth_url, token_url, scopes, pkce, params} | None
_OAUTH_PENDING = {}   # state -> pending exchange info


def _resolve_scopes(pdir, txt):
    """Return the scope strings for a connector, resolving the many forms used
    in the definitions: inline quoted strings, string constants, arrays of
    constants (Google/GitHub), and object-member refs (Canva)."""
    m = re.search(r'scopes:\s*\[(.*?)\]', txt, re.S)
    inline = m.group(1) if m else None
    varname = None
    if inline is None:
        mv = re.search(r'scopes:\s*([A-Za-z_][\w.]*)', txt)
        if not mv:
            return []
        varname = mv.group(1)
    sc = ""
    for fn in ("scopes.ts", "actions.ts"):  # scope consts live in either
        try:
            sc += "\n" + open(os.path.join(pdir, fn), encoding="utf-8").read()
        except OSError:
            pass
    str_const = {}
    for nm, val in re.findall(r'export const (\w+)\s*(?::\s*string)?\s*=\s*"([^"]+)"', sc):
        str_const[nm] = val
    arr_const = {}
    for nm, arr in re.findall(r'export const (\w+)\s*(?::[^={]*?)?=\s*\[(.*?)\]', sc, re.S):
        arr_const[nm] = arr
    obj_props = {}
    for nm, obj in re.findall(r'export const (\w+)\s*(?::[^={]*?)?=\s*\{(.*?)\}', sc, re.S):
        for k, v in re.findall(r'(\w+)\s*:\s*"([^"]+)"', obj):
            obj_props[nm + "." + k] = v

    def tok(t, seen):
        t = t.strip().strip(",").strip()
        if not t:
            return []
        if t.startswith('"') and t.endswith('"'):
            return [t[1:-1]]
        if t in str_const:
            return [str_const[t]]
        if t in obj_props:
            return [obj_props[t]]
        if t in arr_const:
            if t in seen:
                return []
            seen.add(t)
            return body(arr_const[t], seen)
        return []

    def body(b, seen):
        out = []
        for p in re.findall(r'"[^"]+"|[A-Za-z_][\w.]*', b):
            out.extend(tok(p, seen))
        return out

    res = body(inline, set()) if inline is not None else tok(varname, set())
    dedup = []
    for s in res:
        if s not in dedup:
            dedup.append(s)
    return dedup


def _connector_oauth(cid):
    """OAuth metadata for a connector, or None if it isn't oauth2."""
    if cid in _OAUTH_META:
        return _OAUTH_META[cid]
    pdir = os.path.join(_PROVIDERS_DIR, cid)
    meta = None
    try:
        txt = open(os.path.join(pdir, "definition.ts"), encoding="utf-8").read()
        au = re.search(r'authorizationUrl:\s*"([^"]+)"', txt)
        tu = re.search(r'tokenUrl:\s*"([^"]+)"', txt)
        if au and tu:
            params = {}
            pm = re.search(r'authorizationParams:\s*\{([^}]*)\}', txt)
            if pm:
                for k, v in re.findall(r'(\w+):\s*"([^"]+)"', pm.group(1)):
                    params[k] = v
            meta = {"auth_url": au.group(1), "token_url": tu.group(1),
                    "scopes": _resolve_scopes(pdir, txt),
                    "pkce": ("pkce:" in txt or "code_challenge" in txt),
                    "params": params}
    except OSError:
        pass
    _OAUTH_META[cid] = meta
    return meta


def _oauth_start(cid, client_id, client_secret, host):
    meta = _connector_oauth(cid)
    if not meta:
        return {"error": "not_oauth"}
    # reuse credentials saved from a previous setup, so later sign-ins are
    # one tap (jump straight to the provider) — no re-entering client id/secret
    if not client_id or not client_secret:
        saved = _connectors_state().get(cid, {})
        sf = saved.get("fields", {})
        client_id = client_id or saved.get("client_id") or sf.get("client_id", "")
        client_secret = (client_secret or saved.get("client_secret")
                         or sf.get("client_secret", ""))
    if not client_id:
        return {"error": "missing_client_id"}
    redirect_uri = "http://%s/oauth/callback" % host
    state = secrets.token_urlsafe(24)
    verifier = secrets.token_urlsafe(48)
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    _OAUTH_PENDING[state] = {"id": cid, "client_id": client_id,
                             "client_secret": client_secret, "verifier": verifier,
                             "token_url": meta["token_url"],
                             "redirect_uri": redirect_uri, "ts": time.time()}
    # remember the client credentials right away (pending connection)
    st = _connectors_state()
    ex = st.get(cid, {})
    ex.update({"client_id": client_id, "client_secret": client_secret})
    st[cid] = ex
    _save_connectors_state(st)
    q = {"response_type": "code", "client_id": client_id,
         "redirect_uri": redirect_uri, "state": state,
         "code_challenge": challenge, "code_challenge_method": "S256"}
    if meta["scopes"]:
        q["scope"] = " ".join(meta["scopes"])
    q.update(meta.get("params", {}))
    sep = "&" if "?" in meta["auth_url"] else "?"
    return {"auth_url": meta["auth_url"] + sep + urllib.parse.urlencode(q),
            "redirect_uri": redirect_uri}


def _oauth_exchange(pend, code):
    data = urllib.parse.urlencode({
        "grant_type": "authorization_code", "code": code,
        "redirect_uri": pend["redirect_uri"], "client_id": pend["client_id"],
        "client_secret": pend["client_secret"], "code_verifier": pend["verifier"],
    }).encode()
    req = urllib.request.Request(
        pend["token_url"], data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded",
                 "Accept": "application/json"}, method="POST")
    try:
        raw = urllib.request.urlopen(req, timeout=30).read().decode("utf-8")
    except urllib.error.HTTPError as e:
        try:
            raw = e.read().decode("utf-8")
        except Exception:
            raw = str(e)
        return None, "Token exchange failed: " + raw[:250]
    except Exception as e:
        return None, "Token exchange error: " + str(e)
    try:
        tok = json.loads(raw)
    except Exception:
        tok = dict(urllib.parse.parse_qsl(raw))
    if not tok.get("access_token"):
        return None, "No access token returned: " + raw[:250]
    return tok, None


# ── persistent chat history (survives browser/terminal/device restarts) ──
_CHATS_DIR = os.path.join(_ROOT, "config", "chats")
_ID_RE = re.compile(r'^[A-Za-z0-9_.\-]+$')


def _chats_index():
    items = []
    try:
        names = os.listdir(_CHATS_DIR)
    except OSError:
        names = []
    for fn in names:
        if not fn.endswith(".json"):
            continue
        try:
            d = json.load(open(os.path.join(_CHATS_DIR, fn), encoding="utf-8"))
            items.append({"id": d.get("id"), "title": d.get("title", ""),
                          "ts": d.get("ts", 0), "projectId": d.get("projectId"),
                          "count": len(d.get("messages", []))})
        except Exception:
            pass
    items.sort(key=lambda x: x.get("ts", 0), reverse=True)
    return items


def _chat_read(cid):
    if not (cid and _ID_RE.match(cid)):
        return None
    try:
        return json.load(open(os.path.join(_CHATS_DIR, cid + ".json"),
                              encoding="utf-8"))
    except Exception:
        return None


def _chat_write(d):
    cid = d.get("id")
    if not (cid and _ID_RE.match(cid)):
        return False
    try:
        os.makedirs(_CHATS_DIR, exist_ok=True)
        with open(os.path.join(_CHATS_DIR, cid + ".json"), "w",
                  encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False)
        return True
    except Exception:
        return False


def _chat_remove(cid):
    if not (cid and _ID_RE.match(cid)):
        return
    try:
        os.remove(os.path.join(_CHATS_DIR, cid + ".json"))
    except OSError:
        pass


def _connectors_state():
    try:
        return json.loads(open(_CONN_STATE, encoding="utf-8").read())
    except Exception:
        return {}


def _save_connectors_state(st):
    try:
        os.makedirs(os.path.dirname(_CONN_STATE), exist_ok=True)
        with open(_CONN_STATE, "w", encoding="utf-8") as f:
            json.dump(st, f, ensure_ascii=False, indent=2)
        try:
            os.chmod(_CONN_STATE, 0o600)  # credentials stay private
        except OSError:
            pass
    except Exception:
        pass


# Effort levels — real generation settings, not just labels. Higher effort =
# more output budget, lower temperature (more precise/deterministic), and a
# system instruction that asks for deeper, verified reasoning. Uses only
# universally-supported OpenAI-compatible fields, so no provider breaks.
EFFORT = {
    "low":    {"max_tokens": 1024, "temperature": 0.9,
               "system": "Answer concisely and directly."},
    "medium": {"max_tokens": 2048, "temperature": 0.7,
               "system": "Answer clearly and completely."},
    "high":   {"max_tokens": 4096, "temperature": 0.4,
               "system": "Think step by step. Be thorough and precise, and "
                         "double-check your answer before replying."},
    "max":    {"max_tokens": 8192, "temperature": 0.2,
               "system": "Reason rigorously and step by step. Be maximally "
                         "thorough, precise and exhaustive; verify each step "
                         "and consider edge cases before finalizing."},
}


def _chat(message: str, history=None, timeout: int = 120, effort: str = "medium") -> dict:
    """Send a message to the configured provider using the saved key and return
    the assistant reply. OpenAI-compatible /chat/completions (works for the
    registry providers, incl. Anthropic's and Google's compatible endpoints).
    `effort` (low/medium/high/max) changes real generation settings."""
    import urllib.request
    import urllib.error

    s = keysync.get_settings()  # reads config/.env fresh (CLI + web share it)
    key = (s.get("WEAVER_API_KEY") or "").strip()
    if not key:
        return {"error": "no_key"}
    base = (s.get("WEAVER_BASE_URL") or "").rstrip("/")
    model = s.get("WEAVER_MODEL") or ""
    if not base:
        det = getattr(keysync, "detect_provider", lambda _k: None)(key)
        if det:
            base = (det[0] or "").rstrip("/")
            model = model or det[1]
    if not base:
        return {"error": "no_provider",
                "message": "No provider URL is configured. Add your key again."}

    lvl = EFFORT.get((effort or "medium").lower(), EFFORT["medium"])
    max_tokens = lvl["max_tokens"]
    temperature = lvl["temperature"]

    msgs = []
    # a system instruction whose depth scales with the chosen effort
    if not (history and history and history[0].get("role") == "system"):
        msgs.append({"role": "system", "content": lvl["system"]})
    msgs.extend(list(history or []))
    msgs.append({"role": "user", "content": message})
    payload = json.dumps({"model": model, "messages": msgs,
                          "max_tokens": max_tokens,
                          "temperature": temperature}).encode("utf-8")
    headers = {"Content-Type": "application/json",
               "Authorization": f"Bearer {key}",
               "x-api-key": key, "anthropic-version": "2023-06-01"}
    req = urllib.request.Request(base + "/chat/completions", data=payload,
                                 headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            detail = e.read().decode("utf-8")[:400]
        except Exception:
            detail = str(e)
        return {"error": "http_error", "message": f"{e.code}: {detail}"}
    except Exception as e:
        return {"error": "request_failed", "message": str(e)}

    reply = ""
    try:
        reply = data["choices"][0]["message"]["content"]
    except Exception:
        c = data.get("content")
        if isinstance(c, list):  # native Anthropic shape, just in case
            reply = "".join(p.get("text", "") for p in c if isinstance(p, dict))
        elif isinstance(c, str):
            reply = c
    return {"reply": reply, "provider": s.get("WEAVER_PROVIDER", ""),
            "model": model, "effort": (effort or "medium").lower(),
            "max_tokens": max_tokens}


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
            # served with no-store headers, so a manual browser reload always
            # fetches the latest UI (no background polling needed)
            self._serve_file("index.html", "text/html; charset=utf-8")
            return
        if path == "/oauth/callback":
            qs = parse_qs(urlparse(self.path).query)
            code = qs.get("code", [""])[0]
            state = qs.get("state", [""])[0]
            err = qs.get("error", [""])[0]
            pend = _OAUTH_PENDING.pop(state, None)
            if err or not code or not pend:
                self._oauth_page("Sign-in was cancelled or failed."
                                 + ((" (" + err + ")") if err else ""), False)
                return
            tok, e = _oauth_exchange(pend, code)
            if e:
                self._oauth_page(e, False)
                return
            st = _connectors_state()
            ex = st.get(pend["id"], {})
            ex.update({"connected": True, "saved_at": int(time.time()),
                       "oauth": {"access_token": tok.get("access_token"),
                                 "refresh_token": tok.get("refresh_token"),
                                 "scope": tok.get("scope"),
                                 "token_type": tok.get("token_type"),
                                 "expires_at": (int(time.time()) + int(tok["expires_in"]))
                                 if tok.get("expires_in") else None}})
            st[pend["id"]] = ex
            _save_connectors_state(st)
            self._oauth_page("Connected ✓  You can close this tab and "
                             "return to Weaver Write.", True)
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
        if path == "/api/chats":
            self._json({"chats": _chats_index()})
            return
        if path == "/api/chats/one":
            cid = parse_qs(urlparse(self.path).query).get("id", [""])[0]
            d = _chat_read(cid)
            self._json(d if d else {"error": "not_found"})
            return
        if path == "/api/providers":
            reg = []
            try:
                for p in providers.load_registry():
                    reg.append({"name": p.get("name", ""),
                                "base_url": p.get("base_url", ""),
                                "auth": p.get("auth", "bearer")})
            except Exception:
                reg = [{"name": n, "base_url": "", "auth": "bearer"}
                       for n in providers.provider_names()]
            self._json({"providers": [r["name"] for r in reg], "registry": reg})
            return
        if path == "/api/connectors":
            qs = parse_qs(urlparse(self.path).query)
            q = (qs.get("q", [""])[0] or "").lower().strip()
            try:
                limit = max(1, min(200, int(qs.get("limit", ["60"])[0])))
            except Exception:
                limit = 60
            idx = _connectors_index()
            state = _connectors_state()

            def _match(it):
                if not q:
                    return True
                return (q in it["name"].lower() or q in it["id"].lower()
                        or any(q in c.lower() for c in it["categories"]))
            res = [it for it in idx if _match(it)]
            out = []
            for it in res[:limit]:
                c = dict(it)
                sv = state.get(it["id"], {})
                c["connected"] = bool(sv.get("connected"))
                c["has_client"] = bool(sv.get("client_id")
                                       or sv.get("fields", {}).get("client_id"))
                out.append(c)
            self._json({"count_all": len(idx), "total": len(res),
                        "shown": len(out), "connectors": out,
                        "connected_count": len(state)})
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

        if path == "/api/connectors/connect":
            cid = (body.get("id") or "").strip()
            if not cid:
                self._json({"error": "missing id"})
                return
            fields = {k: v for k, v in (body.get("fields") or {}).items() if v}
            st = _connectors_state()
            st[cid] = {"connected": True, "fields": fields,
                       "saved_at": int(time.time())}
            _save_connectors_state(st)
            self._json({"ok": True, "id": cid, "connected": True})
            return
        if path == "/api/connectors/disconnect":
            cid = (body.get("id") or "").strip()
            st = _connectors_state()
            st.pop(cid, None)
            _save_connectors_state(st)
            self._json({"ok": True, "id": cid, "connected": False})
            return
        if path == "/api/connectors/oauth/start":
            host = self.headers.get("Host", "127.0.0.1:%d" % PORT)
            self._json(_oauth_start((body.get("id") or "").strip(),
                                    (body.get("client_id") or "").strip(),
                                    (body.get("client_secret") or "").strip(),
                                    host))
            return

        if path == "/api/chats/save":
            cid = (body.get("id") or "").strip()
            if not cid:
                self._json({"error": "missing_id"})
                return
            rec = {"id": cid, "title": body.get("title", ""),
                   "ts": body.get("ts") or int(time.time() * 1000),
                   "projectId": body.get("projectId"),
                   "messages": body.get("messages", [])}
            self._json({"ok": _chat_write(rec), "id": cid})
            return
        if path == "/api/chats/delete":
            _chat_remove((body.get("id") or "").strip())
            self._json({"ok": True})
            return

        if path == "/api/chat":
            msg = (body.get("message") or "").strip()
            if not msg:
                self._json({"error": "empty"})
                return
            # Every request goes through the FULL pipeline (WeaverOrchestrator):
            # understand → route → research → credibility → write → clean →
            # verify → export. It writes any output file into outputs/.
            keysync.load_env()
            if not os.environ.get("WEAVER_API_KEY", "").strip():
                self._json({"error": "no_key"})
                return
            # thread recent turns so the pipeline still sees the conversation
            history = body.get("history") or []
            desc = msg
            if history:
                ctx = "\n".join(
                    f"{h.get('role','user')}: {h.get('content','')}"
                    for h in history[-6:] if isinstance(h, dict))
                if ctx.strip():
                    desc = (f"[سياق المحادثة السابقة]\n{ctx}\n\n"
                            f"[الطلب الحالي]\n{msg}")
            try:
                from pipeline.orchestrator import run_pipeline_sync
                res = run_pipeline_sync(desc)
            except Exception as e:
                self._json({"error": "pipeline_error", "message": str(e)})
                return
            reply = (res.get("reply") or "").strip()
            out = res.get("output_path")
            if out:
                try:
                    rel = os.path.relpath(out, _ROOT)
                except Exception:
                    rel = out
                note = "📄 تم حفظ الملف: " + rel
                reply = (reply + "\n\n" + note) if reply else note
            if not reply:
                reply = "(لم يُنتج النظام رداً)"
            self._json({
                "reply": reply,
                "output_path": out,
                "pipeline": {
                    "tools": res.get("tools"), "skills": res.get("skills"),
                    "task_type": res.get("task_type"),
                    "topic": res.get("topic"),
                    "output_format": res.get("output_format"),
                },
            })
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

    def _oauth_page(self, msg, ok):
        color = "#68c79a" if ok else "#f07d63"
        html = ("<!doctype html><meta charset=utf-8><meta name=viewport "
                "content='width=device-width,initial-scale=1'>"
                "<body style='margin:0;background:#14131a;color:#ece9f5;"
                "font-family:system-ui,sans-serif;display:grid;place-items:center;"
                "height:100vh;text-align:center;padding:20px'>"
                "<div><div style='font-size:44px'>%s</div>"
                "<h2 style='color:%s;margin:10px 0'>%s</h2>"
                "<p style='opacity:.7'>Weaver Write</p></div></body>"
                % ("✅" if ok else "⚠️", color, msg))
        data = html.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

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
        # never let the browser show a stale UI after an update
        self.send_header("Cache-Control", "no-store, must-revalidate")
        self.send_header("Pragma", "no-cache")
        self.end_headers()
        self.wfile.write(data)


class _ReuseTCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    allow_reuse_address = True  # avoid stale TIME_WAIT "address already in use"
    daemon_threads = True       # don't block the UI while a chat is generating


def serve(port=None):
    port = port or PORT
    keysync.load_env()  # load synced settings first
    with _ReuseTCPServer(("127.0.0.1", port), Handler) as httpd:
        print(f"Weaver Write web UI running at http://127.0.0.1:{port}")
        print("Press Ctrl+C to stop.")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nStopped.")


if __name__ == "__main__":
    p = int(sys.argv[1]) if len(sys.argv) > 1 else PORT
    serve(p)
