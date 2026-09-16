"""
format_apa.py — format a reference in APA 7th style (working script)
====================================================================
Usage:
    python format_apa.py --author "Smith, J." --year 2024 \
        --title "E-learning" --journal "Journal of Education" \
        --volume 12 --issue 3 --pages "45-67" --doi "10.1234/abc"
"""
from __future__ import annotations
import argparse
import re


def _year(y):
    """APA's own marker for an undated work. A missing year arrived as the
    Python object None and was printed literally — «Mobile Phone Effects
    (None).» — which reads as a data leak, not a citation."""
    t = str(y if y is not None else "").strip()
    return t if t and t.lower() not in ("none", "null", "n/a", "") else "n.d."


def format_apa_article(author, year, title, journal,
                       volume=None, issue=None, pages=None, doi=None):
    """Build an APA citation for a journal article."""
    year = _year(year)
    parts = [f"{author} ({year}). {title}. "]
    journal_part = f"*{journal}*"
    if volume:
        journal_part += f", *{volume}*"
        if issue:
            journal_part += f"({issue})"
    if pages:
        journal_part += f", {pages}"
    parts.append(journal_part + ".")
    if doi:
        doi_clean = doi.replace("https://doi.org/", "").strip()
        parts.append(f" https://doi.org/{doi_clean}")
    return "".join(parts)


def format_apa_book(author, year, title, publisher):
    """Build an APA citation for a book."""
    return f"{author} ({_year(year)}). *{title}*. {publisher}."


def _readable_url(url):
    """A URL a human can read. Search results arrive percent-encoded, so an
    Arabic page came out as «%D8%AF%D9%88…» across half a line — unreadable, and
    a plain sign that the link was pasted from a result page untouched. Decoding
    is lossless and reversible; the link still resolves."""
    u = str(url or "").strip()
    if "%" not in u:
        return u
    try:
        from urllib.parse import unquote
        d = unquote(u)
        # keep the decoded form only if it really is readable text
        return d if d.count("%") < u.count("%") else u
    except Exception:
        return u


def _site_from_url(url):
    """The publishing site's host, for an entry that has no journal or
    publisher. An APA web entry without a site is a title and a link — which is
    what a cropped search result looks like. The host is always knowable."""
    try:
        h = str(url or "").split("//")[-1].split("/")[0].strip().lower()
        if h.startswith("www."):
            h = h[4:]
        return h if "." in h and len(h) > 3 else ""
    except Exception:
        return ""


# A DOI RESOLVER IS NOT A WEBSITE. An entry whose only link was
# https://doi.org/10.53796/hnsj4411 rendered as «… (2023). *doi.org*.» —
# naming the resolver as if it were the publisher. doi.org, dx.doi.org and
# handle.net route to a work; they never publish one, so their host is never
# printed as a source's name.
_RESOLVER_HOSTS = ("doi.org", "dx.doi.org", "hdl.handle.net", "handle.net")


def _ident(src):
    """The IDENTITY of a source, for de-duplication: its DOI, else its URL
    reduced to what actually identifies the page, else its normalized title.

    The list carried the SAME Shamela book twice — once as
    `shamela.ws/book/31080` and once as `shamela.ws/index.php/book/31080` —
    because de-duplication compared the RENDERED STRINGS, and two strings that
    differ by `index.php/` are simply not equal. A reference's identity is not
    how it happens to be typeset."""
    if not isinstance(src, dict):
        return str(src).strip().lower()
    doi = str(src.get("doi") or "").strip().lower()
    if doi:
        return "doi:" + doi.replace("https://doi.org/", "").replace(
            "http://doi.org/", "").strip("/")
    url = str(src.get("url") or "").strip().lower()
    if url:
        u = re.sub(r"^https?://", "", url)
        u = re.sub(r"^www\.", "", u)
        u = u.split("#")[0].split("?")[0]
        u = u.replace("/index.php/", "/").replace("/index.html", "/")
        u = re.sub(r"/+$", "", u)
        if u.startswith(_RESOLVER_HOSTS[0]) or any(
                u.startswith(h) for h in _RESOLVER_HOSTS):
            return "doi:" + u.split("/", 1)[-1]
        return "url:" + u
    t = " ".join(str(src.get("title") or "").split()).strip().lower()
    return ("title:" + t) if t else ""


def dedupe_sources(sources):
    """Collapse sources that are the SAME work, keeping the richest record.
    Order is preserved. Never raises."""
    try:
        out, seen = [], {}
        for s_ in (sources or []):
            k = _ident(s_)
            if not k:
                out.append(s_)
                continue
            if k not in seen:
                seen[k] = len(out)
                out.append(s_)
                continue
            # keep whichever record carries more usable bibliographic data
            old_ = out[seen[k]]
            def _score(d):
                if not isinstance(d, dict):
                    return -1
                return sum(1 for f in ("doi", "authors", "author", "venue",
                                       "journal", "year", "publisher")
                           if d.get(f))
            if _score(s_) > _score(old_):
                out[seen[k]] = s_
        return out
    except Exception:
        return list(sources or [])


def format_apa_website(title, url="", year=None, site=None, author=None):
    """APA 7th for a web page / online source.

    `author` is optional and NEW: this used to take no author at all, so a
    source with a known author but no journal/publisher silently lost it and
    was rendered as a bare "Title (year). URL" — which is why lists came out
    unformatted even after the author was successfully retrieved.
    APA 7th: Author, A. A. (Year). Title. Site. URL
    """
    a = (str(author).strip() if author else "")
    y = f" ({_year(year)})."
    # NEVER a bare «Title. URL». Without a site name and a date an entry is a
    # cropped search result, not a reference. The host is derivable from the
    # link itself, and n.d. is APA's own marker for an undated source — both
    # are honest, and both are better than silence.
    site = site or _site_from_url(url)
    if str(site or "").strip().lower() in _RESOLVER_HOSTS:
        site = ""            # a resolver routes to the work; it never issues it
    s = f" *{site}*." if site else ""
    u = f" {_readable_url(url)}" if url else ""
    if a:
        return f"{a}{y} {title}.{s}{u}".strip()
    return f"{title}{y}{s}{u}".strip()


def sort_references(refs: list[str]) -> list[str]:
    """Alphabetical order by first character."""
    return sorted(refs, key=lambda r: r.strip().lower())


def build_bibliography(sources, lang="ar", extra=None):
    """Build a full, sorted, numbered APA reference list from retrieved sources.

    `sources` is a list of dicts (title/url/author/year/journal/publisher/…) as
    gathered by the pipeline's web/academic search. `extra` is any pre-formatted
    references text (e.g. from PaperQA) appended as-is. Returns a string, or ""
    when there is nothing to list.
    """
    entries = []
    sources = dedupe_sources(sources)
    for s in (sources or []):
        if not isinstance(s, dict):
            s = {"title": str(s)}
        # The pipeline stores `authors` as a LIST (and the venue under
        # `venue`/`journal`), while this builder only ever read a singular
        # `author`. The mismatch meant NO source ever had an author, so every
        # entry fell through to the bare website form ("Title (year). URL")
        # instead of a real APA reference.
        author = s.get("author")
        if not author:
            _a = s.get("authors")
            if isinstance(_a, (list, tuple)):
                _a = [str(x).strip() for x in _a if str(x).strip()]
                if _a:
                    author = ", ".join(_a[:3]) + (" et al." if len(_a) > 3 else "")
            elif isinstance(_a, str) and _a.strip():
                author = _a.strip()
        if not s.get("journal") and s.get("venue"):
            s = dict(s, journal=s.get("venue"))
        year = s.get("year")
        title = (s.get("title") or s.get("key") or s.get("url") or "").strip()
        if not title:
            continue
        if author and s.get("journal"):
            entries.append(format_apa_article(
                author, year or "n.d.", title, s["journal"],
                s.get("volume"), s.get("issue"), s.get("pages"), s.get("doi")))
        elif author and s.get("publisher"):
            entries.append(format_apa_book(author, year or "n.d.", title,
                                           s["publisher"]))
        else:
            entries.append(format_apa_website(title, s.get("url", ""), year,
                                              s.get("site"), author))
    # the rendered strings are de-duplicated too, as a last net: two DIFFERENT
    # records that typeset identically are one reference on the page
    seen, uniq = set(), []
    for e in entries:
        if e not in seen:
            seen.add(e)
            uniq.append(e)
    uniq = sort_references(uniq)
    out = "\n".join(f"{i}. {e}" for i, e in enumerate(uniq, 1))
    if extra:
        extra = str(extra).strip()
        out = (out + "\n" + extra).strip() if out else extra
    return out


def _main():
    p = argparse.ArgumentParser(description="APA 7th formatting")
    p.add_argument("--author", required=True)
    p.add_argument("--year", required=True)
    p.add_argument("--title", required=True)
    p.add_argument("--journal")
    p.add_argument("--publisher")
    p.add_argument("--volume")
    p.add_argument("--issue")
    p.add_argument("--pages")
    p.add_argument("--doi")
    args = p.parse_args()

    if args.journal:
        result = format_apa_article(
            args.author, args.year, args.title, args.journal,
            args.volume, args.issue, args.pages, args.doi,
        )
    elif args.publisher:
        result = format_apa_book(args.author, args.year, args.title, args.publisher)
    else:
        result = f"{args.author} ({args.year}). {args.title}."

    print(result)


if __name__ == "__main__":
    _main()
