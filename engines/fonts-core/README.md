# fonts-core — bundled open-source fonts

Offline Arabic/Latin fonts so Weaver Write renders consistently without
depending on device-installed fonts.

## Bundled Arabic fonts (OFL, open-source)
| Family | Weights | Best for |
|--------|---------|----------|
| **Kufyan Arabic** | Regular | user's preferred font (provided & bundled) |
| Amiri | Regular, Bold | academic body text (classical Naskh) |
| Cairo | Variable (all weights) | modern slides/headings |
| Tajawal | Regular, Bold, Black | clean modern sans |
| Noto Naskh Arabic | Variable | highly legible, wide coverage |

## About "Kufyan Arabic Black"
This is the user's preferred deck font, but it is COMMERCIAL and cannot be
bundled or downloaded freely. The builders name it first (so it's used when
installed on the device) and fall back automatically to the closest open
substitute — **Cairo Black** or **Tajawal Black** — otherwise.

## Usage
`fonts.py` provides:
- `resolve_arabic_font(preferred, weight)` -> (family, ttf_path)
- `register_for_matplotlib(preferred)` -> registers + returns family (charts)
- `font_path(family, weight)` -> ttf path (docx/pdf embedding)

Wired into: chart_builder (matplotlib), pdf_builder (reportlab). Slides via
html2pptx use the family name; install the font on the device for exact match.


## Fonts requested per task (Word/PowerPoint)
The builders accept a `font` parameter. Whatever font the user asks for is
WRITTEN INTO the file (docx/pptx), so Word/PowerPoint on the device renders
it with the real font. Commercial fonts that ship with Office render
correctly there even though we can't bundle them:

| Requested font | Type | In file | Preview fallback |
|----------------|------|---------|------------------|
| Kufyan Arabic Regular | bundled (user-provided) | written as-is | Kufyan Arabic (real) |
| Kufyan Arabic Black | commercial | written as-is | Kufyan Regular / Cairo |
| Simplified Arabic | commercial (Office) | written as-is | Amiri |
| Arial | commercial (Office) | written as-is | DejaVu Sans |
| Times New Roman | commercial (Office) | written as-is | DejaVu Serif |
| Amiri / Cairo / Tajawal / Noto Naskh | open (bundled) | written as-is | itself |

`resolve_named_font(name)` maps any requested name to a renderable family for
server-side preview WITHOUT changing what the document says. Slides also embed
a CSS fallback chain (requested → Cairo/Tajawal/Amiri) so they look right even
before the commercial font is present.
