---
name: academic_content
description: >
  Governs CONTENT and STRUCTURE decisions for academic presentations —
  argument flow, evidence, and per-slide-type patterns (title, methods,
  results, discussion, references). Complements the pptx_builder skill,
  which handles visual design and file creation. Bilingual (AR/EN).
triggers:
  - عرض أكاديمي
  - عرض بحثي
  - شرائح بحث
  - مناقشة رسالة
  - محتوى العرض
  - academic presentation
  - conference talk
  - thesis defense
  - research slides
  - slide structure
---

# academic_content

Content/structure intelligence for academic presentations, adapted from the
academic-pptx skill (Claude-style). It governs WHAT goes on each slide and
in WHAT order — the reasoning layer — while pptx_builder governs how it
LOOKS and how the .pptx is produced.

## How it works (two layers, the Claude pattern)
1. **This skill** — argument structure, slide-by-slide content rules.
2. **pptx_builder** — themes, HTML→PPTX, tables, direction, fonts.
Read both before planning a deck.

## References (study before generating)
- `references/academic-pptx-SKILL.md` — the governing content skill.
- `references/content_guidelines.md` — argument structure & slide rules.
- `references/slide_patterns.md` — per-slide-type patterns (title/methods/
  results/discussion/…).
- `references/slide-types.md` — the 5 canonical slide types (cover, TOC,
  section divider, content, closing) with layout + font-size hierarchy rules.

## Slide-type taxonomy (from slide-types.md)
Every slide is exactly one of: Cover, Table of Contents, Section Divider,
Content, Closing. Each has defined layout options and a font-size hierarchy.
The generator uses this to vary layouts correctly instead of repeating one.

## Usage
The pptx generator can load these patterns into the LLM prompt so an academic
deck follows real scholarly structure (problem → methods → results →
discussion) with correct per-slide content — not just pretty layouts.
