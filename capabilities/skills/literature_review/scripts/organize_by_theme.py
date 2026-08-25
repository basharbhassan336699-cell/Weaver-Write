"""
organize_by_theme.py — group references by theme (working script)
=================================================================
Organizes references by shared themes rather than listing them one by one
(the core principle of a good literature review).

Two modes:
  - keyword mode (default, no LLM): groups references by matching theme
    keywords the caller supplies, or by shared significant terms.
  - The output feeds the literature_review writing step, which then prose-
    writes each theme with an LLM.

Usage (as a module):
    from organize_by_theme import organize_by_theme
    groups = organize_by_theme(references, themes={
        "adoption": ["adoption", "تبني", "استخدام"],
        "outcomes": ["outcome", "مخرجات", "نتائج"],
    })
"""
from __future__ import annotations
import argparse
import json
import re
from collections import defaultdict


def organize_by_theme(references, themes=None):
    """
    Group references by theme.

    references: list of dicts, each {"key": str, "text": str, "page": int?}
                or plain strings.
    themes: optional dict {theme_name: [keywords...]}. If None, auto-groups
            by shared significant terms.
    Returns: {theme_name: [references...]}, plus an "unclassified" bucket.
    """
    norm = []
    for r in references:
        if isinstance(r, str):
            norm.append({"key": r[:40], "text": r})
        else:
            norm.append(r)

    if themes:
        groups = defaultdict(list)
        for ref in norm:
            text = ref.get("text", "").lower()
            matched = False
            for theme, kws in themes.items():
                if any(k.lower() in text for k in kws):
                    groups[theme].append(ref)
                    matched = True
            if not matched:
                groups["unclassified"].append(ref)
        return dict(groups)

    # auto mode: group by most common significant shared term
    stop = set("the a an of in on for and or to is are با في من على the عن مع هذا التي".split())
    term_map = defaultdict(list)
    for ref in norm:
        words = re.findall(r"\w{4,}", ref.get("text", "").lower())
        sig = [w for w in words if w not in stop]
        if sig:
            # use the most frequent significant word as the theme anchor
            anchor = max(set(sig), key=sig.count)
            term_map[anchor].append(ref)
    return dict(term_map)


def _main():
    p = argparse.ArgumentParser(description="Group references by theme")
    p.add_argument("--json", required=True, help="JSON: {references:[...], themes:{...}}")
    args = p.parse_args()
    with open(args.json, encoding="utf-8") as f:
        d = json.load(f)
    groups = organize_by_theme(d["references"], d.get("themes"))
    for theme, refs in groups.items():
        print(f"\n[{theme}] ({len(refs)})")
        for r in refs:
            print(f"  - {r.get('key', r.get('text','')[:40])}")


if __name__ == "__main__":
    _main()
