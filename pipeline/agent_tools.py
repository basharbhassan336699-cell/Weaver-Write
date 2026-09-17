# -*- coding: utf-8 -*-
"""الأدواتُ التي تُعطى لحلقة الوكيل — هي عينُها التي استعملها أوبن كلاو.

في تشغيلِ أوبن كلاو الذي عاد بتسعةِ مراجعَ عربيةٍ حقيقية، كانت الأدواتُ:
    web_fetch  ⟶ Google Scholar بالعربية، ثمّ صفحةُ كلِّ مرجعٍ للتحقّق
    exec       ⟶ OpenAlex API بـPython
    exec       ⟶ Crossref API بـcurl
ولا أداةَ اسمُها «ابحث عن مراجع». أدواتٌ عامّة، والنموذجُ يركّبها.

فهذه أربعُ أدواتٍ عامّةٍ مبنيّةٌ على ما في المشروع أصلاً:
    web_fetch        ← `_extract_full` (تمرّ على UniWeb/curl_impersonate)
    scholarly_api    ← الدوالُّ الستُّ الموجودة
    run_python       ← `tool_exec_python` (مطفأةٌ ما لم يُؤذَن لها)
    finish           ← لا شيء؛ وجودُها في الكتالوج يُعلِم النموذجَ كيف يقف

ولا واحدةٌ منها تعرف شيئاً عن «المراجع العربية». النموذجُ هو الذي يعرف."""

import json


def _tool(cls):
    from pipeline.agent_loop import Tool
    return Tool


def make_web_fetch(orch, loop=None):
    """افتح صفحةً واقرأ نصَّها. هذه هي `web_fetch` عند أوبن كلاو."""
    from pipeline.agent_loop import Tool

    def _run(args):
        url = str((args or {}).get("url") or "").strip()
        if not url.startswith("http"):
            return "error: url must start with http"
        import asyncio
        try:
            _l = loop or asyncio.get_event_loop()
            txt = _l.run_until_complete(orch._extract_full(url)) \
                if not _l.is_running() else None
        except Exception as e:
            return f"error: {type(e).__name__}: {str(e)[:120]}"
        if txt is None:
            return ("error: page could not be read (blocked, or an async "
                    "context already running)")
        txt = str(txt)
        n = int((args or {}).get("max_chars") or 8000)
        return txt[:max(500, min(n, 20000))] or "error: empty page"

    return Tool(
        name="web_fetch",
        description=("افتح رابطاً واقرأ نصَّ الصفحة كاملاً (يتجاوز حجبَ "
                     "الآليّات ببصمة متصفّح حقيقيّ). استعمله لصفحات البحث "
                     "العلمي، ولمستودعات الجامعات، وللتحقّق من وجود مرجعٍ "
                     "بفتح صفحته."),
        parameters={"type": "object", "properties": {
            "url": {"type": "string", "description": "الرابط الكامل"},
            "max_chars": {"type": "integer",
                          "description": "أقصى عددِ حروفٍ يُعاد (افتراضياً 8000)"}},
            "required": ["url"]},
        execute=_run)


def make_scholarly_api(orch):
    """اسأل قواعدَ البيانات الأكاديمية. `lang_filter` يضيِّق باللغة حيث يُدعَم."""
    from pipeline.agent_loop import Tool

    def _run(args):
        q = str((args or {}).get("query") or "").strip()
        if len(q) < 3:
            return "error: query too short"
        lg = str((args or {}).get("lang") or "").strip().lower()[:2]
        n = int((args or {}).get("limit") or 8)
        try:
            res = orch._scholarly_search(
                q, lg or "ar", max(3, min(n, 20)),
                lang_filter=bool((args or {}).get("lang_filter"))) or []
        except Exception as e:
            return f"error: {type(e).__name__}: {str(e)[:120]}"
        out = []
        for r in res:
            r.pop("_prefilter", None)
            out.append({k: r.get(k) for k in
                        ("title", "authors", "year", "venue", "doi", "url",
                         "lang", "source") if r.get(k)})
        if not out:
            gap = ", ".join(orch._lang_filter_gap())
            return ("no results. note: language filtering is not supported by "
                    f"these engines ({gap}); only openalex and doaj apply it.")
        return json.dumps(out, ensure_ascii=False)[:9000]

    return Tool(
        name="scholarly_api",
        description=("ابحث في قواعد البيانات الأكاديمية المجّانية (OpenAlex، "
                     "Crossref، arXiv، Semantic Scholar، DOAJ، Europe PMC). "
                     "تُغطّي الإنجليزيةَ أكثر بكثيرٍ من غيرها."),
        parameters={"type": "object", "properties": {
            "query": {"type": "string"},
            "lang": {"type": "string", "description": "رمزُ لغةٍ من حرفين"},
            "lang_filter": {"type": "boolean",
                            "description": "ضيِّق باللغة (openalex وdoaj فقط)"},
            "limit": {"type": "integer"}}, "required": ["query"]},
        execute=_run)


def make_run_python():
    """نفِّذ سكربت Python. `exec` عند أوبن كلاو — مطفأةٌ ما لم يُؤذَن لها."""
    from pipeline.agent_loop import Tool

    def _run(args):
        try:
            from capabilities.tools.tool_exec_python import (
                exec_enabled, run_python)
        except Exception:
            return "error: exec tool unavailable"
        if not exec_enabled():
            return ("error: execution is off. It is enabled only with "
                    "WEAVER_EXEC=1.")
        code = str((args or {}).get("code") or "")
        if len(code.strip()) < 5:
            return "error: no code"
        try:
            res = run_python(code, out_path=None, payload_text=None,
                             timeout=int((args or {}).get("timeout") or 40))
        except Exception as e:
            return f"error: {type(e).__name__}: {str(e)[:150]}"
        return json.dumps(res, ensure_ascii=False, default=str)[:6000]

    return Tool(
        name="run_python",
        description=("نفِّذ سكربت Python واقرأ مُخرَجه. استعمله لسؤال واجهةِ "
                     "برمجةٍ لا تغطّيها الأدواتُ الأخرى."),
        parameters={"type": "object", "properties": {
            "code": {"type": "string"},
            "timeout": {"type": "integer"}}, "required": ["code"]},
        execution_mode="sequential",
        execute=_run)


def reference_tools(orch, loop=None):
    """الأدواتُ التي تُعطى لمهمّة إيجاد المراجع. عامّةٌ كلُّها."""
    tools = [make_web_fetch(orch, loop), make_scholarly_api(orch)]
    try:
        from capabilities.tools.tool_exec_python import exec_enabled
        if exec_enabled():
            tools.append(make_run_python())
    except Exception:
        pass
    return tools


def reference_task(topic, want_lang, need, lang="ar"):
    """المهمّةُ كما تُعطى للنموذج — لا خطواتٌ تُملى عليه، بل ما هو مطلوب.

    أوبن كلاو لم يُملَ عليه «افتح جوجل سكولار»: قيل له ما المطلوبُ فاختار
    الطريق. فهنا كذلك — الأدواتُ في الكتالوج، والقرارُ له."""
    _n = {"ar": "العربية", "en": "الإنجليزية"}.get(want_lang, want_lang)
    if lang == "en":
        return (f"Find {need} real, verifiable academic references in "
                f"{want_lang} on this topic:\n\"{topic}\"\n\n"
                "Each must be peer-reviewed or an academic thesis, and must "
                "actually exist — open its page and confirm before counting "
                "it. Do not invent a reference and do not count one you could "
                "not open.\n\n"
                'When done return: {"done":true,"answer":"<JSON list of '
                '{title,authors,year,venue,url,verified}>"}')
    return (f"جِد {need} مرجعاً أكاديمياً حقيقياً بـ{_n} في هذا الموضوع:\n"
            f"«{topic}»\n\n"
            "شرطُها: محكَّمةٌ أو رسائلُ جامعية، وموجودةٌ فعلاً — افتح صفحةَ "
            "كلِّ مرجعٍ وتأكّد قبل أن تعدَّه. لا تخترع مرجعاً، ولا تعُدَّ "
            "مرجعاً لم تستطع فتحَ صفحته.\n\n"
            "وإذا اكتملت أعِد:\n"
            '{"done":true,"answer":"<قائمة JSON من '
            '{title,authors,year,venue,url,verified}>"}')
