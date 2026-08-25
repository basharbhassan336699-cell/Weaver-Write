---
name: literature_review
description: "Write a literature review organized by themes (not by reference), highlighting agreements and disagreements between studies. Output in the task language."
triggers: ["مراجعة أدبيات", "دراسات سابقة", "الإطار النظري", "literature review", "related work", "theoretical framework"]
layer: 6
---

# Skill: Literature Review

## When to use
When writing the related-work or theoretical-framework section.

## Core principle
Organize the review **by theme**, not by reference.
Common mistake: "X said... then Y said..." (a list of references).
Correct: "Regarding the first theme, several studies showed... while they differed in..."

## Structure
1. Review intro (the themes to be covered)
2. Per theme: presentation of studies, points of agreement, points of disagreement
3. The research gap your current study fills

## Constraints
- Use **only** the references passed in {references}
- Every claim carries a page-accurate citation
- Highlight contradictions between studies objectively

## Scripts
- `scripts/organize_by_theme.py`: groups references by theme

## Templates
- `templates/litreview_template_ar.txt`
- `templates/litreview_template_en.txt`

## Status
- Scripts: **built and tested** (bilingual AR/EN)
