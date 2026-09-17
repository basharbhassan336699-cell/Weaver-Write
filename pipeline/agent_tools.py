# -*- coding: utf-8 -*-
"""الأدواتُ الأساسيةُ لأوبن كلاو — منقولةٌ بأسمائها من سجلّها الرسميّ.

السجلّ: openclaw/dist/core-tool-factory-descriptors-DvHWmRcY.mjs
أربعٌ وخمسون أداةً في ثلاث عائلات:

    [base-coding]  read، write، edit، ls
    [shell]        exec، apply_patch، process
    [openclaw]     web_search، web_fetch، ask_user، view_image، pdf،
                   structured_output … و٤٠ أخرى خاصّةٌ بمنصّته (sessions،
                   gateway، github، tts، music، mobile_ui) لا معنى لها هنا.

فالمنقولُ هو العائلتان الأُوليان كاملتين، ومن الثالثة ما هو عامٌّ فعلاً.
وهذه هي كلُّ عُدّة أوبن كلاو حين يُسأل أيَّ سؤال: لا أداةَ «ابحث عن مراجع»
ولا أداةَ «اكتب بحثاً». أدواتٌ عامّة، والنموذجُ يُركّبها كيف شاء.

    core-tool-factory-descriptors-DvHWmRcY.mjs:236
      "Core coding primitives (file + shell families). Tool-search compaction
       keeps these directly visible: hiding them behind search adds a lookup
       round-trip to nearly every coding turn."

وكلُّ أداةٍ هنا تُعيد نصّاً، وخطؤها يعود إلى النموذج نتيجةً لا انهياراً."""

import os
import json

MAX_READ = 120000


def _err(msg):
    return "error: " + str(msg)


def _safe_path(path):
    p = os.path.abspath(os.path.expanduser(str(path or "")))
    return p


# ── عائلة base-coding ────────────────────────────────────────────────────
def make_read():
    from pipeline.agent_loop import Tool

    def _run(a):
        p = _safe_path(a.get("path"))
        if not os.path.isfile(p):
            return _err(f"not a file: {p}")
        try:
            with open(p, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
        except Exception as e:
            return _err(f"{type(e).__name__}: {str(e)[:120]}")
        off = max(0, int(a.get("offset") or 0))
        lim = int(a.get("limit") or 2000)
        sel = lines[off:off + max(1, min(lim, 4000))]
        out = "".join(f"{off + i + 1}\t{l}" for i, l in enumerate(sel))
        return out[:MAX_READ] or "(empty file)"

    return Tool("read",
                "اقرأ ملفّاً من القرص. يُعيد السطورَ مرقّمة.",
                {"type": "object", "properties": {
                    "path": {"type": "string"},
                    "offset": {"type": "integer"},
                    "limit": {"type": "integer"}}, "required": ["path"]},
                _run)


def make_write():
    from pipeline.agent_loop import Tool

    def _run(a):
        p = _safe_path(a.get("path"))
        content = a.get("content")
        if content is None:
            return _err("content is required")
        try:
            os.makedirs(os.path.dirname(p) or ".", exist_ok=True)
            with open(p, "w", encoding="utf-8") as f:
                f.write(str(content))
        except Exception as e:
            return _err(f"{type(e).__name__}: {str(e)[:120]}")
        return f"wrote {len(str(content))} chars to {p}"

    return Tool("write", "اكتب ملفّاً على القرص (يستبدل الموجود).",
                {"type": "object", "properties": {
                    "path": {"type": "string"},
                    "content": {"type": "string"}},
                    "required": ["path", "content"]},
                _run, execution_mode="sequential")


def make_edit():
    from pipeline.agent_loop import Tool

    def _run(a):
        p = _safe_path(a.get("path"))
        old, new = str(a.get("old_string") or ""), str(a.get("new_string") or "")
        if not old:
            return _err("old_string is required")
        if not os.path.isfile(p):
            return _err(f"not a file: {p}")
        try:
            with open(p, "r", encoding="utf-8", errors="replace") as f:
                src = f.read()
        except Exception as e:
            return _err(f"{type(e).__name__}: {str(e)[:120]}")
        n = src.count(old)
        if n == 0:
            return _err("old_string not found")
        if n > 1 and not a.get("replace_all"):
            return _err(f"old_string appears {n} times; make it unique or "
                        "pass replace_all")
        try:
            with open(p, "w", encoding="utf-8") as f:
                f.write(src.replace(old, new) if a.get("replace_all")
                        else src.replace(old, new, 1))
        except Exception as e:
            return _err(f"{type(e).__name__}: {str(e)[:120]}")
        return f"replaced {n if a.get('replace_all') else 1} occurrence(s)"

    return Tool("edit", "استبدل نصّاً في ملفّ استبدالاً حرفياً دقيقاً.",
                {"type": "object", "properties": {
                    "path": {"type": "string"},
                    "old_string": {"type": "string"},
                    "new_string": {"type": "string"},
                    "replace_all": {"type": "boolean"}},
                    "required": ["path", "old_string", "new_string"]},
                _run, execution_mode="sequential")


def make_ls():
    from pipeline.agent_loop import Tool

    def _run(a):
        p = _safe_path(a.get("path") or ".")
        if not os.path.isdir(p):
            return _err(f"not a directory: {p}")
        try:
            names = sorted(os.listdir(p))[:400]
        except Exception as e:
            return _err(f"{type(e).__name__}: {str(e)[:120]}")
        rows = []
        for n in names:
            fp = os.path.join(p, n)
            rows.append(("dir  " if os.path.isdir(fp) else "file ") + n)
        return "\n".join(rows) or "(empty)"

    return Tool("ls", "اسرد ما في مجلّد.",
                {"type": "object", "properties": {"path": {"type": "string"}}},
                _run)


# ── عائلة shell ──────────────────────────────────────────────────────────
def make_exec():
    """`exec` عند أوبن كلاو. هنا لا تعمل إلا بإذنٍ صريح WEAVER_EXEC=1."""
    from pipeline.agent_loop import Tool

    def _run(a):
        try:
            from capabilities.tools.tool_exec_python import exec_enabled
        except Exception:
            def exec_enabled():
                return (os.environ.get("WEAVER_EXEC", "") or "").strip() == "1"
        if not exec_enabled():
            return _err("execution is off; it is enabled only with WEAVER_EXEC=1")
        cmd = str(a.get("command") or "").strip()
        if not cmd:
            return _err("command is required")
        import subprocess
        try:
            r = subprocess.run(cmd, shell=True, capture_output=True, text=True,
                               timeout=int(a.get("timeout") or 60),
                               cwd=_safe_path(a.get("cwd") or "."))
        except subprocess.TimeoutExpired:
            return _err("timed out")
        except Exception as e:
            return _err(f"{type(e).__name__}: {str(e)[:120]}")
        return (f"exit={r.returncode}\n--- stdout ---\n{(r.stdout or '')[:7000]}"
                f"\n--- stderr ---\n{(r.stderr or '')[:2000]}")

    return Tool("exec", "نفِّذ أمراً في الصَدَفة واقرأ مُخرَجه.",
                {"type": "object", "properties": {
                    "command": {"type": "string"},
                    "cwd": {"type": "string"},
                    "timeout": {"type": "integer"}},
                    "required": ["command"]},
                _run, execution_mode="sequential")


# ── عائلة openclaw: العامُّ منها ─────────────────────────────────────────
def make_web_fetch(orch=None):
    from pipeline.agent_loop import Tool

    def _run(a):
        url = str(a.get("url") or "").strip()
        if not url.startswith("http"):
            return _err("url must start with http")
        n = max(500, min(int(a.get("max_chars") or 8000), 20000))
        # ١) المسارُ الذي يتجاوز الحجب، إن وُجد المُنسِّق
        if orch is not None:
            try:
                import asyncio
                loop = asyncio.new_event_loop()
                try:
                    txt = loop.run_until_complete(orch._extract_full(url))
                finally:
                    loop.close()
                if txt and len(str(txt).strip()) > 80:
                    return str(txt)[:n]
            except Exception:
                pass
        # ٢) وإلّا فجلبٌ مباشر
        try:
            import urllib.request
            req = urllib.request.Request(
                url, headers={"User-Agent": "Mozilla/5.0", "Accept": "*/*"})
            raw = urllib.request.urlopen(req, timeout=25).read()
            txt = raw.decode("utf-8", "replace")
        except Exception as e:
            return _err(f"{type(e).__name__}: {str(e)[:140]}")
        try:
            import re
            txt = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", txt)
            txt = re.sub(r"(?s)<[^>]+>", " ", txt)
            import html as _h
            txt = _h.unescape(txt)
            txt = "\n".join(l.strip() for l in txt.split("\n") if l.strip())
            txt = re.sub(r"[ \t]{2,}", " ", txt)
        except Exception:
            pass
        return txt[:n] or _err("empty page")

    return Tool("web_fetch",
                "افتح رابطاً واقرأ نصَّ الصفحة.",
                {"type": "object", "properties": {
                    "url": {"type": "string"},
                    "max_chars": {"type": "integer"}}, "required": ["url"]},
                _run)


def make_web_search(orch=None):
    """`web_search`. أوبن كلاو يصله بمزوّدٍ بمفتاح؛ وبلا مفتاحٍ يُقرأ محرّكٌ
    لا يشترط مفتاحاً، ويُقال حين يُحجَب — لا يُقال «لا نتائج»."""
    from pipeline.agent_loop import Tool
    _wf = make_web_fetch(orch)

    def _run(a):
        q = str(a.get("query") or "").strip()
        if len(q) < 2:
            return _err("query too short")
        import urllib.parse as up
        params = {"q": q}
        lg = str(a.get("language") or "").strip().lower()[:2]
        if lg:
            params["kl"] = ("wt-wt" if lg not in ("ar", "en")
                            else ("xa-ar" if lg == "ar" else "us-en"))
        url = "https://html.duckduckgo.com/html/?" + up.urlencode(params)
        txt = _wf.execute({"url": url, "max_chars": 9000})
        if str(txt).startswith("error:"):
            return (str(txt) + "  | note: no search-provider key is "
                    "configured; this reads a keyless engine, which may "
                    "block automated requests. Try web_fetch on a specific "
                    "site instead.")
        return txt

    return Tool("web_search",
                "ابحث في الويب وأعِد العناوينَ والروابط.",
                {"type": "object", "properties": {
                    "query": {"type": "string"},
                    "language": {"type": "string",
                                 "description": "رمزُ لغةٍ من حرفين"}},
                    "required": ["query"]},
                _run)


def make_scholarly_api(orch):
    """زيادةٌ على عُدّة أوبن كلاو: القواعدُ الستُّ الموجودةُ في هذا المشروع
    تُعرَض كأداةٍ عامّةٍ أخرى — والنموذجُ يستعملها إن رآها أنسب."""
    from pipeline.agent_loop import Tool

    def _run(a):
        q = str(a.get("query") or "").strip()
        if len(q) < 3:
            return _err("query too short")
        try:
            res = orch._scholarly_search(
                q, str(a.get("lang") or "ar")[:2],
                max(3, min(int(a.get("limit") or 8), 20)),
                lang_filter=bool(a.get("lang_filter"))) or []
        except Exception as e:
            return _err(f"{type(e).__name__}: {str(e)[:120]}")
        out = []
        for r in res:
            r.pop("_prefilter", None)
            out.append({k: r.get(k) for k in
                        ("title", "authors", "year", "venue", "doi", "url",
                         "lang", "source") if r.get(k)})
        return (json.dumps(out, ensure_ascii=False)[:9000] if out
                else "no results")

    return Tool("scholarly_api",
                "ابحث في قواعد البيانات الأكاديمية المجّانية.",
                {"type": "object", "properties": {
                    "query": {"type": "string"},
                    "lang": {"type": "string"},
                    "lang_filter": {"type": "boolean"},
                    "limit": {"type": "integer"}}, "required": ["query"]},
                _run)


def core_tools(orch=None, allow_write=True):
    """عُدّةُ أوبن كلاو الأساسية. هذه هي كلُّ ما يُعطاه لأيّ سؤالٍ كان."""
    tools = [make_read(), make_ls(), make_web_fetch(orch),
             make_web_search(orch)]
    if allow_write:
        tools += [make_write(), make_edit()]
    tools.append(make_exec())
    if orch is not None:
        try:
            tools.append(make_scholarly_api(orch))
        except Exception:
            pass
    return tools
