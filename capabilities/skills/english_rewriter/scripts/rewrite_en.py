"""
rewrite_en.py — protect citations during English rewriting (working script)
===========================================================================
Same principle as rewrite_ar.py: replace each citation with a placeholder
token before rewriting, then restore it afterward.

Usage (as a module):
    from rewrite_en import protect_citations, restore_citations
    protected, mapping = protect_citations(text)
    final = restore_citations(rewritten, mapping)
"""
from __future__ import annotations
import re
import argparse

# English citation pattern: (Author, p. N) or (Author, Year, p. N)
CITATION_PATTERN = re.compile(r"\([^()]*?p\.\s*\d+\)")
CITATION_PATTERN_YEAR = re.compile(r"\([A-Za-z][^()]*?,\s*\d{4}[a-z]?\)")

PLACEHOLDER = "\u2063CITE{}\u2063"


def protect_citations(text: str) -> tuple[str, dict]:
    """Replace each citation with a unique placeholder."""
    mapping = {}
    counter = [0]

    def _replace(match):
        token = PLACEHOLDER.format(counter[0])
        mapping[token] = match.group(0)
        counter[0] += 1
        return token

    protected = CITATION_PATTERN.sub(_replace, text)
    protected = CITATION_PATTERN_YEAR.sub(_replace, protected)
    return protected, mapping


def restore_citations(text: str, mapping: dict) -> str:
    """Restore citations from the mapping."""
    for token, citation in mapping.items():
        text = text.replace(token, citation)
    return text


def count_citations(text: str) -> int:
    """Count citations in the text."""
    return len(CITATION_PATTERN.findall(text)) + len(CITATION_PATTERN_YEAR.findall(text))


def humanize_text(text: str, seed: int = 42, general_rate: float = 0.25, file_type: str = "docx") -> dict:
    """
    Full English humanization: protect citations -> replace AI-signature
    words/phrases via the shared dictionary engine -> restore citations ->
    verify citation count is unchanged.
    """
    before = count_citations(text)
    protected, mapping = protect_citations(text)
    try:
        import os, sys
        eng = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
            os.path.dirname(os.path.abspath(__file__)))))), "engines", "humanizer-core")
        if eng not in sys.path:
            sys.path.insert(0, eng)
        from humanizer import humanize
        rewritten = humanize(protected, lang="en", seed=seed,
                             general_rate=general_rate, file_type=file_type)
    except Exception:
        rewritten = protected
    final = restore_citations(rewritten, mapping)
    after = count_citations(final)
    return {"text": final, "citations_before": before,
            "citations_after": after, "intact": before == after}


def _main():
    p = argparse.ArgumentParser(description="English humanization")
    p.add_argument("--text", required=True)
    p.add_argument("--action", default="humanize",
                   choices=["humanize", "protect", "count"])
    p.add_argument("--general", type=float, default=0.25)
    args = p.parse_args()

    if args.action == "count":
        print(f"Citation count: {count_citations(args.text)}")
    elif args.action == "humanize":
        r = humanize_text(args.text, general_rate=args.general)
        print(r["text"])
        print(f"\n[citations intact: {r['intact']} "
              f"({r['citations_before']}->{r['citations_after']})]")
    else:
        protected, mapping = protect_citations(args.text)
        print("=== Protected text ===")
        print(protected)
        print(f"\n=== {len(mapping)} citations protected ===")


if __name__ == "__main__":
    _main()
