# -*- coding: utf-8 -*-
"""
web_research.py — THE GENERAL RESEARCH & VERIFICATION LAYER
============================================================
Sections 2-5 of `general-web-research-methodology.md`, as pure functions with
no pipeline import: the web path and the academic path both call THESE, so an
improvement here reaches both instead of being copied into two places.

The academic specialization (Section 6 + the full academic methodology) is NOT
duplicated here — it is built ON TOP of these functions, in the orchestrator's
academic path, by calling them with stricter arguments (fetch every candidate
instead of the top three, require the citation fields, apply the quality
ladder). That is the layering the brief asks for.

Nothing here performs I/O. The caller supplies the fetcher, so the same rules
hold for any fetch backend and the functions stay testable offline.
"""
from __future__ import annotations
import re

# ── Section 2 · Golden Rule ────────────────────────────────────────────────
# "Never state a specific fact, figure, quote, name, date, or link as true
#  without having checked it." Mechanically: a field is USABLE only when the
#  primary page confirms it. Everything else is reported as unconfirmed — never
#  dropped silently, never presented as if it were confirmed.

UNVERIFIED = "unverified"
VERIFIED = "verified"
UNREACHABLE = "unreachable"


def _norm(s):
    """Case/diacritic/punctuation-insensitive form for comparing a metadata
    field against page text. Arabic tashkeel is dropped so «الإِعْجَازُ» and
    «الإعجاز» compare equal; punctuation becomes space."""
    s = "".join(c for c in str(s or "") if not ("ً" <= c <= "ْ"))
    s = "".join(c if (c.isalnum() or c.isspace()) else " " for c in s.lower())
    return " ".join(s.split())


def confirm_fields(page_text, candidate, fields=("title", "authors", "venue",
                                                 "year", "doi")):
    """Which of a candidate's metadata fields does the FETCHED PAGE confirm?

    This is the mechanism behind the rule that a scraper's metadata field is
    never trusted on its own: the value must actually occur in the page it
    claims to describe. Returns {field: True/False}. A field the candidate does
    not carry is absent from the result — unknown is not the same as refuted.
    """
    out = {}
    hay = _norm(page_text)
    if not hay:
        return out
    for f in fields:
        v = candidate.get(f) if isinstance(candidate, dict) else None
        if isinstance(v, (list, tuple)):
            vals = [str(x) for x in v if str(x).strip()]
            if not vals:
                continue
            # a single confirmed author is enough to tie the record to the page
            out[f] = any(_norm(x) and _norm(x) in hay for x in vals)
            continue
        v = str(v or "").strip()
        if not v:
            continue
        if f == "doi":
            out[f] = _norm(v.replace("https://doi.org/", "")) in hay
        elif f == "year":
            out[f] = bool(re.search(r"\b" + re.escape(v) + r"\b", page_text or ""))
        else:
            n = _norm(v)
            # long titles rarely appear character-identical (line breaks,
            # subtitle separators), so a strong prefix counts as confirmation
            out[f] = bool(n) and (n in hay or (len(n) > 40 and n[:40] in hay))
    return out


# ── Section 3 Step 2 · source priority, and the academic quality ladder ────
# The ladder is the ACADEMIC one (Section 4 of the academic methodology). It
# lives in the general layer because the general layer owns ordering; the
# academic path is what actually applies it as a gate.
TIER_PEER_DOI = 5       # ★★★★★ peer-reviewed + real DOI
TIER_BOOK = 4           # ★★★★  academic book, known publisher
TIER_OFFICIAL = 3       # ★★★   official university / government page
TIER_REPORT = 2         # ★★    institutional report
TIER_GENERAL = 1        # ★     general site — supplementary only
TIER_EXCLUDED = 0       # ✗     wikipedia / blogs / unidentifiable

_EXCLUDED_HOSTS = ("wikipedia.org", "wikiwand.com", "blogspot.", "wordpress.com",
                   "medium.com", "quora.com", "answers.", "facebook.com",
                   "twitter.com", "x.com", "reddit.com", "pinterest.")
_OFFICIAL_HINTS = (".edu", ".ac.", ".gov", ".mil", ".int")


def quality_tier(src):
    """Rate ONE source on the ladder. Deterministic, from what the record
    already carries — provenance, identifiers, host. No model call, so the
    ordering is the same with any provider."""
    if not isinstance(src, dict):
        return TIER_EXCLUDED
    url = str(src.get("url") or "").lower()
    host = url.split("//")[-1].split("/")[0]
    if any(h in host for h in _EXCLUDED_HOSTS):
        return TIER_EXCLUDED
    doi = str(src.get("doi") or "").strip()
    venue = str(src.get("venue") or src.get("journal") or "").strip()
    if doi and (venue or src.get("academic")):
        return TIER_PEER_DOI
    if doi:
        return TIER_PEER_DOI
    if src.get("publisher") and src.get("authors"):
        return TIER_BOOK
    if any(h in host for h in _OFFICIAL_HINTS):
        return TIER_OFFICIAL
    if venue or src.get("academic"):
        return TIER_REPORT
    return TIER_GENERAL


def order_by_quality(sources):
    """Stable sort, best tier first. Ties keep their gathered order."""
    idx = {id(s): i for i, s in enumerate(sources or [])}
    return sorted(list(sources or []),
                  key=lambda s: (-quality_tier(s), idx.get(id(s), 0)))


# ── Section 5 · date/time filtering — BEFORE verification, never after ─────
def parse_window(text):
    """Read a year or a year range out of the REQUEST's own words. Returns
    (start, end) or (None, None). Digits only — no vocabulary list, so it reads
    «من 2020 إلى 2024», «2020-2024», «since 2018», «بعد 2015» alike."""
    t = str(text or "")
    t = t.translate(str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789"))
    rng = re.search(r"\b(19|20)(\d{2})\s*(?:-|–|—|\.\.|to|إلى|الى)\s*(19|20)(\d{2})\b", t)
    if rng:
        a = int(rng.group(1) + rng.group(2))
        b = int(rng.group(3) + rng.group(4))
        return (min(a, b), max(a, b))
    one = re.search(r"\b(?:since|after|بعد|منذ|من)\s*((?:19|20)\d{2})\b", t)
    if one:
        return (int(one.group(1)), None)
    return (None, None)


def within_window(src, start, end):
    """Is this candidate inside the requested window? A record with NO year is
    kept — its date is unknown, not wrong, and the fetch step is what settles
    it. Excluding it here would silently shrink the pool on missing data."""
    if not start and not end:
        return True
    try:
        y = int(str((src or {}).get("year") or "")[:4])
    except (TypeError, ValueError):
        return True
    if start and y < start:
        return False
    if end and y > end:
        return False
    return True


# ── Section 3 Step 1 · query discipline, and reformulating a failed query ──
def scale_calls(parts, thorough=False):
    """Section 4 of the search methodology as a number: 1 call for a single
    fact, 3-8 for a medium task, 8-20 for a deep one. `parts` is how many
    distinct things the request actually asks about."""
    n = max(1, int(parts or 1))
    if thorough or n >= 4:
        return min(20, max(8, n * 2))
    if n == 1:
        return 1
    return min(8, max(3, n * 2))


def reformulate(query, tried, angle=0):
    """A follow-up query must be MEANINGFULLY different, not the same phrasing
    resent. Each angle changes the shape of the query, not its wording only:
    0 = drop the wrapper words and keep the nouns; 1 = the most specific pair
    of terms alone; 2 = quote the core phrase; 3 = add a site-type narrowing.
    Returns "" when nothing genuinely different is left to try."""
    base = " ".join(str(query or "").split())
    if not base:
        return ""
    seen = {" ".join(str(t).split()).lower() for t in (tried or [])}
    words = [w for w in base.split() if len(w) > 2]
    cands = []
    if len(words) > 2:
        cands.append(" ".join(words[:max(2, len(words) // 2)]))
        cands.append(" ".join(sorted(words, key=len, reverse=True)[:2]))
    cands.append('"' + " ".join(words[:4]) + '"')
    cands.append(base + " filetype:pdf")
    for c in cands:
        c = " ".join(c.split())
        if c and c.lower() not in seen and c.lower() != base.lower():
            return c
    return ""


# ── Section 7 (fetch methodology) · safety, applied to query AND to target ──
_HARM = ("child sexual", "csam", "how to make a bomb", "build a bomb",
         "kill myself", "how to kill", "mass shooting plan", "bomb making",
         "كيف أصنع قنبلة", "صنع متفجرات", "كيف أنتحر", "استغلال الأطفال")
_EXTREMIST_HOSTS = ("stormfront", "8kun", "kiwifarms")


def query_is_blocked(query):
    """A query whose clear purpose is to find harmful material is not run. The
    caller explains the limitation instead of attempting a softer version."""
    q = _norm(query)
    return any(_norm(k) in q for k in _HARM)


def source_is_blocked(url):
    """A page promoting hate, extremism or harm is not fetched and is never a
    legitimate reference — regardless of how the URL arrived."""
    host = str(url or "").lower().split("//")[-1].split("/")[0]
    return any(h in host for h in _EXTREMIST_HOSTS)


# ── Section 8 (fetch methodology) · copyright limits on fetched content ────
MAX_QUOTE_WORDS = 15


def quote_guard(text, source_key, used):
    """At most ONE direct quotation per source, under ~15 words. Returns the
    text to use. Anything longer, or a second quote from the same source, comes
    back trimmed with a marker so the caller paraphrases instead. `used` is a
    set the caller keeps across sources."""
    t = " ".join(str(text or "").split())
    if not t:
        return ""
    key = str(source_key or "")
    if key in (used or set()):
        return ""                       # a second quote from this source
    words = t.split()
    if len(words) > MAX_QUOTE_WORDS:
        t = " ".join(words[:MAX_QUOTE_WORDS]) + "…"
    if used is not None:
        used.add(key)
    return t
