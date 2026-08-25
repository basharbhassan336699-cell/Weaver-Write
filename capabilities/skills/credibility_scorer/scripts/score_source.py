"""
score_source.py — compute a credibility score (working script)
==============================================================
Pure-logic scorer (no LLM). Scores a source 0-50 across five criteria,
each 0-10, and returns a verdict.

Usage (as a module):
    from score_source import score_source
    result = score_source({
        "peer_reviewed": True, "publisher_known": True,
        "author_affiliation": True, "year": 2023,
        "citation_count": 45,
    })
"""
from __future__ import annotations
import argparse
import json
from datetime import datetime


def score_source(meta: dict, current_year: int = None) -> dict:
    """Score a source. meta keys are optional; missing -> conservative 0."""
    current_year = current_year or datetime.now().year
    scores = {}

    # 1. Publisher (0-10)
    scores["publisher"] = 10 if meta.get("publisher_known") else (
        5 if meta.get("has_publisher") else 0)

    # 2. Peer review (0-10)
    scores["peer_review"] = 10 if meta.get("peer_reviewed") else 0

    # 3. Author affiliation (0-10)
    scores["author"] = 10 if meta.get("author_affiliation") else (
        4 if meta.get("author_named") else 0)

    # 4. Recency (0-10): full marks within 5 years, decaying after
    year = meta.get("year")
    if year:
        age = max(0, current_year - int(year))
        scores["recency"] = max(0, 10 - max(0, age - 5))
        scores["recency"] = min(10, scores["recency"])
    else:
        scores["recency"] = 0

    # 5. Citation impact (0-10): log-ish buckets
    cites = meta.get("citation_count", 0) or 0
    if cites >= 100:   scores["impact"] = 10
    elif cites >= 50:  scores["impact"] = 8
    elif cites >= 20:  scores["impact"] = 6
    elif cites >= 5:   scores["impact"] = 4
    elif cites >= 1:   scores["impact"] = 2
    else:              scores["impact"] = 0

    total = sum(scores.values())
    if total >= 40:   verdict = "high"
    elif total >= 25: verdict = "moderate"
    else:             verdict = "low"

    return {
        "total": total, "max": 50, "percent": int(total / 50 * 100),
        "breakdown": scores, "verdict": verdict,
    }


def _main():
    p = argparse.ArgumentParser(description="Score source credibility")
    p.add_argument("--json", required=True, help="JSON file with source metadata")
    args = p.parse_args()
    with open(args.json, encoding="utf-8") as f:
        meta = json.load(f)
    r = score_source(meta)
    print(f"Score: {r['total']}/50 ({r['percent']}%) — {r['verdict']}")
    for k, v in r["breakdown"].items():
        print(f"  {k}: {v}/10")


if __name__ == "__main__":
    _main()
