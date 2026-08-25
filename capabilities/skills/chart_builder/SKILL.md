---
name: chart_builder
description: >
  Build professional, theme-consistent statistical charts and embed them
  directly into Word or PowerPoint files. 12 chart types with palettes that
  match the presentation themes, correct RTL/LTR label handling.
triggers:
  - رسم بياني
  - مخطط بياني
  - رسم إحصائي
  - أضف رسم للتقرير
  - رسم في الوورد
  - رسم في العرض
  - chart
  - graph
  - plot
  - embed chart
  - chart in document
  - add chart to report
---

# chart_builder

Professional charting that matches the quality Claude adds to files.

## Chart types (12)
bar, horizontal_bar, grouped_bar, stacked_bar, line, area, multi_line,
scatter, pie, donut, histogram, radar.

## Themes
Charts reuse the 17 presentation palettes (themes.json), so a chart embedded
in a deck or report visually matches the slides. Pass `theme_id` (e.g.
uae_heritage, midnight_teal, royal_burgundy...).

## Direction
Arabic labels are reshaped (arabic-reshaper + bidi) and the y-axis moves to
the right for RTL; English stays LTR.

## Scripts
- `scripts/build_chart.py` — render a themed chart to PNG/SVG.
- `scripts/embed_chart.py` — render AND insert into a docx (captioned,
  centered) or add as a pptx slide. This is the automatic chart→file link.

## Status
- Both scripts: **built and tested** (12/12 chart types, docx+pptx embed).

## Coordinated but distinct chart colors
Chart series colors come from `palette_generator.chart_series_colors()`,
which walks the theme's hue family to produce N VISUALLY DISTINCT colors.
This solves the key problem: a single-hue ramp makes bars/slices blend and
disappear. Instead each bar/slice is separable AND coordinated with the deck
theme. Works with named themes and with a custom hex color (pass theme_id as
the hex, e.g. "6B8E23").
