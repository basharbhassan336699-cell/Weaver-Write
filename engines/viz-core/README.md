# viz-core — visualization & workflow engine

Backs the `chart` tool and hosts the langgraph workflow dependency.

## vendored/
| Component | Purpose | Used by |
|-----------|---------|---------|
| langgraph | Graph workflow framework (the 11-layer pipeline foundation) | orchestrator |

## Via requirements (not vendored — too heavy to bundle)
- **matplotlib** (~37MB with data) — static statistical charts. Available
  on Termux via `pip install matplotlib`. Used by the `chart` tool.

## Interactive charts (in frontend-core/vendored)
- **chart.js** — interactive JS charts for artifacts
- **d3** — advanced data-driven visualizations for artifacts

## Documented only (not bundled)
- **recharts** — React charts; load from CDN in artifacts (heavy React dep).
- **trustgraph** — full GraphRAG framework (CLI+flow+MCP+base); a large
  system, not a simple library. If GraphRAG is ever needed, integrate it
  as a service alongside paperqa-core rather than vendoring.
- **graphify** — code-project mapper; out of scope for research.
- **graft** — knowledge-graph builder; overlaps trustgraph.
- **md-preview** — the uploaded archive duplicated recharts; excluded.

## Tool boundaries
- `chart`   → data-driven statistical plots (bar/line/scatter/pie)
- `diagram` → process/flow diagrams from Mermaid (diagram-core)
