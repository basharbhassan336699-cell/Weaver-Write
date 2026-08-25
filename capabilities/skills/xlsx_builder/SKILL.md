---
name: xlsx_builder
description: "Build an Excel spreadsheet with formulas, totals, and formatting. Called by the doc_export tool."
triggers: ["Excel", "XLSX", "جدول بيانات", "شيت", "spreadsheet"]
layer: 8
---

# Skill: Excel Builder

## Capabilities
- Formulas (SUM, AVERAGE...)
- Conditional formatting
- Clear headers

## Library
openpyxl (via the doc_export tool)

## Scripts
- `scripts/build_xlsx.py`
- `scripts/recalc.py`: recalculate formulas

## Status
- `scripts/build_xlsx.py`: **built and tested** (real design, RTL/LTR aware)
