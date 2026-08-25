"""
citation_validator.py — validate citation formatting (shared working script)
============================================================================
A shared helper used across the system to verify that every citation
follows the correct form (Author, Year, p. X) / (المؤلف، سنة، ص. X).

Usage:
    python citation_validator.py --file draft.txt
    python citation_validator.py --text "..."

Note: regex patterns contain Arabic characters because they must match
Arabic citation text; the "[يحتاج مرجع]" marker is the Arabic
needs-reference marker produced by the writing layer.
"""
from __future__ import annotations
import re
import argparse

VALID_AR = re.compile(r"\([^()]*?،\s*ص\.\s*\d+\)")
VALID_AR_YEAR = re.compile(r"\([^()]*?،\s*\d{4}\s*،\s*ص\.\s*\d+\)")
VALID_EN = re.compile(r"\([^()]*?,\s*p\.\s*\d+\)")

# Incomplete citations (no page number) — warning
MISSING_PAGE = re.compile(r"\([^()]*?،\s*\d{4}\)(?!\s*،\s*ص)")

# Needs-reference markers (both languages)
NEEDS_REF_MARKERS = ["[يحتاج مرجع]", "[needs reference]"]


def validate_citations(text: str) -> dict:
    """Scan all citations and classify them."""
    valid = (VALID_AR.findall(text) + VALID_AR_YEAR.findall(text)
             + VALID_EN.findall(text))
    missing = MISSING_PAGE.findall(text)
    needs_ref = sum(text.count(m) for m in NEEDS_REF_MARKERS)

    return {
        "valid_count": len(set(valid)),
        "valid_citations": list(set(valid)),
        "missing_page_count": len(missing),
        "missing_page": missing,
        "needs_reference_markers": needs_ref,
        "ok": len(missing) == 0 and needs_ref == 0,
    }


def _main():
    p = argparse.ArgumentParser()
    p.add_argument("--file")
    p.add_argument("--text")
    args = p.parse_args()

    if args.file:
        with open(args.file, encoding="utf-8") as f:
            text = f.read()
    elif args.text:
        text = args.text
    else:
        print("--file or --text is required"); return

    result = validate_citations(text)
    print(f"Valid citations: {result['valid_count']}")
    if result['missing_page_count']:
        print(f"Missing page number: {result['missing_page_count']}")
        for m in result['missing_page']:
            print(f"    {m}")
    if result['needs_reference_markers']:
        print(f"Needs-reference markers: {result['needs_reference_markers']}")
    print(f"\nStatus: {'OK' if result['ok'] else 'needs review'}")


if __name__ == "__main__":
    _main()
