"""live_steps.py — ما يفعله المحرّكُ الآن، خطوةً خطوة، لحظةَ حدوثه.

كانت بطاقاتُ الأدوات تُطلب بعد انتهاء النوبة (`sessions export-trajectory`)،
فلا يرى المستخدمُ أثناء العمل إلا «التفكير» عالقاً، ثمّ بعد قرابة دقيقةٍ
«Tool calls 11» دفعةً واحدة. والسببُ مقيس:

    جدولُ trajectory_runtime_events   ⟵ يُكتب عند نهاية النوبة فقط
    جدولُ transcript_events           ⟵ يُكتب حيّاً:
        رسالةُ النموذج (كلامُه + الأداةُ التي سيستدعيها) لحظةَ وصولها،
        ونتيجةُ الأداة لحظةَ انتهائها (قِيس: أمرٌ مدّتُه ٣٫٦ ث ظهرت نتيجتُه
        بعد ٣٫٦ ث بالضبط)

فهنا قراءةٌ لِما جدّ في سجلّ الجلسة (قراءةً فقط — لا يُكتب شيءٌ في قاعدة
المحرّك) وتحويلُه إلى أحداثٍ بسيطة للواجهة:

    {"k": "note",   "text": …}                       كلامُ النموذج بين الأدوات
    {"k": "think",  "text": …}                       تفكيرٌ (إن أرسله النموذج)
    {"k": "call",   "id", "name", "args"}             أداةٌ بدأت
    {"k": "result", "id", "name", "ok", "text", "details"}   ونتيجتُها

لا يرفع أبداً: أيُّ عجزٍ ⟵ لا أحداث، والعرضُ القديمُ يبقى كما هو.
"""
from __future__ import annotations

import json
import os
import re
import sqlite3

MAX_TEXT = 8000
MAX_ARG = 3000


def _db_path():
    try:
        from pipeline import weaver_core as wc
        return os.path.join(wc._STATE_DIR, "agents", "main", "agent",
                            "openclaw-agent.sqlite")
    except Exception:
        return ""


def _key(session):
    try:
        from pipeline import weaver_core as wc
        return wc.session_key(session)
    except Exception:
        return ""


def _trim(v, n=MAX_ARG):
    if isinstance(v, str):
        return v if len(v) <= n else v[:n] + "…"
    if isinstance(v, dict):
        return {k: _trim(x, n) for k, x in list(v.items())[:30]}
    if isinstance(v, list):
        return [_trim(x, n) for x in v[:30]]
    return v


def _text_of(content):
    if isinstance(content, str):
        return content
    out = []
    for c in content or []:
        if isinstance(c, dict) and c.get("type") == "text":
            out.append(c.get("text") or "")
    return "\n".join(out)


class Tail:
    """قارئُ سجلّ جلسةٍ واحدة: ما بعد لحظة الإنشاء فقط."""

    def __init__(self, session):
        self.path = _db_path()
        self.key = _key(session)
        self.seen = {}            # session_id ⟵ آخرُ seq قُرئ
        self.ok = bool(self.path and self.key)
        if self.ok:
            # ما في السجلّ قبل النوبة لا يُعرض
            for sid, mx in self._query(
                    "SELECT session_id, MAX(seq) FROM transcript_events "
                    "WHERE session_id IN (SELECT session_id FROM session_windows "
                    "WHERE session_key = ?) GROUP BY session_id", (self.key,)):
                self.seen[sid] = mx if mx is not None else -1

    def _query(self, sql, params=()):
        if not os.path.isfile(self.path):
            return []
        db = None
        try:
            db = sqlite3.connect("file:%s?mode=ro" % self.path, uri=True, timeout=1.5)
            return list(db.execute(sql, params))
        except Exception:
            return []
        finally:
            if db is not None:
                try:
                    db.close()
                except Exception:
                    pass

    def poll(self):
        """أحداثُ ما جدّ منذ آخر نداء (بترتيبها)."""
        if not self.ok:
            return []
        rows = []
        sids = [r[0] for r in self._query(
            "SELECT session_id FROM session_windows WHERE session_key = ?", (self.key,))]
        cur = self._query("SELECT current_session_id FROM session_nodes "
                          "WHERE session_key = ?", (self.key,))
        if cur and cur[0][0] and cur[0][0] not in sids:
            sids.append(cur[0][0])
        for sid in sids:
            last = self.seen.get(sid, -1)
            new = self._query("SELECT seq, event_json FROM transcript_events "
                              "WHERE session_id = ? AND seq > ? ORDER BY seq",
                              (sid, last))
            for seq, ej in new:
                self.seen[sid] = max(self.seen.get(sid, -1), seq)
                rows.append(ej)
        out = []
        for ej in rows:
            try:
                out.extend(events_of(json.loads(ej)))
            except Exception:
                continue
        return out


def events_of(ev):
    """حدثُ سجلٍّ واحد ⟵ أحداثُ الواجهة."""
    if not isinstance(ev, dict) or ev.get("type") != "message":
        return []
    m = ev.get("message") or {}
    role = m.get("role")
    if role == "assistant":
        content = m.get("content")
        if not isinstance(content, list):
            return []
        calls = [c for c in content if isinstance(c, dict) and c.get("type") == "toolCall"]
        if not calls:
            return []            # الجوابُ النهائيّ — يصل بطريقه المعتاد
        out = []
        for c in content:
            if not isinstance(c, dict):
                continue
            t = c.get("type")
            if t == "text" and (c.get("text") or "").strip():
                out.append({"k": "note", "text": _trim(c["text"].strip(), 4000)})
            elif t == "thinking" and (c.get("thinking") or c.get("text") or "").strip():
                out.append({"k": "think",
                            "text": _trim((c.get("thinking") or c.get("text")).strip(), 1500)})
            elif t == "toolCall":
                args = c.get("arguments")
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except Exception:
                        args = {"input": args}
                out.append({"k": "call", "id": str(c.get("id") or ""),
                            "name": str(c.get("name") or ""),
                            "args": _trim(args if isinstance(args, dict) else {})})
        return out
    if role == "toolResult":
        det = m.get("details") if isinstance(m.get("details"), dict) else {}
        keep = {}
        for k in ("exitCode", "durationMs", "status", "created", "changed", "diff",
                  "patch", "cwd", "url", "title", "finalUrl", "provider", "count"):
            if k in det:
                keep[k] = _trim(det[k], 4000)
        name = str(m.get("toolName") or "")
        text = _text_of(m.get("content"))
        ok = not bool(m.get("isError")) and det.get("status") != "failed"
        if name in ("web_search", "web_fetch"):
            text, extra, ok2 = _web(name, text)
            keep.update(extra)
            ok = ok and ok2
        return [{"k": "result", "id": str(m.get("toolCallId") or ""),
                 "name": name, "ok": ok,
                 "text": _trim(text, MAX_TEXT), "details": keep}]
    return []


_MARK = re.compile(r"<<<\s*(?:END[\s_]+)?EXTERNAL[\s_]+UNTRUSTED[\s_]+CONTENT[^>]*>>>", re.I)


def unwrap(s):
    """نصٌّ خارجيٌّ ملفوفٌ بعلامات المحرّك (تحذيرٌ ومصدرٌ ثمّ ---) ⟵ النصُّ نفسُه."""
    s = str(s or "")
    if "EXTERNAL" not in s.upper():
        return s.strip()
    parts = _MARK.split(s)
    body = parts[1] if len(parts) >= 3 else parts[-1]
    if "\n---\n" in body:
        body = body.split("\n---\n", 1)[1]
    elif body.lstrip().startswith("Source:"):
        body = body.split("\n", 1)[1] if "\n" in body else ""
    return body.strip()


def _json_in(text):
    i = text.find("{")
    if i < 0:
        return None
    try:
        return json.loads(text[i:])
    except Exception:
        return None


def _web(name, text):
    """نتيجةُ بحثٍ/جلبٍ ⟵ (نصٌّ مختصر، تفاصيلُ منظّمة، نجحت؟)."""
    d = _json_in(text)
    if not isinstance(d, dict):
        return unwrap(text), {}, True
    if d.get("status") == "error" or d.get("kind") == "error" or d.get("error"):
        msg = d.get("message") or d.get("error") or ""
        return unwrap(msg)[:600], {}, False
    if name == "web_search":
        res = []
        for r in (d.get("results") or [])[:20]:
            if not isinstance(r, dict):
                continue
            url = str(r.get("url") or "")
            site = str(r.get("siteName") or "")
            if not site:
                site = re.sub(r"^https?://(www\.)?", "", url).split("/")[0]
            res.append({"title": unwrap(r.get("title"))[:200], "url": url[:500],
                        "site": site[:80],
                        "snippet": unwrap(r.get("snippet") or r.get("description"))[:300]})
        extra = {"results": res, "query": str(d.get("query") or "")[:300]}
        ans = unwrap(d.get("content")) if d.get("kind") == "answer" else ""
        return ans, extra, True
    # web_fetch
    extra = {}
    for k in ("url", "finalUrl", "title", "status"):
        if d.get(k):
            extra[k] = unwrap(d.get(k))[:500] if k == "title" else str(d.get(k))[:500]
    body = d.get("text") or d.get("content") or d.get("markdown") or ""
    return unwrap(body), extra, True
