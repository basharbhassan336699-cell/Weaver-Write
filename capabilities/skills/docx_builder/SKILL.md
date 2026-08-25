---
name: docx_builder
description: "Build a professional Word document with Arabic RTL support, headings, tables, and citations. Called by the doc_export tool."
triggers: ["Word", "DOCX", "مستند وورد", "ملف Word", "word document"]
layer: 8
---

# Skill: Word Document Builder

## Capabilities
- Full RTL support for Arabic
- Multi-level headings
- Formatted tables
- Automatic reference list
- Professional Arabic font

## Library used
python-docx (via the doc_export tool)

## Constraints
- For Arabic: set paragraph direction to RTL
- Default font: a clear Arabic font

## Scripts
- `scripts/build_docx.py`: builds the full document
- `scripts/validate_docx.py`: verifies structure integrity

## Templates
- `templates/academic_ar.docx`: ready Arabic paper template
- `templates/academic_en.docx`: ready English paper template

## Rich Word features (docx_advanced.py) — Claude-level
Beyond basic text, the builder now supports:
- **Formatted tables**: colored header row (theme primary), cell shading,
  borders, optional totals row; RTL tables use `<w:bidiVisual/>` so columns
  read right-to-left for Arabic.
- **Inline images** with centered captions.
- **Two-column** newspaper layout (`<w:cols>`), for magazine-style docs.
- **Header/footer** with automatic **page numbers** (PAGE field).
- **Table of contents** (TOC field; Word builds it on "update fields").
- **Colored headings** using the shared presentation theme.

Direction is correct throughout: Arabic paragraphs/tables get `<w:bidi/>` /
`<w:bidiVisual/>` and right alignment; English stays LTR left-aligned.

Theme colors are shared with the deck themes (themes.json), so a report and a
presentation on the same topic match visually.

The `word` tool auto-selects rich mode when a section has a table/image or
when toc/header_text/two_columns is requested; otherwise it uses the basic
builder. Pass `font` to control the typeface (e.g. "Kufyan Arabic").

## Mathematical equations (docx_math.py)
Native Word equations (OMML) — real equations, not images. Pass `equation`
in a section (string or list). Supports fractions (a/b), superscripts (x^2),
subscripts (x_i), roots (\sqrt{x}), Greek letters (\alpha ...), and common
operators/symbols. Optional latex2mathml for full LaTeX coverage; the built-in
converter handles common academic cases with no dependency.

## Cover page + Table of Contents (docx_frontmatter.py)
- **Cover page** (add_cover_page): mandatory title page for any real task —
  institution, title, subtitle, author, supervisor, course, date — centered,
  themed, RTL/LTR correct. Skipped only for in-place edits, fragments/
  continuations, or an explicit "no cover" instruction; added by default
  otherwise. Policy helper: should_add_cover(task_card).
- **Table of contents** (add_toc_page): real Word TOC field, bilingual,
  direction-correct. Placement via resolve_toc_position(task_card):
  "after_cover" (page 2, the default when requested-but-unspecified) or "end"
  (last page).

## Deep OOXML references (added from Claude's docx skill)
references/ooxml-reference.md and docx-js-reference.md document the raw OOXML
for advanced features we didn't cover: tracked changes (redlining), comments,
and full validation. scripts/ooxml/ has pack/unpack/validate plus redlining
validation. These COMPLEMENT our builders (they don't replace them).
