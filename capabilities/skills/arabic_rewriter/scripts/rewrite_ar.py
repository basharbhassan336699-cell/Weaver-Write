"""
rewrite_ar.py — protect citations during rewriting (working script)
===================================================================
Problem: when an LLM rewrites text, citations can get corrupted.
Solution: replace each citation with a placeholder token before rewriting,
          then restore it afterward — the same principle as the WeaverCode
          humanization system.

Usage (as a module):
    from rewrite_ar import protect_citations, restore_citations
    protected, mapping = protect_citations(text)
    # ... send `protected` to the LLM for rewriting ...
    final = restore_citations(rewritten, mapping)

Note: the regex patterns intentionally contain Arabic characters
(ص. = "p.") because they must match Arabic citation text.
"""
from __future__ import annotations
import re
import argparse

# Arabic citation patterns:
#  - (Author, p. N) / (Author, Year, p. N)  — page-based
#  - (Author, Year)                          — author-year (APA in-text),
#    supporting Arabic comma "،" and a 4-digit year (optionally with هـ/م)
CITATION_PATTERN = re.compile(r"\([^()]*?ص\.\s*\d+\)")
CITATION_PATTERN_AR_YEAR = re.compile(
    r"\([^()]*?[،,]\s*\d{4}\s*(?:هـ|م)?\)")

# English citation pattern inside Arabic text: (Author, p. N) and (Author, Year)
CITATION_PATTERN_EN = re.compile(r"\([^()]*?p\.\s*\d+\)")
CITATION_PATTERN_EN_YEAR = re.compile(r"\([A-Za-z][^()]*?,\s*\d{4}[a-z]?\)")

PLACEHOLDER = "\u2063CITE{}\u2063"  # invisible char to avoid overlap


def protect_citations(text: str) -> tuple[str, dict]:
    """
    Replace each citation with a unique placeholder.

    Returns:
        (protected text, restore mapping)
    """
    mapping = {}
    counter = [0]

    def _replace(match):
        token = PLACEHOLDER.format(counter[0])
        mapping[token] = match.group(0)
        counter[0] += 1
        return token

    protected = CITATION_PATTERN.sub(_replace, text)
    protected = CITATION_PATTERN_AR_YEAR.sub(_replace, protected)
    protected = CITATION_PATTERN_EN.sub(_replace, protected)
    protected = CITATION_PATTERN_EN_YEAR.sub(_replace, protected)
    return protected, mapping


def restore_citations(text: str, mapping: dict) -> str:
    """Restore citations from the mapping."""
    for token, citation in mapping.items():
        text = text.replace(token, citation)
    return text


def count_citations(text: str) -> int:
    """Count citations in the text."""
    return (len(CITATION_PATTERN.findall(text))
            + len(CITATION_PATTERN_AR_YEAR.findall(text))
            + len(CITATION_PATTERN_EN.findall(text))
            + len(CITATION_PATTERN_EN_YEAR.findall(text)))


def verify_integrity(original: str, rewritten: str) -> dict:
    """Verify the citation count did not change after rewriting."""
    before = count_citations(original)
    after = count_citations(rewritten)
    return {
        "citations_before": before,
        "citations_after": after,
        "intact": before == after,
    }


def humanize_text(text: str, seed: int = 42, general_rate: float = 0.25, file_type: str = "docx") -> dict:
    """
    Full Arabic humanization pass:
      1) protect citations (placeholder tokens),
      2) replace AI-signature words/phrases via the shared dictionary engine,
      3) restore citations,
      4) verify citation integrity.
    Returns {"text", "intact", "citations_before", "citations_after"}.
    """
    protected, mapping = protect_citations(text)
    try:
        import os, sys
        eng = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
            os.path.dirname(os.path.abspath(__file__)))))), "engines", "humanizer-core")
        if eng not in sys.path:
            sys.path.insert(0, eng)
        from humanizer import humanize
        rewritten = humanize(protected, lang="ar", seed=seed,
                             general_rate=general_rate, file_type=file_type)
    except Exception:
        rewritten = protected  # if engine missing, leave protected text as-is
    final = restore_citations(rewritten, mapping)
    integrity = verify_integrity(text, final)
    return {"text": final, **integrity}


def _main():
    p = argparse.ArgumentParser(description="Arabic humanization")
    p.add_argument("--text", required=True, help="text to humanize")
    p.add_argument("--action", default="humanize",
                   choices=["humanize", "protect", "count"])
    p.add_argument("--general", type=float, default=0.25,
                   help="general-synonym rate (0 = AI words only)")
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
        for token, cite in mapping.items():
            print(f"  {repr(token)} -> {cite}")


if __name__ == "__main__":
    _main()
