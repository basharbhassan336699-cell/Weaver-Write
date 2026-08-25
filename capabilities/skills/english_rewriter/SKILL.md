---
name: english_rewriter
description: "Rewrite text into natural academic English while keeping all citations intact — to reduce AI-detection signatures. English-only output."
triggers: ["rewrite", "humanize", "academic english", "reword", "أنسنة إنجليزي"]
layer: 65
---

# Skill: English Academic Rewriter

## Goal
Transform AI-signature text into natural academic English,
preserving every citation and page number.

## Rules
- Never alter citations (Author, Year, p. X)
- Vary sentence structure and length
- Avoid AI-signature vocabulary

## Scripts
- `scripts/rewrite_en.py`: protects citations with placeholder tokens

## Dictionary-based humanization
`humanize_text(text)` now reduces AI-signature phrasing using a large bundled
dictionary (engines/humanizer-core/): 550 EN + 131 AR curated AI-signature
words/phrases mapped to human alternatives, plus ~104K general synonyms
(ON by default, general_rate=0.25; dictionary to be refined later).
Longest phrases match first; matching is case-insensitive with word
boundaries. CITATIONS ARE PROTECTED throughout (author-year and page forms,
Arabic and Latin) and verified intact after rewriting.

## AI-fingerprint cleaning (file-type aware, silent)
Before synonym replacement, the rewriter cleans visual/linguistic AI tells
via engines/humanizer-core/text_cleaner.py:
- Long dashes (— ─ ──): "word—word"→"word word", "word — word"→"word word",
  "—phrase—"→"-phrase-", lone "—"→"-".
- Decorative symbols removed in prose: ★ ☆ ✓ ✗ ✦ ◆ • → ← ↑ ↓ | ` �
  ("A | B | C" → "A، B، C"). Backticks removed.
- Language-mix fixed: stray CJK removed; a foreign letter glued inside a word
  ("Caر","بياناT") is normalized to the majority script; a whole Latin word
  inside Arabic prose ("...Remains...") is FLAGGED for review, not deleted.
- Linguistic tells reported ("علاوة على ذلك", "Furthermore," ...) so the
  synonym pass can vary them.
FILE-TYPE AWARE: full cleaning for docx/pdf; PowerPoint KEEPS visual symbols
(slides use them legitimately); Excel gets light cleaning. Applied silently —
the user isn't told it ran. Citations are always protected and verified.
