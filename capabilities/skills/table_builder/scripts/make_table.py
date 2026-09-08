"""
make_table.py — build a structured table with totals (working script)
=====================================================================
Pure-logic table builder (bilingual). Produces a markdown table and,
optionally, a totals row summing numeric columns.

Usage (as a module):
    from make_table import make_table
    md = make_table(headers=["Month","Sales"], rows=[["Jan",100],["Feb",150]],
                    with_totals=True, lang="en")
"""
from __future__ import annotations
import argparse
import json


def _cell(v):
    """One clean single-line Markdown table cell. A cell value may arrive with a
    newline (a multi-line "detail") or a literal '|' — either one BREAKS a GFM
    table: the pipe row must be a single line, and an inner '|' would split into
    a bogus extra column. Collapse ALL whitespace (incl. newlines/tabs) to single
    spaces, and replace any inner '|' with '/', so the row stays exactly one line
    with the intended column count. Text meaning is preserved."""
    return " ".join(str(v).split()).replace("|", "/")


def make_table(headers, rows, with_totals=False, lang="ar"):
    """Return a markdown table string. RTL handled by the renderer, not here."""
    rtl = (lang == "ar")
    lines = []
    lines.append("| " + " | ".join(_cell(h) for h in headers) + " |")
    lines.append("| " + " | ".join("---" for _ in headers) + " |")
    for row in rows:
        lines.append("| " + " | ".join(_cell(c) for c in row) + " |")

    if with_totals and rows:
        totals = []
        for c in range(len(headers)):
            col_vals = [r[c] for r in rows if c < len(r)]
            if all(isinstance(v, (int, float)) for v in col_vals) and col_vals:
                totals.append(sum(col_vals))
            elif c == 0:
                totals.append("الإجمالي" if rtl else "Total")
            else:
                totals.append("")
        lines.append("| " + " | ".join(_cell(t) for t in totals) + " |")

    return "\n".join(lines)


def make_table_data(headers, rows, with_totals=False, lang="ar"):
    """Return structured data (for xlsx_builder/docx) instead of markdown."""
    result = {"headers": headers, "rows": [list(r) for r in rows]}
    if with_totals and rows:
        totals = []
        for c in range(len(headers)):
            col_vals = [r[c] for r in rows if c < len(r)]
            if all(isinstance(v, (int, float)) for v in col_vals) and col_vals:
                totals.append(sum(col_vals))
            elif c == 0:
                totals.append("الإجمالي" if lang == "ar" else "Total")
            else:
                totals.append("")
        result["totals"] = totals
    return result


def _main():
    p = argparse.ArgumentParser(description="Build a table")
    p.add_argument("--json", required=True)
    p.add_argument("--lang", default="ar")
    p.add_argument("--totals", action="store_true")
    args = p.parse_args()
    with open(args.json, encoding="utf-8") as f:
        d = json.load(f)
    print(make_table(d["headers"], d["rows"], args.totals, args.lang))


if __name__ == "__main__":
    _main()
