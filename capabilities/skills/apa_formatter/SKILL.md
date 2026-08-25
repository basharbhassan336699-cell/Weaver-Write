---
name: apa_formatter
description: "Format the reference list in APA 7th style: alphabetical order, hanging indent, DOI as a link."
triggers: ["APA", "توثيق APA", "قائمة مراجع", "references APA", "APA style"]
layer: 8
---

# Skill: APA 7th Formatting

## Core rules
- Alphabetical order by surname
- Hanging indent
- DOI as a link: https://doi.org/xxx
- Year in parentheses immediately after the author

## Common forms
- Article: Author, F. (Year). Title. Journal, Volume(Issue), Pages.
- Book: Author, F. (Year). Title. Publisher.

## Scripts
- `scripts/format_apa.py`: converts reference data to correct APA form
