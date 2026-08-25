"""
UniWeb — واجهة موحّدة للتعامل مع الويب.

تجمع خمس أدوات دون تعديل منطق أي منها:
  • curl_impersonate — جلب HTTP مع انتحال بصمة متصفح (يتجاوز مكافحة البوتات)
  • autoscraper      — استخلاص بقواعد متعلَّمة من أمثلة (offline)
  • firecrawl        — scraping ذكي → Markdown نظيف (API)
  • browser_use      — متصفح آلي بالـ AI (نقر، نماذج، تفاعل)
  • agent_reach      — وصول لـ 17 منصة (تويتر، لينكدإن، يوتيوب…)

الاستخدام الأبسط:
    import uniweb
    html = uniweb.fetch("https://example.com")            # curl_impersonate
    data = uniweb.scrape("https://shop.com", wanted=["$29.99"])  # autoscraper
    md = uniweb.fetch("https://blog.com", clean=True)     # firecrawl
    post = uniweb.fetch("https://twitter.com/user/status/123")   # agent_reach
"""

from __future__ import annotations
from typing import Optional, Any

from .router import route, Engine, Task, Capabilities, RouteDecision
from .capabilities import detect_capabilities
from .engines import run_engine

__version__ = "1.0.0"

__all__ = [
    "fetch", "scrape", "crawl", "interact",
    "fetch_detailed", "route", "detect_capabilities",
    "Engine", "Task", "Capabilities", "RouteDecision",
]


def fetch(
    url: str,
    *,
    clean: bool = False,
    engine: Optional[str] = None,
    caps: Optional[Capabilities] = None,
    **kwargs,
) -> Any:
    """
    جلب صفحة ويب. يختار المحرك تلقائياً.

    Args:
        url: الرابط
        clean: نريد Markdown نظيف → firecrawl
        engine: إجبار محرك محدد
        caps: الموارد (تُكتشف تلقائياً)
    """
    return fetch_detailed(
        url, task=Task.FETCH, need_clean_markdown=clean,
        engine=engine, caps=caps, **kwargs
    )["content"]


def scrape(
    url: str,
    *,
    wanted: Optional[list] = None,
    rules_file: Optional[str] = None,
    engine: Optional[str] = None,
    caps: Optional[Capabilities] = None,
    **kwargs,
) -> Any:
    """
    استخلاص بيانات محددة.

    Args:
        wanted: أمثلة للبيانات المطلوبة → autoscraper يتعلّم
        rules_file: قواعد محفوظة → autoscraper يطبّق
    """
    result = fetch_detailed(
        url, task=Task.SCRAPE,
        has_learned_rules=bool(rules_file),
        engine=engine, caps=caps,
        wanted_list=wanted, rules_file=rules_file, **kwargs
    )
    return result["content"]


def crawl(
    url: str,
    *,
    engine: Optional[str] = None,
    caps: Optional[Capabilities] = None,
    **kwargs,
) -> Any:
    """زحف عدة صفحات → firecrawl."""
    return fetch_detailed(
        url, task=Task.CRAWL, need_clean_markdown=True,
        engine=engine, caps=caps, **kwargs
    )["content"]


def interact(
    url: str,
    instruction: str,
    *,
    llm: Any = None,
    engine: Optional[str] = None,
    caps: Optional[Capabilities] = None,
    **kwargs,
) -> Any:
    """
    مهمة تفاعلية (نقر/نماذج) → browser_use.

    Args:
        instruction: وصف المهمة بلغة طبيعية
        llm: كائن النموذج (ChatAnthropic…)

    Returns:
        coroutine — شغّله عبر asyncio.run()
    """
    return fetch_detailed(
        url, task=Task.INTERACT, need_interaction=True,
        engine=engine, caps=caps,
        instruction=instruction, llm=llm, **kwargs
    )["content"]


def fetch_detailed(
    url: str,
    *,
    task: Task = Task.FETCH,
    need_clean_markdown: bool = False,
    need_interaction: bool = False,
    has_learned_rules: bool = False,
    engine: Optional[str] = None,
    caps: Optional[Capabilities] = None,
    **engine_kwargs,
) -> dict:
    """
    الواجهة التفصيلية — تُعيد { content, engine, url, reason, meta }.
    """
    c = caps or detect_capabilities()
    prefer = Engine(engine) if engine else None

    decision = route(
        url, c, task=task,
        has_learned_rules=has_learned_rules,
        need_clean_markdown=need_clean_markdown,
        need_interaction=need_interaction,
        prefer_engine=prefer,
    )

    result = run_engine(decision.engine, url, decision.task, c, **engine_kwargs)
    result["reason"] = decision.reason
    return result
