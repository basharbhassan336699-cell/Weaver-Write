"""
capabilities/tools/tool_chart.py
=================================
Tool 17: statistical charts from data.

Render bar/line/scatter/pie charts of research results as PNG/SVG for
embedding in the final document. This is the quantitative-results
counterpart to the `diagram` tool (which draws process diagrams).

Primary engine: matplotlib (via requirements — available on Termux).
For interactive artifacts, chart.js / d3 are vendored in frontend-core.

Difference from existing tools:
  - diagram : process/flow diagrams from Mermaid text
  - chart   : data-driven statistical plots from numeric series
"""
from __future__ import annotations
import os
from . import BaseTool, ToolResult

TOOL_SPEC = {
    "name": "chart",
    "description": "Render statistical charts (bar/line/scatter/pie) from numeric data to PNG/SVG for research results.",
    "triggers": ["رسم بياني", "مخطط بياني", "رسم إحصائي", "أعمدة", "منحنى", "دائري",
                 "chart", "plot", "bar chart", "line chart", "scatter", "histogram", "graph data"],
    "layers": [6, 8],
}


class ChartTool(BaseTool):
    TOOL_SPEC = TOOL_SPEC

    async def _execute(self, inputs: dict) -> ToolResult:
        action = inputs.get("action", "render")  # render | embed_docx | embed_pptx

        # embed a chart directly into a Word or PowerPoint file
        if action in ("embed_docx", "embed_pptx"):
            return await self._embed(inputs, action)

        return await self._render(inputs)

    async def _embed(self, inputs: dict, action: str) -> ToolResult:
        import os, sys
        base = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        scripts = os.path.join(base, "capabilities", "skills", "chart_builder", "scripts")
        if scripts not in sys.path:
            sys.path.insert(0, scripts)
        try:
            from embed_chart import embed_chart_in_docx, add_chart_slide
        except ImportError as e:
            return ToolResult(ok=False, error=f"chart embedder unavailable: {e}")

        spec = {
            "type": inputs.get("type", "bar"),
            "data": inputs.get("data", {}),
            "title": inputs.get("title", ""),
            "theme_id": inputs.get("theme_id", inputs.get("theme", "academic_navy")),
            "xlabel": inputs.get("xlabel", ""), "ylabel": inputs.get("ylabel", ""),
            "lang": inputs.get("lang", "ar"),
        }
        target = inputs.get("target_path")
        if not target:
            return ToolResult(ok=False, error="target_path (docx/pptx) is required")

        if action == "embed_docx":
            r = embed_chart_in_docx(target, spec, caption=inputs.get("caption", ""),
                                    lang=spec["lang"],
                                    output_path=inputs.get("output_path"))
        else:
            r = add_chart_slide(target, spec, title=inputs.get("caption", spec["title"]),
                                lang=spec["lang"], output_path=inputs.get("output_path"))
        return ToolResult(ok=r.get("ok", False), data=r if r.get("ok") else None,
                          error=r.get("error"))

    async def _render(self, inputs: dict) -> ToolResult:
        import os, sys
        # use the professional themed chart builder
        base = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        scripts = os.path.join(base, "capabilities", "skills", "chart_builder", "scripts")
        if scripts not in sys.path:
            sys.path.insert(0, scripts)
        try:
            from build_chart import build_chart
        except ImportError:
            return await self._render_basic(inputs)

        output = inputs.get("output_path", "./output/chart.png")
        r = build_chart(
            inputs.get("type", "bar"), inputs.get("data", {}), output,
            title=inputs.get("title", ""),
            theme_id=inputs.get("theme_id", inputs.get("theme", "academic_navy")),
            xlabel=inputs.get("xlabel", ""), ylabel=inputs.get("ylabel", ""),
            lang=inputs.get("lang", "ar"))
        return ToolResult(ok=r.get("ok", False), data=r if r.get("ok") else None,
                          error=r.get("error"))

    async def _render_basic(self, inputs: dict) -> ToolResult:
        chart_type = inputs.get("type", "bar")  # bar|line|scatter|pie|hist
        data = inputs.get("data", {})
        output = inputs.get("output_path", "./output/chart.png")
        title = inputs.get("title", "")
        xlabel = inputs.get("xlabel", "")
        ylabel = inputs.get("ylabel", "")

        if not data:
            return ToolResult(ok=False, error="data is required")

        os.makedirs(os.path.dirname(output) or ".", exist_ok=True)

        try:
            import matplotlib
            matplotlib.use("Agg")  # headless — no display needed (Termux-safe)
            import matplotlib.pyplot as plt
        except ImportError:
            return ToolResult(ok=False,
                error="matplotlib not available (pip install matplotlib). "
                      "For artifacts, chart.js/d3 are vendored in frontend-core.")

        fig, ax = plt.subplots(figsize=inputs.get("figsize", (8, 5)))

        try:
            if chart_type == "bar":
                labels = data.get("labels", [])
                values = data.get("values", [])
                ax.bar(labels, values, color=inputs.get("color", "#2c3e70"))
            elif chart_type == "line":
                x = data.get("x", list(range(len(data.get("y", [])))))
                ax.plot(x, data.get("y", []), marker="o")
            elif chart_type == "scatter":
                ax.scatter(data.get("x", []), data.get("y", []))
            elif chart_type == "pie":
                ax.pie(data.get("values", []), labels=data.get("labels", []),
                       autopct="%1.1f%%")
            elif chart_type == "hist":
                ax.hist(data.get("values", []), bins=inputs.get("bins", 10))
            else:
                plt.close(fig)
                return ToolResult(ok=False, error=f"unknown chart type: {chart_type}")

            if title:
                ax.set_title(title)
            if xlabel:
                ax.set_xlabel(xlabel)
            if ylabel:
                ax.set_ylabel(ylabel)

            fig.tight_layout()
            fig.savefig(output, dpi=inputs.get("dpi", 150))
            plt.close(fig)
        except Exception as e:
            plt.close(fig)
            return ToolResult(ok=False, error=f"render failed: {e}")

        return ToolResult(ok=True, data={
            "output_path": output, "type": chart_type, "engine": "matplotlib",
        })


async def run(inputs: dict) -> ToolResult:
    return await ChartTool().run(inputs)
