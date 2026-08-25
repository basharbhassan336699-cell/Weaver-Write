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


def format_apa_article(author, year, title, journal,
                       volume=None, issue=None, pages=None, doi=None):
    """Build an APA citation for a journal article."""
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
    return f"{author} ({year}). *{title}*. {publisher}."


def sort_references(refs: list[str]) -> list[str]:
    """Alphabetical order by first character."""
    return sorted(refs, key=lambda r: r.strip().lower())


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
