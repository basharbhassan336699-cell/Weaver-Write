"""
كشف الموارد المتاحة لـ UniWeb.
"""

from __future__ import annotations
import os
import shutil

from .router import Capabilities


def _has_curl_impersonate() -> bool:
    """فحص وجود curl-impersonate مبني."""
    if os.environ.get("UNIWEB_CURL_PATH"):
        return os.path.exists(os.environ["UNIWEB_CURL_PATH"])
    # curl-impersonate عادة باسم curl_chrome أو curl-impersonate
    for name in ("curl_chrome116", "curl-impersonate", "curl_chrome", "curl_ff"):
        if shutil.which(name):
            return True
    # أو مكتبة curl_cffi البديلة
    try:
        import curl_cffi  # type: ignore
        return True
    except Exception:
        return False


def _has_browser() -> bool:
    """فحص وجود متصفح + playwright."""
    try:
        import playwright  # type: ignore
        return True
    except Exception:
        pass
    # متصفح مثبت مباشرة
    return any(shutil.which(b) for b in ("chromium", "google-chrome", "chrome"))


def _detect_llm() -> tuple[bool, str | None]:
    """كشف مزود LLM متاح للـ browser_use."""
    if os.environ.get("ANTHROPIC_API_KEY"):
        return True, "anthropic"
    if os.environ.get("OPENAI_API_KEY"):
        return True, "openai"
    if os.environ.get("GOOGLE_API_KEY"):
        return True, "google"
    # نموذج محلي
    if os.environ.get("UNIWEB_LLM_BASE"):
        return True, "local"
    return False, None


def detect_capabilities() -> Capabilities:
    """
    كشف تلقائي للموارد المتاحة.

    متغيرات البيئة المؤثرة:
      UNIWEB_CURL_PATH=<path>     → مسار curl-impersonate
      FIRECRAWL_API_KEY=<key>     → مفتاح firecrawl
      ANTHROPIC_API_KEY / OPENAI_API_KEY → LLM للـ browser_use
      UNIWEB_LLM_BASE=<url>       → نموذج LLM محلي
    """
    fc_key = os.environ.get("FIRECRAWL_API_KEY")
    has_llm, llm_provider = _detect_llm()

    return Capabilities(
        has_curl_impersonate=_has_curl_impersonate(),
        has_firecrawl_key=bool(fc_key),
        firecrawl_key=fc_key,
        has_browser=_has_browser(),
        has_llm=has_llm,
        llm_provider=llm_provider,
    )
