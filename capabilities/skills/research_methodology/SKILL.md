---
name: research_methodology
description: >
  Provide scientific research methodology scaffolding when a paper lacks one:
  approach, design, population/sample, instruments, data collection,
  validity, analysis, ethics, limitations — bilingual (AR/EN). Suggests a
  suitable approach from the topic; invents no data.
triggers:
  - منهجية البحث
  - منهج الدراسة
  - أدوات الدراسة
  - عينة الدراسة
  - methodology
  - research method
  - study population
  - data analysis
---

# research_methodology

Lays out a methodology section when the work needs one.

## Suggests an approach
From topic keywords: quantitative / qualitative / mixed / descriptive /
analytical / experimental / case study / historical.

## Components (bilingual)
approach, design, population, sample, instruments, data collection, validity
& reliability, analysis, ethics, limitations. Small tasks get the essentials
only. The writing layer fills each with topic-specific content — no fabricated
data.

## Script
`scripts/methodology.py`: `build_methodology(task_card, lang)`,
`suggest_approach()`, `has_methodology()`.
