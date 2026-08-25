"""
source_reliability.py — academic source reliability gate (working script)
=========================================================================
Decides whether a source is acceptable for academic citation, following the
project's policy:

  Unreliable-by-default sources (general encyclopedias, personal blogs,
  content mills, Q&A sites, forums, social media, news for scientific claims,
  commercial/promotional sites) MUST NOT be used in any task UNLESS the task
  explicitly asks to use one of them — then it is allowed, for that task only.

  If the task doesn't explicitly permit them, they are rejected and a reliable
  alternative is recommended (peer-reviewed journals, academic books, official
  government sites, international-body reports).

This is a deterministic gate (domain/pattern based). It complements the
LLM-based credibility_scorer (which judges quality of an otherwise-acceptable
source). It never fabricates: it only classifies by known patterns.
"""
from __future__ import annotations
import re
from urllib.parse import urlparse


# ── unreliable-by-default domains / patterns ─────────────────
_UNRELIABLE = {
    "general_encyclopedia": [
        "wikipedia.org", "wikia.com", "fandom.com", "britannica.com",
    ],
    "personal_blog": [
        "blogger.com", "blogspot.com", "wordpress.com", "medium.com",
        "substack.com", "tumblr.com",
    ],
    "content_mill": [
        "mawdoo3.com", "mawdo3.com", "m3loma.com", "almrsal.com",
        "mo3lম.com", "sotor.com", "e3arabi.com",  # common Arabic content sites
    ],
    "qa_forum": [
        "reddit.com", "quora.com", "answers.yahoo.com", "chegg.com",
        "coursehero.com", "brainly.com", "brainly.",
    ],
    "social_media": [
        "twitter.com", "x.com", "facebook.com", "instagram.com",
        "tiktok.com", "linkedin.com", "youtube.com", "t.me",
    ],
}

# news domains: acceptable for events, NOT for scientific claims
_NEWS_HINTS = ["aljazeera", "bbc", "cnn", "reuters", "nytimes", "alarabiya",
               "skynews", "news", "press"]

# reliable categories (for the recommendation message)
_RELIABLE_ALTERNATIVES = {
    "ar": ("المجلات المحكّمة (Scopus / Web of Science)، الكتب الأكاديمية "
           "المنشورة، المواقع الحكومية الرسمية، وتقارير الهيئات الدولية "
           "(الأمم المتحدة، منظمة الصحة العالمية، صندوق النقد الدولي)"),
    "en": ("peer-reviewed journals (Scopus / Web of Science), published "
           "academic books, official government sites, and international-body "
           "reports (UN, WHO, IMF)"),
}


def _domain(url_or_name: str) -> str:
    s = url_or_name.strip().lower()
    if "://" not in s:
        s = "http://" + s
    try:
        net = urlparse(s).netloc
        return net[4:] if net.startswith("www.") else net
    except Exception:
        return url_or_name.lower()


def classify_source(url_or_name: str):
    """
    Return (category, reliable_by_default) for a source.
    category is one of the _UNRELIABLE keys, 'news', or 'acceptable'.
    """
    dom = _domain(url_or_name)
    for category, domains in _UNRELIABLE.items():
        if any(d in dom for d in domains):
            return category, False
    if any(h in dom for h in _NEWS_HINTS):
        return "news", False  # ok for events only, not scientific claims
    return "acceptable", True


def check_source(url_or_name: str, task_card: dict = None, lang="ar") -> dict:
    """
    Decide if a source may be used, applying the explicit-permission rule.

    task_card may contain:
      - allow_unreliable: True  -> user explicitly permitted these sources
      - allowed_sources: [..]   -> specific permitted domains/names
      - about_company: "name"   -> a company site is OK if the task is about it

    Returns {"allowed", "category", "reason", "alternative"}.
    """
    task_card = task_card or {}
    category, reliable = classify_source(url_or_name)
    alt = _RELIABLE_ALTERNATIVES["ar" if lang == "ar" else "en"]

    if reliable:
        return {"allowed": True, "category": category,
                "reason": "acceptable academic source", "alternative": None}

    # explicit permission for this task?
    if task_card.get("allow_unreliable"):
        return {"allowed": True, "category": category,
                "reason": "explicitly permitted for this task",
                "alternative": None}

    allowed_list = [a.lower() for a in task_card.get("allowed_sources", [])]
    if any(a in _domain(url_or_name) for a in allowed_list):
        return {"allowed": True, "category": category,
                "reason": "in task's allowed-sources list", "alternative": None}

    # commercial/company site is OK only if the task is about that company
    about = (task_card.get("about_company") or "").lower()
    if about and about in _domain(url_or_name):
        return {"allowed": True, "category": "company_own",
                "reason": "company site, and the task is about this company",
                "alternative": None}

    # otherwise: rejected, with an alternative
    msg_ar = {
        "general_encyclopedia": "الموسوعات العامة ليست مرجعاً أكاديمياً",
        "personal_blog": "المدونات الشخصية غير موثوقة أكاديمياً",
        "content_mill": "مواقع المحتوى المنوّع غير موثوقة أكاديمياً",
        "qa_forum": "مواقع الأسئلة والمنتديات غير موثوقة",
        "social_media": "وسائل التواصل الاجتماعي ليست مرجعاً علمياً",
        "news": "المصادر الإخبارية تُقبل للأحداث لا للتوثيق العلمي",
    }
    msg_en = {
        "general_encyclopedia": "general encyclopedias are not academic sources",
        "personal_blog": "personal blogs are not academically reliable",
        "content_mill": "content-mill sites are not academically reliable",
        "qa_forum": "Q&A sites and forums are not reliable",
        "social_media": "social media is not a scientific source",
        "news": "news is acceptable for events, not for scientific claims",
    }
    reason = (msg_ar if lang == "ar" else msg_en).get(category, "unreliable source")
    return {"allowed": False, "category": category, "reason": reason,
            "alternative": alt}


def filter_sources(sources: list, task_card: dict = None, lang="ar") -> dict:
    """Split a list of sources into accepted/rejected with reasons."""
    accepted, rejected = [], []
    for s in sources:
        r = check_source(s, task_card, lang)
        (accepted if r["allowed"] else rejected).append({"source": s, **r})
    return {"accepted": accepted, "rejected": rejected}


if __name__ == "__main__":
    tc = {}
    tests = ["https://en.wikipedia.org/wiki/AI", "mawdoo3.com/article",
             "https://www.nature.com/articles/x", "reddit.com/r/science",
             "https://www.who.int/report", "twitter.com/user/status/1"]
    for t in tests:
        r = check_source(t, tc, "ar")
        mark = "✅" if r["allowed"] else "❌"
        print(f"{mark} {t}")
        print(f"    {r['category']}: {r['reason']}")

    # with explicit permission
    print("\nمع إذن صريح (allow_unreliable=True):")
    r = check_source("wikipedia.org", {"allow_unreliable": True}, "ar")
    print(f"  wikipedia: {'✅ مسموح' if r['allowed'] else '❌'} — {r['reason']}")
