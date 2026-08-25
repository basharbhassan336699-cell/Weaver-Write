---
name: pptx_builder
description: "Build a professional PowerPoint deck with Kufyan Arabic Black font and consistent layout. Called by the doc_export tool."
triggers: ["PowerPoint", "PPTX", "عرض تقديمي", "شرائح", "بوربوينت", "slides", "presentation"]
layer: 8
---

# Skill: PowerPoint Builder

## Capabilities
- Kufyan Arabic Black font for headings
- Consistent layout across slides
- RTL support
- Professional colors

## Library used
python-pptx (via the doc_export tool)

## Typical structure
1. Title slide
2. Content (3-5 points per slide)
3. Conclusion/references slide

## Scripts
- `scripts/build_pptx.py`
- `scripts/thumbnail.py`: preview slides as images

## Templates
- `templates/academic_ar.pptx`
- `templates/academic_en.pptx`

## Status
- `scripts/build_pptx.py`: **built and tested** (real design, RTL/LTR aware)
- `scripts/thumbnail.py`: **built and tested** (real design, RTL/LTR aware)

## Theme system (HTML → native PPTX, the Claude way)
The builder can design in HTML/CSS and convert to native editable PPTX via
the html2pptx-core engine. This unlocks theme variety:

Themes (themes/themes.json): academic_navy, academic_green, formal_gray,
modern_blue, creative_purple, warm_maroon — each a full palette + fonts.

The theme is chosen from a free-text design request (bilingual):
- "عرض رسمي / formal business" → formal_gray
- "إبداعي / creative" → creative_purple
- "بحث أكاديمي / academic" → academic_navy
- "حديث تقني / modern tech" → modern_blue
- "تاريخي أدبي / traditional" → warm_maroon

Scripts:
- `scripts/html_deck_generator.py`: request → theme → themed HTML (RTL/LTR aware)
- `scripts/html2pptx_bridge.py`: HTML → native PPTX via engines/html2pptx-core
- `scripts/build_pptx.py`: fallback native builder (navy/gold)

Direction: Arabic → RTL (right-anchored), English → LTR (left-anchored),
handled in the generated CSS (dir + text-align + anchor side).

## Three build paths (highest to lowest fidelity)
1. **LLM-authored (the fullest Claude way)** — pass `llm_fn` to the powerpoint
   tool. An LLM writes creative HTML/CSS per slide (varied layouts: cards,
   columns, timelines, quotes...), guided by the chosen theme palette, then
   html2pptx converts to native editable PPTX. Unbounded layout variety.
   Script: `scripts/llm_deck_generator.py` (sanitizes + validates the HTML,
   retries on failure, falls back to the template if the LLM output is invalid).
2. **Themed template** — no LLM: `html_deck_generator.py` fills a themed HTML
   template (6 palettes) → html2pptx. Color/font variety, fixed layout.
3. **Native fallback** — `build_pptx.py` (python-pptx) when Node is unavailable.

The tool auto-selects: llm_fn present → path 1; else → path 2; Node missing → path 3.
Direction (RTL/LTR) is enforced in the prompt and re-checked after generation.

## Visual self-correction loop (the complete Claude way)
The highest-fidelity path adds a visual QA loop. Pass BOTH `llm_fn` and
`vision_fn` to the powerpoint tool:

    generate HTML -> html2pptx -> render slide thumbnails (PNG)
        -> vision_fn inspects images against a defect checklist
        -> if issues: llm_fn fixes the HTML -> repeat (up to max_rounds)
        -> stop when clean

Checklist enforced by the vision model: text overflow, element overlap,
clipped text, poor contrast, empty/unbalanced areas, wrong reading
direction (Arabic must be RTL), unreadably small text.

Script: `scripts/visual_review_loop.py` — `review_and_correct(...)`.
Callables are provider-agnostic:
- `llm_fn(prompt)->str` authors and fixes HTML
- `vision_fn(prompt, images)->str` inspects the rendered PNGs (returns JSON verdict)

Degrades safely: no `vision_fn` -> single build (no visual loop); no
LibreOffice/poppler -> skips rendering and returns the built deck.

Tool result includes `review_rounds` and `final_clean` so callers know
whether the deck passed visual QA.

## Extended theme library (12 themes)
Six base themes plus six palettes extracted from real, visually-QA'd decks
built earlier:

Base: academic_navy, academic_green, formal_gray, modern_blue,
creative_purple, warm_maroon.

From prior real work (tested hex values):
- **uae_heritage** — green #1A5C38 + gold #C8922A (UAE economy decks)
- **midnight_teal** — teal #00B4D8 + gold #F4A623 (sports/tech decks)
- **midnight_executive** — navy #0A1628 + gold #C8A04A (leadership/business)
- **royal_burgundy** — wine #7B1D3C + antique gold #C8973A (media/literary)
- **cyber_dune** — ivory #F9F6F0 + matte gold #C5A059 (tourism/premium)
- **e_red** — signature red #E30613 (telecom/corporate brand)

The LLM prompt also carries a PROVEN LAYOUT VOCABULARY drawn from those decks
(two-panel covers, numbered agenda cards, section dividers, card rows,
two-column splits, oversized stats, corner motif, closing slide) — offered as
a design vocabulary the LLM mixes per content, not a rigid template.

## 17 themes + real reference layouts
Theme library expanded to 17 with 5 creative styles extracted from real
prior templates:
- **editorial_minimal** — sand #F5EFE6 + terracotta #B85042 (ghost-numeral motif)
- **neon_tech_grid** — neon #00FFC2 on #0B0E14 (grid backdrop + scanline + mono)
- **organic_nature** — green #2C5F2D + sage #97BC62 (organic blob frames)
- **swiss_poster_bold** — blue #2F3C7E + red #990011 (Swiss grid, bold type)
- **ocean_glass** — teal #1C7293 + mint #6FE3C9 (gradient waves + glass cards)

## Reference layouts (templates/reference_layouts/)
27 REAL, previously-built HTML slide templates the LLM studies for layout
ideas: Expo2020 set (cover, toc, three-col circles, stats+image, stacked
cards, section dividers, two-col variants, five-cards-icon, closing quote,
references), 5 creative styles, and Friends&Family set (cover, three cards,
timeline, six-card grid, story+outlined cards, takeaways, closing).
`load_reference_layout(hint)` injects a matching one into the LLM prompt so
generated decks echo proven, real designs — not generic layouts.
Note: uploaded templates are 1280x720; the generator normalizes to the
deck's target size.

## Direction handling (verified, both languages)
Every generated slide is direction-correct for its language:
- **Arabic (lang="ar") → RTL**: elements anchored from the RIGHT
  (CSS `right:`), `dir="rtl"`, `direction:rtl`, `text-align:right`.
- **English (lang="en") → LTR**: elements anchored from the LEFT
  (CSS `left:`), `dir="ltr"`, `direction:ltr`, `text-align:left`.

The 27 reference layouts are direction-mixed as authored (20 RTL, 7 LTR),
but `load_reference_layout(hint, lang)` NORMALIZES each to the task language
via `normalize_direction()` before it reaches the LLM prompt — so an Arabic
task always sees an RTL example and an English task always sees an LTR one.
(Native python-pptx fallback also sets paragraph-level rtl=1 / algn for
Arabic; the html2pptx path expresses direction through box position +
alignment instead, which is visually equivalent.)

## Custom colors (any color, still harmonious)
Pass `custom_color` (any hex, e.g. "6B8E23") to the powerpoint tool and the
system builds a COMPLETE harmonious theme around it via
`palette_generator.custom_theme()`: a matching accent (near-complementary
hue), a light tinted background, a dark title panel, and contrast-checked
text — so any color the user picks stays professional and readable.
Priority: custom_color > theme_id > design request.

## Native tables in slides (pptx_table.py) — direction-correct
`add_table_slide()` adds a REAL PowerPoint table (a:tbl), themed and
direction-aware:
- Arabic: table marked rtl="1", COLUMNS REVERSED so the first logical column
  sits on the right, cells right-aligned — a proper right-to-left table.
- English: normal LTR.
Themed header (primary fill, white bold) + optional totals row (accent).
Tool: `{"action":"add_table", "headers":[...], "rows":[...], "totals":[...],
"lang":"ar", "theme_id":"...", "output_path":"deck.pptx"}`.
