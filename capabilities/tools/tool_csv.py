"""
capabilities/tools/tool_csv.py
===============================
Tool 14: CSV/TSV data operations.

Read, write, and clean tabular data files. Fills a real gap — the pipeline
handled xlsx (excel tool) but had no dedicated CSV path for research
datasets, exported survey data, or reference tables.

Primary engine: Python csv/pandas (Termux-friendly).
The vendored papaparse.min.js is available for JS/artifact contexts.
"""
from __future__ import annotations
import os
import csv as _csv
import io
from . import BaseTool, ToolResult

TOOL_SPEC = {
    "name": "csv",
    "description": "Read, write, and clean CSV/TSV data files for research datasets and tables.",
    "triggers": ["CSV", "TSV", "بيانات جدولية", "ملف بيانات", "قراءة CSV",
                 "csv file", "tabular data", "dataset", "parse csv"],
    "layers": [2, 8],
}


class CsvTool(BaseTool):
    TOOL_SPEC = TOOL_SPEC

    async def _execute(self, inputs: dict) -> ToolResult:
        action = inputs.get("action", "read")  # read | write | clean
        if action == "write":
            return await self._write(inputs)
        if action == "clean":
            return await self._clean(inputs)
        return await self._read(inputs)

    async def _read(self, inputs: dict) -> ToolResult:
        path = inputs.get("path", "").strip()
        if not path or not os.path.exists(path):
            return ToolResult(ok=False, error=f"file not found: {path}")

        delimiter = inputs.get("delimiter", ",")
        with open(path, encoding=inputs.get("encoding", "utf-8"), newline="") as f:
            reader = _csv.reader(f, delimiter=delimiter)
            rows = list(reader)

        headers = rows[0] if rows else []
        data = rows[1:] if len(rows) > 1 else []
        return ToolResult(ok=True, data={
            "headers": headers, "rows": data,
            "count": len(data), "engine": "python-csv",
        })

    async def _write(self, inputs: dict) -> ToolResult:
        headers = inputs.get("headers", [])
        rows = inputs.get("rows", [])
        output = inputs.get("output_path", "./output/data.csv")
        delimiter = inputs.get("delimiter", ",")

        os.makedirs(os.path.dirname(output) or ".", exist_ok=True)
        with open(output, "w", encoding="utf-8", newline="") as f:
            writer = _csv.writer(f, delimiter=delimiter)
            if headers:
                writer.writerow(headers)
            writer.writerows(rows)
        return ToolResult(ok=True, data={"output_path": output, "engine": "python-csv"})

    async def _clean(self, inputs: dict) -> ToolResult:
        """Basic cleaning: strip whitespace, drop empty rows, dedupe."""
        path = inputs.get("path", "").strip()
        if not path or not os.path.exists(path):
            return ToolResult(ok=False, error=f"file not found: {path}")

        delimiter = inputs.get("delimiter", ",")
        with open(path, encoding="utf-8", newline="") as f:
            rows = list(_csv.reader(f, delimiter=delimiter))

        cleaned, seen = [], set()
        for row in rows:
            stripped = [c.strip() for c in row]
            if not any(stripped):       # drop fully empty rows
                continue
            key = tuple(stripped)
            if key in seen:             # dedupe
                continue
            seen.add(key)
            cleaned.append(stripped)

        output = inputs.get("output_path", path.replace(".csv", "_clean.csv"))
        with open(output, "w", encoding="utf-8", newline="") as f:
            _csv.writer(f, delimiter=delimiter).writerows(cleaned)

        return ToolResult(ok=True, data={
            "output_path": output,
            "rows_before": len(rows), "rows_after": len(cleaned),
            "engine": "python-csv",
        })


async def run(inputs: dict) -> ToolResult:
    return await CsvTool().run(inputs)
