---
name: slide_designer
description: "Propose a slide structure: for each slide, the title, key points, and suggested visual type. Output in the task language."
triggers: ["تصميم شرائح", "هيكل عرض", "خطة عرض", "slide structure", "deck outline", "slide design"]
layer: 6
---

# Skill: Slide Designer

## Output
Per slide:
- Title
- 3-5 key points
- Visual type (chart/table/image/text)

## Constraints
- Number of slides per {slide_count}
- Balanced content across slides

## Scripts
- `scripts/design_slides.py`

## Status
- Scripts: **built and tested** (bilingual AR/EN)
