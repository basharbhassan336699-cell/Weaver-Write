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
# Per-chat sidecar holding the FULL text of documents produced in that chat, so
# memory recall and chat search can see the document body (not just the chat
# messages) — e.g. searching with a line copied from a produced file finds its
# conversation, and a repeated document task recalls the earlier one.
_CHATS_DOCS_DIR = os.path.join(_ROOT, "config", "chats_docs")
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
                          "windowId": d.get("windowId"),
                          "count": len(d.get("messages", []))})
        except Exception:
            pass
    items.sort(key=lambda x: x.get("ts", 0), reverse=True)
    return items


def _chats_search(query, limit=50):
    """Search stored chats by TITLE and by MESSAGE CONTENT. Returns matches
    newest-first, each with a short snippet around the first content hit so the
    user sees WHY it matched. Case-insensitive; Arabic tolerant (strips the
    Arabic diacritics/tatweel so 'ذكاء' matches 'ذكاءً')."""
    q = _normalize_ar((query or "").strip().lower())
    if not q:
        return []
    try:
        names = os.listdir(_CHATS_DIR)
    except OSError:
        names = []
    out = []
    for fn in names:
        if not fn.endswith(".json"):
            continue
        try:
            d = json.load(open(os.path.join(_CHATS_DIR, fn), encoding="utf-8"))
        except Exception:
            continue
        title = d.get("title", "") or ""
        title_hit = q in _normalize_ar(title.lower())
        snippet, hits = "", 0
        for m in d.get("messages", []) or []:
            body = m.get("content", "") if isinstance(m, dict) else str(m)
            norm = _normalize_ar(body.lower())
            pos = norm.find(q)
            if pos != -1:
                hits += 1
                if not snippet:
                    start = max(0, pos - 40)
                    end = min(len(body), pos + len(q) + 60)
                    snippet = ("…" if start else "") + body[start:end].strip() \
                              + ("…" if end < len(body) else "")
        # also search the produced-document body (a line copied from the file
        # should find its conversation)
        doc = _read_chat_doc(d.get("id"))
        if doc:
            pos = _normalize_ar(doc.lower()).find(q)
            if pos != -1:
                hits += 1
                if not snippet:
                    start = max(0, pos - 40)
                    end = min(len(doc), pos + len(q) + 60)
                    snippet = ("…" if start else "") + doc[start:end].strip() \
                              + ("…" if end < len(doc) else "")
        if title_hit or hits:
            out.append({"id": d.get("id"), "title": title,
                        "ts": d.get("ts", 0), "windowId": d.get("windowId"),
                        "projectId": d.get("projectId"),
                        "snippet": snippet, "hits": hits,
                        "titleHit": bool(title_hit)})
    out.sort(key=lambda x: x.get("ts", 0), reverse=True)
    return out[:limit]


def _normalize_ar(s):
    """Fold Arabic diacritics, tatweel, and alef/hamza variants so search is
    forgiving. ASCII text passes through unchanged."""
    if not s:
        return s
    out = []
    for ch in s:
        o = ord(ch)
        if 0x064B <= o <= 0x0652 or ch == "ـ":   # harakat + tatweel
            continue
        if ch in "أإآ":
            out.append("ا")
        elif ch == "ى":
            out.append("ي")
        elif ch == "ة":
            out.append("ه")
        else:
            out.append(ch)
    return "".join(out)


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
    try:
        os.remove(os.path.join(_CHATS_DOCS_DIR, cid + ".txt"))
    except OSError:
        pass


_CHAT_DOC_CAP = 200000   # keep at most ~200k chars of produced docs per chat


def _save_chat_doc(cid, text):
    """Append a produced document's text to the chat's sidecar so it becomes
    searchable/recallable. Safe + bounded; any failure is ignored."""
    if not (cid and _ID_RE.match(cid)) or not (text or "").strip():
        return
    try:
        os.makedirs(_CHATS_DOCS_DIR, exist_ok=True)
        p = os.path.join(_CHATS_DOCS_DIR, cid + ".txt")
        prev = ""
        if os.path.exists(p):
            try:
                prev = open(p, encoding="utf-8").read()
            except Exception:
                prev = ""
        combined = (prev + "\n\n" + text).strip() if prev else text.strip()
        if len(combined) > _CHAT_DOC_CAP:      # keep the most recent
            combined = combined[-_CHAT_DOC_CAP:]
        with open(p, "w", encoding="utf-8") as f:
            f.write(combined)
    except Exception:
        pass


def _read_chat_doc(cid):
    """Return the sidecar document text for a chat, or ""."""
    if not (cid and _ID_RE.match(cid)):
        return ""
    try:
        return open(os.path.join(_CHATS_DOCS_DIR, cid + ".txt"),
                    encoding="utf-8").read()
    except Exception:
        return ""


# ── cross-conversation memory ────────────────────────────────────────────────
# The persisted chats (config/chats/*.json) ARE the long-term memory. On a new
# message we retrieve the user's OTHER past chats that are lexically relevant and
# inject a compact digest, so the assistant has continuity across conversations.
# Fully offline (no embeddings), additive, and degrading (any failure → nothing
# injected). Disable with WEAVER_MEMORY=0.
_AR_STOP = set((
    "في من الى إلى على عن مع هذا هذه هذان هؤلاء ذلك تلك التي الذي الذين ما ماذا "
    "كيف هل و او أو ثم قد كل بعض هو هي انا أنا انت أنت نحن لك لي له لها به بها "
    "عند عندما لكن بل لا نعم يا اي أي كذا كما حتى إذا اذا لان لأن حول نحو دون بين"
).split())
_EN_STOP = set((
    "the a an of to in on for and or is are was were be been being this that "
    "these those with what how do does did you i we it as at by from your our "
    "can could would should will just about into over than then them they"
).split())


def _sig_terms(text):
    """Significant, normalized terms of a text (Arabic-folded, stopword- and
    short-word-filtered) used for lexical relevance scoring."""
    norm = _normalize_ar((text or "").lower())
    out = set()
    for w in re.findall(r"[a-z0-9؀-ۿ]+", norm):
        if len(w) < 3 or w in _AR_STOP or w in _EN_STOP:
            continue
        out.add(w)
    return out


def _chat_digest(d, maxlen=600):
    """A compact digest of a stored chat — the user's own questions capture its
    intent best, with a fallback to the first non-empty message."""
    ups = []
    for m in d.get("messages", []) or []:
        if isinstance(m, dict) and m.get("role") == "user":
            c = (m.get("content") or "").strip().replace("\n", " ")
            if c:
                ups.append(c)
    text = " | ".join(ups[:6])
    if not text:
        for m in d.get("messages", []) or []:
            c = (m.get("content", "") if isinstance(m, dict) else str(m)).strip()
            if c:
                text = c.replace("\n", " ")
                break
    return text[:maxlen]


def _recall_memory(query, exclude_id=None, k=3, budget=2600):
    """Return a compact 'memory from past conversations' block relevant to
    `query`, or "". Scans the most recent stored chats, scores each by shared
    significant terms (title matches weighted), and includes the top few that
    clear a minimum relevance. Offline and safe — any failure returns ""."""
    if os.environ.get("WEAVER_MEMORY", "1").strip().lower() in ("0", "off", "false"):
        return ""
    terms = _sig_terms(query)
    if len(terms) < 2:            # too little signal → don't inject / don't scan
        return ""
    try:
        names = os.listdir(_CHATS_DIR)
    except OSError:
        return ""
    files = []
    for fn in names:
        if not fn.endswith(".json"):
            continue
        p = os.path.join(_CHATS_DIR, fn)
        try:
            files.append((os.path.getmtime(p), p))
        except OSError:
            pass
    files.sort(reverse=True)      # newest first
    scored = []
    for _mt, p in files[:200]:    # cap the scan for speed
        try:
            d = json.load(open(p, encoding="utf-8"))
        except Exception:
            continue
        if exclude_id and d.get("id") == exclude_id:
            continue
        msgs = d.get("messages", []) or []
        if not msgs:
            continue
        title = d.get("title", "") or ""
        doc = _read_chat_doc(d.get("id"))
        blob = title + " " + " ".join(
            (m.get("content", "") if isinstance(m, dict) else str(m))
            for m in msgs[:40]) + " " + doc[:8000]
        overlap = terms & _sig_terms(blob)
        if not overlap:
            continue
        score = len(overlap) + (2 if (_sig_terms(title) & terms) else 0)
        scored.append((score, d.get("ts", 0), d))
    if not scored:
        return ""
    scored.sort(key=lambda x: (x[0], x[1]), reverse=True)
    parts, total = [], 0
    for score, _ts, d in scored:
        if score < 2:             # require ≥2 shared terms (or a title hit)
            continue
        block = "• [" + (d.get("title") or "محادثة") + "]\n" + _chat_digest(d)
        if total + len(block) > budget and parts:
            break
        parts.append(block)
        total += len(block)
        if len(parts) >= k:
            break
    return "\n\n".join(parts)


def _with_memory_for_task(desc, msg, chat_id):
    """For a DOCUMENT task: if a similar task was done in an earlier chat, prepend
    a memory block + an instruction to produce a DIFFERENT version (other
    references/studies/sources, new angles, different wording). Returns desc
    unchanged when there is no relevant memory. Safe/degrading."""
    try:
        mem = _recall_memory(msg, exclude_id=chat_id)
    except Exception:
        mem = ""
    if not mem:
        return desc
    return (
        "[ذاكرة: مهام سابقة ذات صلة أنجزناها في محادثات أخرى]\n" + mem + "\n\n"
        "[تعليمات مهمة] لقد أنجزنا مهمة مشابهة سابقاً (انظر أعلاه). أنتِج الآن "
        "نسخة مختلفة تماماً عنها: استعمل مراجع ودراسات ومصادر أخرى، وتناول "
        "زوايا وأفكاراً جديدة، وبأسلوب تعبير وصياغة مختلفين، دون تكرار المحتوى "
        "أو المصادر السابقة.\n\n" + desc)


# ── windows (workspaces): each groups its own chats; the main list shows all ──
_WINDOWS_FILE = os.path.join(_ROOT, "config", "windows.json")


def _windows_read():
    try:
        d = json.load(open(_WINDOWS_FILE, encoding="utf-8"))
        return d if isinstance(d, list) else []
    except Exception:
        return []


def _windows_write(items):
    try:
        os.makedirs(os.path.dirname(_WINDOWS_FILE), exist_ok=True)
        with open(_WINDOWS_FILE, "w", encoding="utf-8") as f:
            json.dump(items, f, ensure_ascii=False)
        return True
    except Exception:
        return False


def _windows_list():
    """Windows with a live chat count (from the chats index)."""
    wins = _windows_read()
    counts = {}
    for c in _chats_index():
        wid = c.get("windowId")
        if wid:
            counts[str(wid)] = counts.get(str(wid), 0) + 1
    for w in wins:
        w["count"] = counts.get(str(w.get("id")), 0)
    wins.sort(key=lambda x: x.get("ts", 0), reverse=True)
    return wins


# ── calendar: task deadlines + reminders ──────────────────────────────────
_CAL_FILE = os.path.join(_ROOT, "config", "calendar.json")


def _cal_read():
    try:
        d = json.load(open(_CAL_FILE, encoding="utf-8"))
        return d if isinstance(d, list) else []
    except Exception:
        return []


def _cal_write(items):
    try:
        os.makedirs(os.path.dirname(_CAL_FILE), exist_ok=True)
        with open(_CAL_FILE, "w", encoding="utf-8") as f:
            json.dump(items, f, ensure_ascii=False)
        return True
    except Exception:
        return False


def _cal_list():
    items = _cal_read()
    items.sort(key=lambda x: (x.get("done", False), x.get("due", "")))
    return items


def _calendar_suggest(text):
    """Propose up to 4 due-date options inferred from the task text (Arabic +
    English: explicit dates, غداً/tomorrow, بعد N أيام/in N days, next week,
    نهاية الأسبوع/end of week, بعد شهر/next month). Always returns concrete
    dates; the UI adds an open 'custom date' option as the 4th."""
    import datetime
    import re
    t = (text or "").lower()
    today = datetime.date.today()
    opts = []

    def add(d, label=None):
        s = d.isoformat()
        if d >= today and all(o["date"] != s for o in opts):
            opts.append({"date": s, "label": label or s})

    m = re.search(r"(\d{4})-(\d{1,2})-(\d{1,2})", t)
    if m:
        try:
            add(datetime.date(int(m.group(1)), int(m.group(2)),
                              int(m.group(3))), "التاريخ المذكور")
        except Exception:
            pass
    for mm in re.finditer(r"\b(\d{1,2})[/\-](\d{1,2})(?:[/\-](\d{2,4}))?\b", t):
        try:
            dd, mo = int(mm.group(1)), int(mm.group(2))
            yy = mm.group(3)
            yy = int(yy) if yy else today.year
            if yy < 100:
                yy += 2000
            dt = datetime.date(yy, mo, dd)
            if dt < today:
                dt = datetime.date(yy + 1, mo, dd)
            add(dt, "التاريخ المذكور")
        except Exception:
            pass

    def has(*ws):
        return any(w in t for w in ws)
    td = datetime.timedelta
    if has("غدا", "غداً", "بكرة", "tomorrow"):
        add(today + td(days=1), "غداً")
    if has("بعد يومين", "بعد غد", "in 2 days", "in two days"):
        add(today + td(days=2), "بعد يومين")
    mn = (re.search(r"بعد\s+(\d+)\s+(?:يوم|أيام|ايام)", t)
          or re.search(r"in\s+(\d+)\s+days?", t))
    if mn:
        try:
            add(today + td(days=int(mn.group(1))))
        except Exception:
            pass
    if has("الأسبوع القادم", "الاسبوع القادم", "الأسبوع المقبل", "next week",
           "بعد أسبوع", "بعد اسبوع", "in a week", "in one week"):
        add(today + td(days=7), "بعد أسبوع")
    if has("أسبوعين", "اسبوعين", "two weeks", "in 2 weeks"):
        add(today + td(days=14), "بعد أسبوعين")
    if has("نهاية الأسبوع", "نهاية الاسبوع", "end of week", "this weekend"):
        days = (4 - today.weekday()) % 7 or 7   # coming Friday
        add(today + td(days=days), "نهاية الأسبوع")
    if has("بعد شهر", "الشهر القادم", "الشهر المقبل", "next month", "in a month"):
        add(today + td(days=30), "بعد شهر")
    for dd, lab in ((1, "غداً"), (3, "بعد ٣ أيام"), (7, "بعد أسبوع")):
        if len(opts) >= 3:
            break
        add(today + td(days=dd), lab)
    return opts[:4]


def _send_notification(title, body):
    """Best-effort phone notification via Termux:API. Silent no-op elsewhere."""
    import subprocess
    try:
        subprocess.run(["termux-notification", "--title", str(title),
                        "--content", str(body)], capture_output=True, timeout=8)
        return True
    except Exception:
        return False


def _reminder_loop():
    """Background: notify (once) for any calendar event whose due date has
    arrived. Uses a phone notification when Termux:API is present; the in-app
    Calendar view always shows overdue/upcoming regardless."""
    import datetime
    while True:
        try:
            items = _cal_read()
            today = datetime.date.today().isoformat()
            changed = False
            for e in items:
                if e.get("done") or e.get("notified"):
                    continue
                due = e.get("due", "")
                if due and due <= today:
                    _send_notification("Weaver Write — تذكير بموعد",
                                       f"{e.get('title','مهمة')} — تاريخ: {due}")
                    e["notified"] = True
                    changed = True
            if changed:
                _cal_write(items)
        except Exception:
            pass
        time.sleep(300)


# ── output files (generated documents) — list / preview / download ──
def _output_dir():
    """The directory the pipeline writes finished files to — the SAME resolver
    the orchestrator uses (WEAVER_OUTPUT_DIR, phone shared storage, else the
    project's outputs/)."""
    try:
        from pipeline.orchestrator import WeaverOrchestrator
        return WeaverOrchestrator._resolve_output_dir()
    except Exception:
        d = os.path.join(_ROOT, "outputs")
        os.makedirs(d, exist_ok=True)
        return d


_MIME = {
    ".md": "text/markdown; charset=utf-8", ".txt": "text/plain; charset=utf-8",
    ".csv": "text/csv; charset=utf-8", ".json": "application/json; charset=utf-8",
    ".html": "text/html; charset=utf-8", ".htm": "text/html; charset=utf-8",
    ".pdf": "application/pdf",
    ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
    ".gif": "image/gif", ".webp": "image/webp", ".svg": "image/svg+xml",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}
_PREVIEWABLE = {"text/markdown", "text/plain", "text/csv", "application/json",
                "text/html", "application/pdf",
                "image/png", "image/jpeg", "image/gif", "image/webp", "image/svg+xml"}


def _safe_output_file(path_or_name: str):
    """Resolve a requested file to an absolute path INSIDE the output dir.
    Accepts a bare filename or an absolute path; returns None if it escapes the
    output directory or isn't a regular file (path-traversal safe)."""
    if not path_or_name:
        return None
    d = os.path.realpath(_output_dir())
    cand = path_or_name
    if not os.path.isabs(cand):
        cand = os.path.join(d, cand)
    real = os.path.realpath(cand)
    if real != d and not real.startswith(d + os.sep):
        return None
    if not os.path.isfile(real):
        return None
    return real


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


def _sources_md(sources, isar: bool) -> str:
    """Build a numbered Markdown 'Sources' block from an ordered list of
    {title,url}. Titles link to the article (clickable in the UI); order matches
    the live-search order. Deduplicated; returns "" when there is nothing."""
    if not sources:
        return ""
    head = "المصادر" if isar else "Sources"
    lines, seen, n = [], set(), 1
    for s in sources:
        u = (s.get("url") or "").strip()
        if not u or u in seen:
            continue
        seen.add(u)
        t = (s.get("title") or u).strip().replace("]", "〕").replace("[", "〔")
        lines.append(f"{n}. [{t}]({u})")
        n += 1
        if n > 8:
            break
    if not lines:
        return ""
    return "\n\n---\n\n**" + head + ":**\n\n" + "\n".join(lines)


def _chat(message: str, history=None, timeout: int = 120, effort: str = "medium",
          context: str = None, memory: str = None) -> dict:
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
    # Cap history by total characters, keeping the MOST RECENT turns, so a very
    # long conversation can't overflow the provider's context window (which
    # would produce a slow or empty reply). Normal-length chats are unaffected —
    # they fit well under the budget. ~60k chars ≈ a safe input size for the
    # flash model; the newest messages are always kept.
    _HIST_CHAR_BUDGET = 60000
    _hist = list(history or [])
    _kept, _total = [], 0
    for _m in reversed(_hist):
        _c = _m.get("content", "") if isinstance(_m, dict) else str(_m)
        _total += len(_c or "")
        if _total > _HIST_CHAR_BUDGET and _kept:
            break
        _kept.append(_m)
    _kept.reverse()
    msgs.extend(_kept)
    # memory from the user's OTHER past conversations (cross-conversation
    # continuity) → injected as guidance the model may use or ignore
    if memory:
        msgs.append({"role": "system", "content": (
            "ذاكرة من محادثات المستخدم السابقة، قد تكون ذات صلة بسؤاله الحالي. "
            "استعن بها للاستمرارية والسياق إن كانت مفيدة، وتجاهلها تماماً إن لم "
            "تكن ذات صلة، ولا تخترع منها ما ليس فيها:\n"
            "Memory from the user's earlier conversations — use for continuity "
            "if relevant, ignore if not:\n\n" + memory)})
    # live context (news search results / pasted-URL content) → answer from it
    if context:
        msgs.append({"role": "system", "content": (
            "لديك أدناه مصادر حيّة حديثة من الإنترنت. اعتمد عليها للإجابة عن سؤال "
            "المستخدم بمعلومات محدّثة، ولا تقل إنك لا تملك وصولاً للإنترنت أو أنّ "
            "معرفتك قديمة؛ واذكر باختصار أنّ المعلومات من بحث حيّ.\n"
            "You have live, up-to-date sources below. Use them to answer with "
            "current information; do NOT claim you lack internet access or that "
            "your knowledge is outdated.\n\n" + context)})
    msgs.append({"role": "user", "content": message})
    payload = json.dumps({"model": model, "messages": msgs,
                          "max_tokens": max_tokens,
                          "temperature": temperature}).encode("utf-8")
    headers = {"Content-Type": "application/json",
               "Authorization": f"Bearer {key}",
               "x-api-key": key, "anthropic-version": "2023-06-01"}
    req = urllib.request.Request(base + "/chat/completions", data=payload,
                                 headers=headers, method="POST")

    def _extract_reply(data):
        try:
            return data["choices"][0]["message"]["content"] or ""
        except Exception:
            c = data.get("content")
            if isinstance(c, list):  # native Anthropic shape, just in case
                return "".join(p.get("text", "") for p in c
                               if isinstance(p, dict))
            if isinstance(c, str):
                return c
        return ""

    # Some flash providers return HTTP 200 with EMPTY content under concurrent
    # load (a silent throttle) instead of a 429. Retry once on an empty reply.
    reply = ""
    for attempt in range(2):
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
        reply = _extract_reply(data)
        if reply.strip() or attempt == 1:
            break
        time.sleep(1.2)  # brief backoff, then one more try

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
        if path == "/api/health":
            # lets the user confirm the REAL server (with persistence) is the
            # one running — the static fallback has no /api endpoints at all.
            try:
                n = len([f for f in os.listdir(_CHATS_DIR)
                         if f.endswith(".json")])
            except OSError:
                n = 0
            self._json({"ok": True, "server": "full",
                        "chats_dir": _CHATS_DIR, "chats": n})
            return
        if path == "/api/outputs":
            # list generated files (present_files): name, size, type, mtime
            d = _output_dir()
            items = []
            try:
                for name in os.listdir(d):
                    fp = os.path.join(d, name)
                    if not os.path.isfile(fp):
                        continue
                    ext = os.path.splitext(name)[1].lower()
                    ctype = _MIME.get(ext, "application/octet-stream")
                    base = ctype.split(";")[0].strip()
                    st = os.stat(fp)
                    items.append({"name": name, "size": st.st_size,
                                  "mtime": int(st.st_mtime), "ext": ext,
                                  "type": ctype,
                                  "previewable": base in _PREVIEWABLE})
            except OSError:
                pass
            items.sort(key=lambda x: x["mtime"], reverse=True)
            self._json({"dir": d, "files": items})
            return
        if path == "/api/output":
            # view / download a single generated file (view + present_files)
            q = parse_qs(urlparse(self.path).query)
            real = _safe_output_file(q.get("path", [""])[0])
            if not real:
                self._json({"error": "not_found"}, 404)
                return
            ext = os.path.splitext(real)[1].lower()
            ctype = _MIME.get(ext, "application/octet-stream")
            base = ctype.split(";")[0].strip()
            download = q.get("download", ["0"])[0] in ("1", "true", "yes")
            try:
                with open(real, "rb") as f:
                    data = f.read()
            except OSError:
                self._json({"error": "read_failed"}, 500)
                return
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            if download or base not in _PREVIEWABLE:
                import urllib.parse as _up
                fn = _up.quote(os.path.basename(real))
                self.send_header("Content-Disposition",
                                 f"attachment; filename*=UTF-8''{fn}")
            self.end_headers()
            self.wfile.write(data)
            return
        if path == "/api/chats":
            self._json({"chats": _chats_index()})
            return
        if path == "/api/chats/one":
            cid = parse_qs(urlparse(self.path).query).get("id", [""])[0]
            d = _chat_read(cid)
            self._json(d if d else {"error": "not_found"})
            return
        if path == "/api/chats/search":
            q = parse_qs(urlparse(self.path).query).get("q", [""])[0]
            self._json({"results": _chats_search(q)})
            return
        if path == "/api/windows":
            self._json({"windows": _windows_list()})
            return
        if path == "/api/calendar":
            self._json({"events": _cal_list()})
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
        # static files (js/css/img/favicon) from web/
        safe = path.lstrip("/").replace("..", "")
        if safe and os.path.exists(os.path.join(_HERE, safe)):
            ext = os.path.splitext(safe)[1].lower()
            ctype = (_MIME.get(ext) or
                     ("application/javascript" if ext == ".js"
                      else "text/css" if ext == ".css"
                      else "image/x-icon" if ext == ".ico"
                      else "application/octet-stream"))
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
                   "windowId": body.get("windowId"),
                   "messages": body.get("messages", [])}
            self._json({"ok": _chat_write(rec), "id": cid})
            return
        if path == "/api/chats/delete":
            _chat_remove((body.get("id") or "").strip())
            self._json({"ok": True})
            return
        if path == "/api/windows/save":
            wid = (str(body.get("id") or "")).strip()
            name = (body.get("name") or "").strip()
            if not name:
                self._json({"error": "missing_name"})
                return
            wins = _windows_read()
            if not wid:
                wid = "w" + str(int(time.time() * 1000))
            found = False
            for w in wins:
                if str(w.get("id")) == wid:
                    w["name"] = name
                    found = True
                    break
            if not found:
                wins.append({"id": wid, "name": name,
                             "ts": int(time.time() * 1000)})
            self._json({"ok": _windows_write(wins), "id": wid, "name": name})
            return
        if path == "/api/windows/delete":
            wid = str(body.get("id") or "").strip()
            wins = [w for w in _windows_read() if str(w.get("id")) != wid]
            ok = _windows_write(wins)
            # keep the chats (user asked they never be deleted): just detach them
            for c in _chats_index():
                if str(c.get("windowId")) == wid:
                    rec = _chat_read(c.get("id"))
                    if rec:
                        rec["windowId"] = None
                        _chat_write(rec)
            self._json({"ok": ok})
            return
        if path == "/api/calendar/suggest":
            self._json({"options": _calendar_suggest(body.get("text", ""))})
            return
        if path == "/api/calendar/add":
            title = (body.get("title") or "").strip()
            due = (body.get("due") or "").strip()
            if not title or not due:
                self._json({"error": "missing_title_or_due"})
                return
            items = _cal_read()
            ev = {"id": "e" + str(int(time.time() * 1000)),
                  "title": title, "due": due,
                  "chatId": body.get("chatId"), "note": body.get("note", ""),
                  "created_ts": int(time.time() * 1000),
                  "done": False, "notified": False}
            items.append(ev)
            self._json({"ok": _cal_write(items), "event": ev})
            return
        if path == "/api/calendar/update":
            eid = str(body.get("id") or "").strip()
            items = _cal_read()
            hit = None
            for e in items:
                if str(e.get("id")) == eid:
                    for k in ("title", "due", "note", "done"):
                        if k in body:
                            e[k] = body[k]
                    if "due" in body:
                        e["notified"] = False   # re-arm reminder on reschedule
                    hit = e
                    break
            self._json({"ok": _cal_write(items) if hit else False, "event": hit})
            return
        if path == "/api/calendar/delete":
            eid = str(body.get("id") or "").strip()
            items = [e for e in _cal_read() if str(e.get("id")) != eid]
            self._json({"ok": _cal_write(items)})
            return

        if path == "/api/chat/stream":
            # Server-Sent Events: streams tool-use steps live and in order,
            # then the final reply. Falls back to /api/chat semantics.
            msg = (body.get("message") or "").strip()
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Connection", "close")
            self.end_headers()

            def sse(obj):
                try:
                    self.wfile.write(("data: " + json.dumps(obj, ensure_ascii=False)
                                      + "\n\n").encode("utf-8"))
                    self.wfile.flush()
                except Exception:
                    pass

            if not msg:
                sse({"t": "error", "message": "empty"})
                return
            try:
                from pipeline.orchestrator import is_document_task, run_pipeline_sync
                _is_task = is_document_task(msg)
            except Exception:
                _is_task = True

            isar = any("؀" <= c <= "ۿ" for c in msg)
            # quick question → answer directly (one step). For news/recency
            # questions or a pasted link, gather live context first so the model
            # answers from current sources instead of refusing.
            if not _is_task:
                ctx = ""
                srcs = []
                try:
                    from pipeline.orchestrator import quick_live_context_ex
                    ctx, srcs = quick_live_context_ex(msg, "ar" if isar else "en")
                except Exception:
                    ctx, srcs = "", []
                mem_ctx = ""
                try:
                    mem_ctx = _recall_memory(msg, exclude_id=body.get("chatId"))
                except Exception:
                    mem_ctx = ""
                sse({"t": "step", "label": (
                    ("بحث حيّ" if isar else "Live search") if ctx
                    else ("التفكير" if isar else "Thinking"))})
                r = _chat(msg, body.get("history"),
                          effort=body.get("effort", "medium"), context=ctx,
                          memory=mem_ctx)
                if r.get("error"):
                    if r.get("error") == "no_key":
                        sse({"t": "reply", "reply": (
                            "لم يتم ضبط مفتاح API بعد. أضِف مفتاحك من قسم Keys."
                            if isar else
                            "No API key is set yet. Add your key in the Keys section.")})
                    else:
                        sse({"t": "reply", "reply": ("خطأ: " if isar else "Error: ")
                             + (r.get("message") or r.get("error"))})
                else:
                    reply = r.get("reply") or ""
                    if reply.strip():
                        reply += _sources_md(srcs, isar)
                    sse({"t": "reply", "reply": reply})
                sse({"t": "done"})
                return

            # document task → full pipeline with live steps
            keysync.load_env()
            if not os.environ.get("WEAVER_API_KEY", "").strip():
                sse({"t": "reply", "reply": (
                    "لم يتم ضبط مفتاح API بعد. أضِف مفتاحك من قسم Keys."
                    if isar else
                    "No API key is set yet. Add your key in the Keys section.")})
                sse({"t": "done"})
                return
            history = body.get("history") or []
            desc = msg
            if history:
                ctx = "\n".join(f"{h.get('role','user')}: {h.get('content','')}"
                                for h in history[-6:] if isinstance(h, dict))
                if ctx.strip():
                    desc = (f"[سياق المحادثة السابقة]\n{ctx}\n\n"
                            f"[الطلب الحالي]\n{msg}")
            desc = _with_memory_for_task(desc, msg, body.get("chatId"))
            try:
                from pipeline.orchestrator import task_priority
                prio = body.get("priority")
                prio = int(prio) if prio is not None else task_priority(msg)
                res = run_pipeline_sync(desc, progress=sse, priority=prio)
            except Exception as e:
                sse({"t": "reply", "reply": ("خطأ: " if isar else "Error: ") + str(e)})
                sse({"t": "done"})
                return
            try:
                _save_chat_doc(body.get("chatId"), res.get("reply") or "")
            except Exception:
                pass
            reply = (res.get("reply") or "").strip()
            out = res.get("output_path")
            if out:
                note = "📄 تم حفظ الملف: " + out
                reply = (reply + "\n\n" + note) if reply else note
            if not reply:
                reply = "(لم يُنتج النظام رداً)"
            sse({"t": "reply", "reply": reply, "output_path": out,
                 "pipeline": {"tools": res.get("tools"), "skills": res.get("skills"),
                              "task_type": res.get("task_type"),
                              "topic": res.get("topic")}})
            sse({"t": "done"})
            return

        if path == "/api/chat":
            msg = (body.get("message") or "").strip()
            if not msg:
                self._json({"error": "empty"})
                return
            # Quick question → fast direct answer (keeps history + effort).
            # Document/generation task → the FULL pipeline below.
            try:
                from pipeline.orchestrator import is_document_task
                _is_task = is_document_task(msg)
            except Exception:
                _is_task = True
            if not _is_task:
                isar = any("؀" <= c <= "ۿ" for c in msg)
                ctx, srcs = "", []
                try:
                    from pipeline.orchestrator import quick_live_context_ex
                    ctx, srcs = quick_live_context_ex(msg, "ar" if isar else "en")
                except Exception:
                    ctx, srcs = "", []
                mem_ctx = ""
                try:
                    mem_ctx = _recall_memory(msg, exclude_id=body.get("chatId"))
                except Exception:
                    mem_ctx = ""
                r = _chat(msg, body.get("history"),
                          effort=body.get("effort", "medium"), context=ctx,
                          memory=mem_ctx)
                if not r.get("error") and (r.get("reply") or "").strip():
                    r["reply"] = r["reply"] + _sources_md(srcs, isar)
                self._json(r)
                return
            # FULL pipeline (WeaverOrchestrator): understand → route → research
            # → credibility → write → clean → verify → export (writes outputs/).
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
            desc = _with_memory_for_task(desc, msg, body.get("chatId"))
            try:
                from pipeline.orchestrator import run_pipeline_sync, task_priority
                prio = body.get("priority")
                prio = int(prio) if prio is not None else task_priority(msg)
                res = run_pipeline_sync(desc, priority=prio)
            except Exception as e:
                self._json({"error": "pipeline_error", "message": str(e)})
                return
            try:
                _save_chat_doc(body.get("chatId"), res.get("reply") or "")
            except Exception:
                pass
            reply = (res.get("reply") or "").strip()
            out = res.get("output_path")
            if out:
                # show the full path — the file lives in the phone's
                # "Weaver Write" folder (outside the project), so a relative
                # path would be misleading.
                note = "📄 تم حفظ الملف: " + out
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
    # background reminder checker (phone notification when a due date arrives)
    try:
        import threading
        threading.Thread(target=_reminder_loop, daemon=True).start()
    except Exception:
        pass
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
