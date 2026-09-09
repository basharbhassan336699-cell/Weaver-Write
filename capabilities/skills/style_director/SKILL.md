---
name: style_director
description: >
  Produces a short, model-DECIDED style directive that Layer 6 appends to the
  section-writing prompt. It supplies the writing-style guidance the base
  prompt lacked: mixing continuous narrative with bullet points BY THE NATURE
  OF THE INFORMATION (activating the principle of the narrative_bullet_mixing
  skill), a human academic voice with varied rhythm and a measured stance,
  employed rhetorical questions where they serve the analysis, and a
  non-standard closing for conclusion-like sections. It describes WHEN to use
  each device and never forces it, so the model stays the author. Bilingual
  (AR/EN). Governs presentation STYLE only — not statistical/methodological
  correctness, and not citation integrity.
triggers:
  - أسلوب
  - سرد
  - نقاط
  - نبرة بشرية
  - خاتمة غير نمطية
  - style
  - narrative
  - bullets
  - human voice
---

# Skill: Style Director

## Purpose
The section writers were governed only by a one-line "academic, human-toned,
varied rhythm" instruction. This skill adds the missing style intelligence as a
compact directive block injected into the writing prompt — leaving the decision
to the model.

## Script
- `scripts/style_directives.py`
  - `build_style_block(card, section_name, lang="ar") -> str`
    Returns a concise directive (or `""` for a references section). Pure logic,
    no model call, never raises for normal input.

## What it injects
1. **Narrative vs. bullets by information nature** — bullets only for countable,
   homogeneous, independent items with no causal link; narrative for a single
   connected idea. Never bullets just to break monotony.
2. **Human academic voice** — varied sentence length/rhythm, a measured stance,
   no filler / excess emotion / mechanical repetition.
3. **Employed questions** — open an idea with a research question where it
   serves the analysis, then answer it.
4. **Non-standard closing** — for conclusion-like sections: a question, a
   paradox, or a brief reflection instead of a repetitive "In conclusion".

## Wiring
Called in `pipeline/orchestrator.py` Layer 6 for each generic-writer section:
the returned block is appended to the writing prompt (same mechanism as the
depth/Islamic directives). Fully guarded: any failure → no block, writing
continues unchanged. Toggle with `WEAVER_STYLE_DIRECTOR` (default on).

## Boundaries
Style/presentation only. It does not touch citations, strict-RAG, statistical
validity, or file building.
