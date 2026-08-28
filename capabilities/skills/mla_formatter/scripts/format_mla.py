"""
format_mla.py — format references in MLA 9th style (working script)
===================================================================
Pure-logic formatter (no LLM needed). Handles articles, books, websites.

Usage:
    python format_mla.py --author "Smith, John" --title "E-Learning" \
        --container "Journal of Education" --year 2024 --pages "45-67"
"""
from __future__ import annotations
import argparse


def format_mla_article(author, title, container, year, volume=None,
                       issue=None, pages=None, doi=None):
    """MLA 9th for a journal article."""
    out = f'{author}. "{title}." *{container}*'
    if volume:
        out += f", vol. {volume}"
    if issue:
        out += f", no. {issue}"
    out += f", {year}"
    if pages:
        out += f", pp. {pages}"
    out += "."
    if doi:
        doi_clean = doi.replace("https://doi.org/", "").strip()
        out += f" https://doi.org/{doi_clean}."
    return out


def format_mla_book(author, title, publisher, year):
    """MLA 9th for a book."""
    return f"{author}. *{title}*. {publisher}, {year}."


def format_mla_website(author, title, site, year, url=None, access=None):
    """MLA 9th for a web source."""
    out = f'{author}. "{title}." *{site}*, {year}'
    out += "."
    if url:
        out += f" {url}."
    if access:
        out += f" Accessed {access}."
    return out


def sort_works_cited(refs):
    """Alphabetical order, ignoring leading articles."""
    def key(r):
        r = r.strip().lower()
        for art in ("a ", "an ", "the "):
            if r.startswith(art):
                return r[len(art):]
        return r
    return sorted(refs, key=key)


def build_bibliography(sources, lang="ar", extra=None):
    """Build a full, sorted, numbered MLA Works-Cited list from retrieved
    sources (list of dicts). `extra` is pre-formatted text appended as-is.
    Returns a string, or "" when empty."""
    entries = []
    for s in (sources or []):
        if not isinstance(s, dict):
            s = {"title": str(s)}
        title = (s.get("title") or s.get("key") or s.get("url") or "").strip()
        if not title:
            continue
        author = s.get("author") or ("" if lang == "ar" else "")
        site = s.get("site") or s.get("journal") or ""
        year = s.get("year") or "n.d."
        if author:
            entries.append(format_mla_website(author, title, site, year,
                                              s.get("url")))
        else:
            u = f" {s.get('url')}." if s.get("url") else ""
            sp = f" *{site}*," if site else ""
            entries.append(f'"{title}."{sp} {year}.{u}'.strip())
    seen, uniq = set(), []
    for e in entries:
        if e not in seen:
            seen.add(e)
            uniq.append(e)
    uniq = sort_works_cited(uniq)
    out = "\n".join(f"{i}. {e}" for i, e in enumerate(uniq, 1))
    if extra:
        extra = str(extra).strip()
        out = (out + "\n" + extra).strip() if out else extra
    return out


def format_mla(ref_data):
    """Dispatch by type. ref_data: dict with 'type' and fields."""
    t = ref_data.get("type", "article")
    if t == "book":
        return format_mla_book(ref_data["author"], ref_data["title"],
                               ref_data["publisher"], ref_data["year"])
    if t == "website":
        return format_mla_website(ref_data["author"], ref_data["title"],
                                  ref_data.get("site", ""), ref_data["year"],
                                  ref_data.get("url"), ref_data.get("access"))
    return format_mla_article(
        ref_data["author"], ref_data["title"], ref_data.get("container", ""),
        ref_data["year"], ref_data.get("volume"), ref_data.get("issue"),
        ref_data.get("pages"), ref_data.get("doi"))


def _main():
    p = argparse.ArgumentParser(description="MLA 9th formatting")
    p.add_argument("--author", required=True)
    p.add_argument("--title", required=True)
    p.add_argument("--container")
    p.add_argument("--publisher")
    p.add_argument("--year", required=True)
    p.add_argument("--volume")
    p.add_argument("--issue")
    p.add_argument("--pages")
    p.add_argument("--doi")
    args = p.parse_args()
    if args.publisher:
        print(format_mla_book(args.author, args.title, args.publisher, args.year))
    else:
        print(format_mla_article(args.author, args.title, args.container or "",
                                 args.year, args.volume, args.issue, args.pages, args.doi))


if __name__ == "__main__":
    _main()
