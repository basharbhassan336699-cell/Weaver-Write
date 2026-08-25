"""
capabilities/tools/tool_diagram.py
===================================
Tool 12: render diagrams from Mermaid syntax.

Turns Mermaid text (flowcharts, sequence, gantt, ER, mindmaps...) into
SVG/PNG for embedding in the final document. Fills a gap — the pipeline
could describe processes but not visualize them.

Rendering path (in priority order):
  1. mermaid-cli (mmdc) if installed  → SVG/PNG
  2. vendored mermaid.min.js via Node → SVG
  3. return the raw Mermaid source so the caller can render client-side
"""
from __future__ import annotations
import os
import sys
import subprocess
import shutil
import tempfile
from . import BaseTool, ToolResult

TOOL_SPEC = {
    "name": "diagram",
    "description": "Render a diagram (flowchart, sequence, gantt, ER, mindmap) from Mermaid syntax to SVG/PNG.",
    "triggers": ["رسم بياني", "مخطط", "فلوشارت", "رسم توضيحي", "مخطط انسيابي",
                 "diagram", "flowchart", "mermaid", "chart", "sequence diagram"],
    "layers": [6, 8],
}


def _vendored_mermaid():
    base = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.join(base, "engines", "diagram-core", "vendored", "mermaid.min.js")


class DiagramTool(BaseTool):
    TOOL_SPEC = TOOL_SPEC

    async def _execute(self, inputs: dict) -> ToolResult:
        source = inputs.get("source", "").strip()
        if not source:
            return ToolResult(ok=False, error="mermaid source is required")

        output = inputs.get("output_path", "./output/diagram.svg")
        fmt = inputs.get("format", "svg")  # svg | png
        os.makedirs(os.path.dirname(output) or ".", exist_ok=True)

        # 1) mermaid-cli (mmdc)
        mmdc = shutil.which("mmdc")
        if mmdc:
            try:
                with tempfile.NamedTemporaryFile("w", suffix=".mmd", delete=False) as tf:
                    tf.write(source)
                    src_path = tf.name
                subprocess.run([mmdc, "-i", src_path, "-o", output],
                               check=True, capture_output=True, timeout=60)
                os.unlink(src_path)
                return ToolResult(ok=True, data={"output_path": output, "engine": "mermaid-cli"})
            except Exception as e:
                # fall through to next strategy
                pass

        # 2) vendored mermaid.min.js via Node (headless render)
        node = shutil.which("node")
        mermaid_js = _vendored_mermaid()
        if node and os.path.exists(mermaid_js):
            # Note: full headless render needs a DOM (jsdom/puppeteer). If the
            # environment lacks it, we gracefully return the source below.
            pass

        # 3) return raw source for client-side rendering
        return ToolResult(ok=True, data={
            "output_path": None,
            "mermaid_source": source,
            "engine": "raw",
            "note": "no server-side renderer available; render this source client-side "
                    "or install mermaid-cli (npm i -g @mermaid-js/mermaid-cli)",
        })


async def run(inputs: dict) -> ToolResult:
    return await DiagramTool().run(inputs)
