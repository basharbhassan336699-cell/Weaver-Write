"""
format_results.py — organize research results (working script)
==============================================================
Builds the results section structure: for each result, a table (if data is
numeric) + a present/interpret/link scaffold. Optional LLM writes the prose
interpretation. Provider-agnostic.

Usage (as a module):
    from format_results import format_results
    out = format_results(results, lang="ar", llm_fn=my_llm)
"""
from __future__ import annotations
import argparse
import json
import sys
import os

# reuse make_table from the table_builder skill
_TB = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), "table_builder", "scripts")
if _TB not in sys.path:
    sys.path.insert(0, _TB)


def format_results(results, lang="ar", llm_fn=None):
    """
    results: list of dicts, each:
        {"title": str, "data": {"headers":[...], "rows":[...]}?, "note": str?}
    Returns: {"text": str, "structured": bool}
    """
    try:
        from make_table import make_table
    except ImportError:
        make_table = None

    blocks = []
    for i, res in enumerate(results, 1):
        title = res.get("title", f"Result {i}")
        block = [f"## {title}"]

        # table if data present
        data = res.get("data")
        if data and make_table:
            block.append(make_table(data.get("headers", []), data.get("rows", []),
                                    with_totals=res.get("totals", False), lang=lang))

        # interpretation
        if llm_fn:
            guide = ("اعرض النتيجة، فسّرها، ثم اربطها بالأدبيات السابقة."
                     if lang == "ar" else
                     "Present the result, interpret it, then link it to prior literature.")
            prompt = (f"{guide}\n\nالنتيجة: {title}\nملاحظات: {res.get('note','')}"
                      if lang == "ar" else
                      f"{guide}\n\nResult: {title}\nNotes: {res.get('note','')}")
            block.append(llm_fn(prompt).strip())
        else:
            block.append("[العرض] [التفسير] [الربط بالأدبيات]" if lang == "ar"
                         else "[Presentation] [Interpretation] [Link to literature]")
        blocks.append("\n\n".join(block))

    return {"text": "\n\n".join(blocks), "structured": llm_fn is None}


def _main():
    p = argparse.ArgumentParser()
    p.add_argument("--json", required=True)
    p.add_argument("--lang", default="ar")
    args = p.parse_args()
    with open(args.json, encoding="utf-8") as f:
        d = json.load(f)
    print(format_results(d["results"], args.lang)["text"])


if __name__ == "__main__":
    _main()
