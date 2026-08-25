"""
core/browser/__init__.py
========================
UniWeb مدمجة كمتصفح داخلي للنظام.

يُستخدم لـ:
  - جلب الأوراق البحثية من arXiv / ResearchGate
  - جلب صفحات ويب للبحث
  - الوصول لمنصات أكاديمية
  - تجاوز مكافحة البوتات (curl-impersonate)
"""

from __future__ import annotations
import sys
import os

UNIWEB_PATH = os.path.join(os.path.dirname(__file__), "../../engines/uniweb-core")
if UNIWEB_PATH not in sys.path:
    sys.path.insert(0, UNIWEB_PATH)

from uniweb import fetch, scrape, crawl, fetch_detailed
from uniweb.router import Engine, Task, Capabilities
from uniweb.capabilities import detect_capabilities


class WeaverBrowser:
    """
    متصفح Weaver Write الداخلي.
    
    يختار المحرك المناسب تلقائياً:
      منصة أكاديمية → agent_reach
      PDF من URL    → curl_impersonate
      استخلاص بيانات → autoscraper / firecrawl
      مهمة تفاعلية → browser_use
    """

    def __init__(self, firecrawl_key: str = None):
        self.caps = detect_capabilities()
        if firecrawl_key:
            self.caps.firecrawl_key = firecrawl_key
            self.caps.has_firecrawl_key = True

    async def fetch_paper(self, url: str) -> dict:
        """
        يجلب ورقة بحثية من الإنترنت.
        يعمل مع: arXiv, ResearchGate, DOI, PubMed
        """
        return fetch_detailed(url, caps=self.caps)

    async def fetch_page(self, url: str, clean_markdown: bool = True) -> str:
        """
        يجلب صفحة ويب كـ Markdown نظيف.
        للبحث وجمع معلومات أكاديمية.
        """
        result = fetch_detailed(
            url, need_clean_markdown=clean_markdown, caps=self.caps
        )
        return result["content"]

    async def scrape_data(
        self,
        url: str,
        wanted: list = None,
        rules_file: str = None,
    ) -> list:
        """
        يستخلص بيانات محددة من صفحة.
        مفيد لجمع بيانات من فهارس أكاديمية.
        """
        result = fetch_detailed(
            url,
            task=Task.SCRAPE,
            has_learned_rules=bool(rules_file),
            caps=self.caps,
            wanted_list=wanted,
            rules_file=rules_file,
        )
        return result["content"]

    async def crawl_site(self, url: str) -> list:
        """
        يزحف عبر موقع متعدد الصفحات.
        للمواقع الأكاديمية التي تحتوي عدة أوراق.
        """
        result = fetch_detailed(
            url, task=Task.CRAWL, need_clean_markdown=True, caps=self.caps
        )
        return result["content"]

    def engine_for(self, url: str) -> str:
        """يخبرك أي محرك سيُستخدم لرابط معين."""
        from uniweb.router import route
        decision = route(url, self.caps)
        return decision.engine.value
