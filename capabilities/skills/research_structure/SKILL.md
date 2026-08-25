---
name: research_structure
description: >
  Build a research outline/plan sized to the task (assignment / medium /
  large / thesis), based on structures actually used before plus academic
  conventions. Bilingual (AR/EN). Skips planning when the task dictates its
  own structure, is a Q&A, or continues earlier work.
triggers:
  - هيكلة البحث
  - خطة بحثية
  - تقسيم البحث
  - مباحث ومطالب
  - outline
  - research structure
  - research plan
---

# research_structure

Chooses a structure tier and emits a bilingual section plan.

## Tiers (from our real prior work)
- **assignment**: intro + body + conclusion + refs (3-4).
- **medium**: intro + 3 مباحث (3 مطالب each, 1.1.1 numbering) + conclusion
  + refs (~10).
- **large** (20-23 pp): intro (importance/problem/questions/objectives) +
  5 مباحث (3 مطالب each + 2.1.1 sub-divisions) + results&recommendations +
  refs (~12).
- **thesis**: front matter + chapters (intro, lit review, methodology,
  results, discussion, conclusion) + refs + appendices (~25-40).

## Override rule
If the task specifies its own structure, is a set of questions to answer, or
continues earlier work, planning is SKIPPED — the task is followed as given.

## Script
`scripts/structures.py`: `build_structure(task_card, lang)`,
`detect_tier()`, `should_plan()`.
