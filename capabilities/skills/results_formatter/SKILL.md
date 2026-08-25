---
name: results_formatter
description: "Organize research results into a structured scientific section with tables, logical sequence, and interpretation linked to the literature. Output in the task language."
triggers: ["نتائج", "عرض النتائج", "تحليل النتائج", "results", "findings", "results analysis"]
layer: 6
---

# Skill: Results Formatter

## Principle
Each result is presented, then interpreted, then linked to prior literature.

## Structure
1. Present the result (text + table/figure if needed)
2. Interpret the result
3. Link it to the review studies (agreement/disagreement)

## Constraints
- Use tables for numeric data
- Do not repeat table numbers verbatim in the text

## Scripts
- `scripts/format_results.py`: builds tables from raw data

## Status
- Scripts: **built and tested** (bilingual AR/EN)
