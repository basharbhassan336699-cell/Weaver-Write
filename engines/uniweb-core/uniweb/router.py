"""
UniWeb Router — يختار المحرك المناسب لكل مهمة ويب.

يجمع خمس أدوات دون تعديل منطق أي منها:

  ┌──────────────────┬────────────────────────────────┬──────────────────┐
  │ المحرك             │ التخصص                          │ المتطلبات         │
  ├──────────────────┼────────────────────────────────┼──────────────────┤
  │ curl_impersonate │ جلب HTTP مع انتحال بصمة TLS     │ C build          │
  │                  │ يتجاوز TLS/HTTP2 fingerprinting  │                  │
  ├──────────────────┼────────────────────────────────┼──────────────────┤
  │ autoscraper      │ استخلاص بقواعد متعلَّمة من أمثلة   │ CPU فقط (offline)│
  │                  │ يتعلم مرة ويطبّق على صفحات مشابهة  │                  │
  ├──────────────────┼────────────────────────────────┼──────────────────┤
  │ firecrawl        │ scraping ذكي → Markdown نظيف     │ API key + إنترنت │
  │                  │ crawl/map/search بلا قواعد        │                  │
  ├──────────────────┼────────────────────────────────┼──────────────────┤
  │ browser_use      │ متصفح آلي بالـ AI: نقر، كتابة     │ Chromium + LLM   │
  │                  │ مهام تفاعلية معقدة                │                  │
  ├──────────────────┼────────────────────────────────┼──────────────────┤
  │ agent_reach      │ وصول لـ 17 منصة محددة            │ cookies/APIs     │
  │                  │ Twitter, LinkedIn, YouTube...    │                  │
  └──────────────────┴────────────────────────────────┴──────────────────┘

منطق الاختيار:
  1. رابط منصة معروفة (تويتر، يوتيوب…)   → agent_reach
  2. مهمة تفاعلية (نقر، ملء نماذج، تنقّل) → browser_use
  3. استخلاص بقواعد متكررة معروفة          → autoscraper
  4. scraping ذكي بلا قواعد + API متاح     → firecrawl
  5. جلب HTML بسيط + حماية مكافحة البوتات  → curl_impersonate
  6. جلب HTML بسيط عادي                    → curl_impersonate (افتراضي)
"""

from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
from urllib.parse import urlparse


class Engine(str, Enum):
    CURL_IMPERSONATE = "curl_impersonate"
    AUTOSCRAPER = "autoscraper"
    FIRECRAWL = "firecrawl"
    BROWSER_USE = "browser_use"
    AGENT_REACH = "agent_reach"


class Task(str, Enum):
    FETCH = "fetch"          # جلب HTML خام
    SCRAPE = "scrape"        # استخلاص بيانات محددة
    CRAWL = "crawl"          # زحف عدة صفحات
    INTERACT = "interact"    # مهمة تفاعلية (نقر/نماذج)
    PLATFORM = "platform"    # منصة محددة


# ── المنصات التي يدعمها agent_reach ──
KNOWN_PLATFORMS = {
    "twitter.com": "twitter", "x.com": "twitter",
    "linkedin.com": "linkedin",
    "youtube.com": "youtube", "youtu.be": "youtube",
    "reddit.com": "reddit",
    "instagram.com": "instagram",
    "facebook.com": "facebook",
    "github.com": "github",
    "bilibili.com": "bilibili",
    "xiaohongshu.com": "xiaohongshu",
    "zhihu.com": "zhihu",
    "xueqiu.com": "xueqiu",
    "v2ex.com": "v2ex",
}


@dataclass
class Capabilities:
    """الموارد المتاحة."""
    has_curl_impersonate: bool = False   # مبني ومتاح
    has_firecrawl_key: bool = False      # API key متاح
    firecrawl_key: Optional[str] = None
    has_browser: bool = False            # Chromium + playwright
    has_llm: bool = False                # نموذج للـ browser_use
    llm_provider: Optional[str] = None   # anthropic/openai/...
    platform_cookies: dict = field(default_factory=dict)  # cookies للمنصات


@dataclass
class RouteDecision:
    engine: Engine
    reason: str
    task: Task
    fallback: Optional[Engine] = None


def _platform_of(url: str) -> Optional[str]:
    """يستخرج اسم المنصة من الرابط إن كانت معروفة."""
    try:
        host = urlparse(url).netloc.lower()
        host = host.replace("www.", "").replace("m.", "")
        for domain, platform in KNOWN_PLATFORMS.items():
            if host == domain or host.endswith("." + domain):
                return platform
    except Exception:
        pass
    return None


def route(
    url: str,
    caps: Capabilities,
    *,
    task: Task = Task.FETCH,
    has_learned_rules: bool = False,   # autoscraper تعلّم سابقاً؟
    need_clean_markdown: bool = False, # نريد Markdown نظيف؟
    need_interaction: bool = False,    # نقر/ملء نماذج؟
    prefer_engine: Optional[Engine] = None,
) -> RouteDecision:
    """
    يقرر المحرك المناسب لمهمة ويب.

    Args:
        url: الرابط المستهدف
        caps: الموارد المتاحة
        task: نوع المهمة
        has_learned_rules: هل توجد قواعد autoscraper متعلَّمة لهذا الموقع
        need_clean_markdown: نريد إخراج Markdown نظيف (firecrawl)
        need_interaction: المهمة تحتاج تفاعل (browser_use)
        prefer_engine: إجبار محرك محدد
    """
    # ── تجاوز يدوي ──
    if prefer_engine is not None:
        return RouteDecision(
            engine=prefer_engine,
            reason=f"محرك محدد يدوياً: {prefer_engine.value}",
            task=task,
        )

    # ── ١. تفاعل صريح يفوز على كل شيء → browser_use ──
    # (نقر/ملء نماذج يتطلب متصفحاً حقيقياً حتى على منصة معروفة)
    if need_interaction or task == Task.INTERACT:
        if caps.has_browser and caps.has_llm:
            return RouteDecision(
                engine=Engine.BROWSER_USE,
                reason="مهمة تفاعلية (نقر/نماذج) — browser_use بالـ AI",
                task=Task.INTERACT,
            )
        raise RuntimeError(
            "المهمة التفاعلية تحتاج browser_use (Chromium + LLM). "
            "فعّل has_browser و has_llm."
        )

    # ── ٢. منصة معروفة (قراءة فقط) → agent_reach ──
    platform = _platform_of(url)
    if platform or task == Task.PLATFORM:
        if platform:
            return RouteDecision(
                engine=Engine.AGENT_REACH,
                reason=f"منصة معروفة ({platform}) — agent_reach متخصص بها",
                task=Task.PLATFORM,
                fallback=Engine.BROWSER_USE if caps.has_browser else None,
            )

    # ── ٣. استخلاص بقواعد متعلَّمة → autoscraper ──
    if task == Task.SCRAPE and has_learned_rules:
        return RouteDecision(
            engine=Engine.AUTOSCRAPER,
            reason="قواعد استخلاص متعلَّمة موجودة — autoscraper يطبّقها (offline)",
            task=Task.SCRAPE,
        )

    # ── ٤. scraping ذكي / Markdown نظيف / crawl → firecrawl ──
    if need_clean_markdown or task == Task.CRAWL:
        if caps.has_firecrawl_key:
            return RouteDecision(
                engine=Engine.FIRECRAWL,
                reason=(
                    "زحف متعدد الصفحات" if task == Task.CRAWL
                    else "Markdown نظيف مطلوب"
                ) + " — firecrawl",
                task=task,
                fallback=Engine.CURL_IMPERSONATE,
            )
        # لا API key — بديل
        if task == Task.CRAWL:
            raise RuntimeError(
                "الزحف يحتاج firecrawl API key. "
                "احصل عليه من firecrawl.dev أو استخدم autoscraper للاستخلاص."
            )

    # ── ٥. استخلاص عام بلا قواعد → firecrawl إن متاح، وإلا autoscraper ──
    if task == Task.SCRAPE:
        if caps.has_firecrawl_key:
            return RouteDecision(
                engine=Engine.FIRECRAWL,
                reason="استخلاص ذكي بلا قواعد — firecrawl",
                task=Task.SCRAPE,
            )
        return RouteDecision(
            engine=Engine.AUTOSCRAPER,
            reason="استخلاص بلا API — autoscraper (يحتاج أمثلة أولاً)",
            task=Task.SCRAPE,
        )

    # ── ٦. جلب HTML بسيط → curl_impersonate (افتراضي) ──
    if caps.has_curl_impersonate:
        return RouteDecision(
            engine=Engine.CURL_IMPERSONATE,
            reason="جلب HTML مع انتحال بصمة متصفح (يتجاوز مكافحة البوتات)",
            task=Task.FETCH,
            fallback=Engine.FIRECRAWL if caps.has_firecrawl_key else None,
        )

    # ── لا curl — بديل firecrawl ──
    if caps.has_firecrawl_key:
        return RouteDecision(
            engine=Engine.FIRECRAWL,
            reason="curl_impersonate غير مبني — firecrawl كبديل للجلب",
            task=Task.FETCH,
        )

    raise RuntimeError(
        "لا محرك متاح للجلب. ابنِ curl_impersonate أو وفّر firecrawl API key."
    )
