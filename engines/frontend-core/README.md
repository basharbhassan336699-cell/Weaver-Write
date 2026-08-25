# frontend-core — JS/data libraries for artifacts & data ops

Lightweight vendored libraries supporting the `csv` tool and interactive
artifact output. Kept minified-only to stay light (Termux-friendly).

## vendored/
| File | Purpose | Used by |
|------|---------|---------|
| papaparse.min.js | Fast CSV parsing in JS/artifacts | csv (JS contexts) |
| sheetjs.min.js | Read/write xlsx in JS/artifacts | excel (JS alt) |
| lodash.min.js | General data utilities | artifacts |

## Not vendored (documented only)
- **mathjs** — advanced math; use the Python `statistics`/`numpy` path
  server-side, or load mathjs from CDN in artifacts (source is 24MB).
- **lucide / shadcn-ui** — React icon/UI kits for artifact rendering;
  load from CDN in the artifact runtime rather than bundling.
- **tfjs** — TensorFlow.js; out of scope for the research pipeline.
- **tone** — audio synthesis; not relevant to academic research output.

## Rationale
Weaver Write is a Python-first research system. Data work (CSV, stats,
xlsx) is done server-side in Python; these JS libraries are for the
artifact/UI layer only, so only the small, high-value ones are bundled.
