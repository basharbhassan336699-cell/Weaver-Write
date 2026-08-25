---
name: quran_hadith_citation
description: >
  Precise typographic formatting for quoting Quranic verses (آيات) and
  Prophetic hadiths (أحاديث) inside documents. Governs the enclosing marks,
  bold weight, and citation rendering — NOT source verification or file
  creation. Use whenever a verse or hadith is inserted into a Word/PowerPoint
  document, even if the user just pastes it and says "add it".
triggers:
  - آية قرآنية
  - آيات قرآنية
  - حديث نبوي
  - أحاديث
  - قرآن
  - تخريج الحديث
  - quran verse
  - hadith
  - quranic citation
---

# quran_hadith_citation

Applies the exact conventions (see references/formatting-rules.md).

## Quranic verses
- Enclosed in the ornamental Quran brackets ﴿ ﴾ (U+FD3E/FD3F) — never normal
  parentheses or quotes.
- The whole verse is BOLD.
- Citation "(Surah: Ayah)" after it, smaller/normal, e.g. (البقرة: 286).

## Prophetic hadiths
- Enclosed in Arabic double angle quotes « » — NEVER the Quran brackets
  (mixing the two is strictly forbidden).
- Matn is BOLD; an optional key phrase may be red (still bold).
- Optional non-bold lead-in "قال رسول الله ﷺ:".
- Takhrij after it (narrator, source, grading), smaller/normal, e.g.
  رواه البخاري، صحيح.

## Important
Formatting only — this does NOT verify a verse belongs to its surah or that a
hadith's grading is correct. Source accuracy is a separate responsibility.

## The cleaner respects these marks
The AI-fingerprint cleaner keeps ﴿ ﴾ and « » (they are sacred/legitimate
marks, not AI decoration) while still removing ★ → | etc.

## Script
`scripts/quran_hadith.py`: `add_quran_verse(doc, verse, surah, ayah)`,
`add_hadith(doc, matn, narrator, source, grading, key_phrase)`.
