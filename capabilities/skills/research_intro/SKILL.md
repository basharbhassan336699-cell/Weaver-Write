---
name: research_intro
description: "Write an academic research introduction: background, significance, problem, objectives, brief methodology. Produces output in the task language (Arabic or English)."
triggers: ["مقدمة بحث", "خلفية الموضوع", "أهمية البحث", "introduction", "research background", "significance"]
layer: 6
---

# Skill: Research Introduction

## When to use
When asked to write an introduction for an academic paper or report,
in either Arabic or English.

## Required structure
An academic introduction contains these elements in order:
1. **Background** — a general lead-in placing the reader in context
2. **Significance** — why the topic is worth studying
3. **Research problem** — the knowledge gap or central question
4. **Objectives** — what the research aims to achieve (specific points)
5. **Brief methodology** — a short pointer to the approach used

## Constraints
- Default length: 300-500 words (customizable via {length})
- Every factual claim needs a citation: (Author, Year, p. X) / (المؤلف، سنة، ص. X)
- No general-knowledge content — only from RAG references

## Inputs
- `topic`: research topic (required)
- `length`: word count (optional, default 400)
- `references`: available references from the search layer
- `lang`: output language (ar/en) — selects the matching template

## Scripts
- `scripts/build_intro.py`: builds the introduction from the template

## Templates
- `templates/intro_template_ar.txt`: Arabic introduction skeleton
- `templates/intro_template_en.txt`: English introduction skeleton

## Status
- Scripts: **built and tested** (bilingual AR/EN)
