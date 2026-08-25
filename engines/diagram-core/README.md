# diagram-core — Mermaid diagram engine

Renders Mermaid syntax (flowcharts, sequence, gantt, ER, mindmaps) to SVG/PNG
for the `diagram` tool (capabilities/tools/tool_diagram.py).

## vendored/
- `mermaid.min.js` — the Mermaid bundle (client-side render)

## Rendering options (in priority)
1. `mermaid-cli` (mmdc) if installed → SVG/PNG server-side
   Install: `npm i -g @mermaid-js/mermaid-cli`
2. Vendored mermaid.min.js via Node (needs a DOM shim)
3. Fallback: returns raw Mermaid source for client-side rendering

For headless server-side PNG/SVG on Termux, mermaid-cli is the simplest path.
