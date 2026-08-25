"""
طبقة المحركات — تستدعي كل أداة أصلية دون تعديل منطقها.

كل دالة غلاف (adapter) تترجم واجهة UniWeb الموحّدة إلى استدعاء
الأداة الأصلية كما هي في engines_src_*/.
"""

from __future__ import annotations
from typing import Optional, Any

from .router import Engine, Task, Capabilities


def run_engine(
    engine: Engine,
    url: str,
    task: Task,
    caps: Capabilities,
    **kwargs,
) -> dict:
    """
    يشغّل المحرك المختار ويُعيد نتيجة موحّدة:
      { content, engine, url, meta }
    """
    if engine == Engine.CURL_IMPERSONATE:
        return _run_curl(url, **kwargs)
    if engine == Engine.AUTOSCRAPER:
        return _run_autoscraper(url, **kwargs)
    if engine == Engine.FIRECRAWL:
        return _run_firecrawl(url, task, caps, **kwargs)
    if engine == Engine.BROWSER_USE:
        return _run_browser_use(url, caps, **kwargs)
    if engine == Engine.AGENT_REACH:
        return _run_agent_reach(url, **kwargs)
    raise ValueError(f"محرك غير معروف: {engine}")


# ─────────────────────────────────────────────────────────
# curl_impersonate — جلب HTTP مع انتحال بصمة
# ─────────────────────────────────────────────────────────

def _run_curl(url: str, *, browser: str = "chrome116", **kwargs) -> dict:
    """
    يستخدم curl_cffi (الغلاف Python لـ curl-impersonate) كما هو.
    الكود C الأصلي في engines_src_curl_impersonate/ — لا يُعدَّل.
    """
    try:
        from curl_cffi import requests as cffi_requests
    except ImportError:
        raise ImportError(
            "curl_cffi غير مثبت. ثبّته: pip install curl_cffi\n"
            "(الغلاف Python الرسمي لـ curl-impersonate)\n"
            "أو ابنِ curl-impersonate من engines_src_curl_impersonate/"
        )

    # curl_cffi يدعم impersonate مباشرة
    resp = cffi_requests.get(url, impersonate=browser, **kwargs)
    return {
        "content": resp.text,
        "engine": "curl_impersonate",
        "url": url,
        "meta": {
            "status": resp.status_code,
            "browser_fingerprint": browser,
            "headers": dict(resp.headers),
        },
    }


# ─────────────────────────────────────────────────────────
# autoscraper — استخلاص بقواعد متعلَّمة
# ─────────────────────────────────────────────────────────

def _run_autoscraper(
    url: str,
    *,
    wanted_list: Optional[list] = None,
    rules_file: Optional[str] = None,
    html: Optional[str] = None,
    save_rules: Optional[str] = None,
    **kwargs,
) -> dict:
    """
    يستدعي AutoScraper كما هو.
    الكود الأصلي في engines_src_autoscraper/autoscraper/ — لا يُعدَّل.

    يمرّر html مباشرة إن وُجد (بلا اتصال إنترنت)، وإلا يستخدم url.
    """
    try:
        from autoscraper import AutoScraper
    except ImportError:
        raise ImportError(
            "autoscraper غير مثبت. ثبّته من engines_src_autoscraper/:\n"
            "  pip install -e engines_src_autoscraper/"
        )

    scraper = AutoScraper()

    # المصدر: html مباشر (offline) أو url (يجلب)
    src = {"html": html} if html else {"url": url}

    if rules_file:
        # تحميل قواعد متعلَّمة سابقاً وتطبيقها
        scraper.load(rules_file)
        result = scraper.get_result_similar(**src)
    elif wanted_list:
        # تعلّم قواعد جديدة من أمثلة (توقيع الدالة الأصلي)
        result = scraper.build(wanted_list=wanted_list, **src)
        if save_rules:
            scraper.save(save_rules)
    else:
        raise ValueError(
            "autoscraper يحتاج إما wanted_list (للتعلّم) "
            "أو rules_file (لتطبيق قواعد محفوظة)."
        )

    return {
        "content": result,
        "engine": "autoscraper",
        "url": url,
        "meta": {"learned": bool(wanted_list), "applied_rules": bool(rules_file)},
    }


# ─────────────────────────────────────────────────────────
# firecrawl — scraping ذكي عبر API
# ─────────────────────────────────────────────────────────

def _run_firecrawl(
    url: str,
    task: Task,
    caps: Capabilities,
    **kwargs,
) -> dict:
    """
    يستدعي Firecrawl SDK كما هو.
    الكود الأصلي في engines_src_firecrawl/firecrawl/ — لا يُعدَّل.
    """
    try:
        from firecrawl import FirecrawlApp
    except ImportError:
        raise ImportError(
            "firecrawl غير مثبت. ثبّته: pip install firecrawl-py\n"
            "أو من engines_src_firecrawl/: pip install -e engines_src_firecrawl/"
        )

    if not caps.firecrawl_key:
        raise RuntimeError("firecrawl يحتاج API key. ضعه في FIRECRAWL_API_KEY.")

    app = FirecrawlApp(api_key=caps.firecrawl_key)

    if task == Task.CRAWL:
        result = app.crawl_url(url, **kwargs)
    else:
        result = app.scrape_url(url, **kwargs)

    # استخراج المحتوى النظيف
    content = ""
    if isinstance(result, dict):
        content = result.get("markdown") or result.get("content") or str(result)
    else:
        content = getattr(result, "markdown", None) or str(result)

    return {
        "content": content,
        "engine": "firecrawl",
        "url": url,
        "meta": {"task": task.value, "raw": result},
    }


# ─────────────────────────────────────────────────────────
# browser_use — متصفح آلي بالـ AI
# ─────────────────────────────────────────────────────────

def _run_browser_use(
    url: str,
    caps: Capabilities,
    *,
    instruction: Optional[str] = None,
    llm: Any = None,
    **kwargs,
) -> dict:
    """
    يستدعي browser_use Agent كما هو.
    الكود الأصلي في engines_src_browser_use/browser_use/ — لا يُعدَّل.

    ملاحظة: browser_use غير متزامن (async) ويحتاج LLM object.
    """
    try:
        from browser_use import Agent
    except ImportError:
        raise ImportError(
            "browser_use غير مثبت. ثبّته من engines_src_browser_use/:\n"
            "  pip install -e engines_src_browser_use/\n"
            "  playwright install chromium\n"
            "ويحتاج LLM (anthropic/openai)."
        )

    if not instruction:
        instruction = f"افتح {url} واستخرج المحتوى الرئيسي"
    if llm is None:
        raise ValueError(
            "browser_use يحتاج كائن LLM. مرّره عبر llm=... "
            "(مثل ChatAnthropic أو ChatOpenAI)."
        )

    # browser_use غير متزامن — نعيد coroutine للمستدعي ليشغّله
    async def _task():
        agent = Agent(task=instruction, llm=llm, **kwargs)
        history = await agent.run()
        return history

    return {
        "content": _task(),   # coroutine — يُشغَّل عبر asyncio.run
        "engine": "browser_use",
        "url": url,
        "meta": {"instruction": instruction, "is_async": True},
    }


# ─────────────────────────────────────────────────────────
# agent_reach — وصول لمنصات محددة
# ─────────────────────────────────────────────────────────

def _run_agent_reach(url: str, *, config: Any = None, **kwargs) -> dict:
    """
    يستدعي AgentReach كما هو.
    الكود الأصلي في engines_src_agent_reach/agent_reach/ — لا يُعدَّل.
    """
    try:
        from agent_reach import AgentReach
    except ImportError:
        raise ImportError(
            "agent_reach غير مثبت. ثبّته من engines_src_agent_reach/:\n"
            "  pip install -e engines_src_agent_reach/"
        )

    reach = AgentReach(config=config) if config else AgentReach()
    content = reach.read(url) if hasattr(reach, "read") else reach.fetch(url)

    return {
        "content": content,
        "engine": "agent_reach",
        "url": url,
        "meta": {"platform_native": True},
    }
