"""
capabilities/tools/tool_powerpoint.py
======================================
Tool 8: PowerPoint operations.

Build:  via the `pptxgenjs` JavaScript library (vendored) or python-pptx.
Read:   via markitdown.

Complements the pptx_builder skill (know-how) with a build/read interface.
"""
from __future__ import annotations
import os
import sys
from . import BaseTool, ToolResult

TOOL_SPEC = {
    "name": "powerpoint",
    "description": "Build or read PowerPoint (.pptx) files. Build via pptxgenjs/python-pptx, read via markitdown.",
    "triggers": ["PowerPoint", "PPTX", "عرض تقديمي", "شرائح", "بوربوينت",
                 "presentation", "slides", "read pptx", "build slides"],
    "layers": [8],
}


def _vendored_dir():
    base = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.join(base, "engines", "office-core", "vendored")


class PowerPointTool(BaseTool):
    TOOL_SPEC = TOOL_SPEC

    async def _execute(self, inputs: dict) -> ToolResult:
        action = inputs.get("action", "build")
        if action == "read":
            return await self._read(inputs)
        if action == "add_table":
            return await self._add_table(inputs)
        return await self._build(inputs)

    async def _add_table(self, inputs: dict) -> ToolResult:
        """Add a native, direction-correct table slide to a deck."""
        import os, sys
        base = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        scripts = os.path.join(base, "capabilities", "skills", "pptx_builder", "scripts")
        if scripts not in sys.path:
            sys.path.insert(0, scripts)
        try:
            from pptx_table import add_table_slide
        except ImportError as e:
            return ToolResult(ok=False, error=f"pptx_table unavailable: {e}")
        target = inputs.get("target_path") or inputs.get("output_path")
        if not target:
            return ToolResult(ok=False, error="target_path/output_path required")
        r = add_table_slide(
            target, inputs.get("headers", []), inputs.get("rows", []),
            lang=inputs.get("lang", "ar"),
            theme_id=inputs.get("theme_id", "academic_navy"),
            title=inputs.get("title", ""), totals=inputs.get("totals"),
            font=inputs.get("font"), output_path=inputs.get("output_path"))
        return ToolResult(ok=r.get("ok", False), data=r if r.get("ok") else None,
                          error=r.get("error"))

    async def _build(self, inputs: dict) -> ToolResult:
        slides = inputs.get("slides", [])
        output = inputs.get("output_path", "./output/result.pptx")
        lang   = inputs.get("lang", "ar")
        title  = inputs.get("title", "")
        subtitle = inputs.get("subtitle", "")
        closing = inputs.get("closing")
        # design request drives theme selection (e.g. "عرض إبداعي" / "formal")
        design_request = inputs.get("design", inputs.get("theme", ""))
        engine = inputs.get("engine", "auto")  # auto | html2pptx | native

        if not slides and not title:
            return ToolResult(ok=False, error="slides or title is required")

        os.makedirs(os.path.dirname(output) or ".", exist_ok=True)

        base = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        skill_scripts = os.path.join(base, "capabilities", "skills",
                                     "pptx_builder", "scripts")
        if skill_scripts not in sys.path:
            sys.path.insert(0, skill_scripts)

        # ── high-fidelity path: themed HTML -> native PPTX (the "Claude way") ──
        if engine in ("auto", "html2pptx", "llm"):
            try:
                from html2pptx_bridge import html_to_pptx
                llm_fn = inputs.get("llm_fn")  # optional callable(prompt)->str

                # If an LLM is provided, let it author the HTML creatively
                # (unbounded layout variety — the fullest "Claude way").
                if llm_fn is not None:
                    vision_fn = inputs.get("vision_fn")  # optional vision LLM
                    # If a vision model is available, run the full generate ->
                    # render -> inspect -> correct loop (the fullest Claude way).
                    if vision_fn is not None:
                        from visual_review_loop import review_and_correct
                        rev = review_and_correct(
                            title=title, slides_content=slides, output_pptx=output,
                            lang=lang, request=design_request, subtitle=subtitle,
                            theme_id=inputs.get("theme_id"),
                            llm_fn=llm_fn, vision_fn=vision_fn,
                            max_rounds=inputs.get("max_rounds", 2))
                        if rev.get("ok"):
                            return ToolResult(ok=True, data={
                                "output_path": output, "engine": "html2pptx",
                                "theme": rev["theme"], "authored_by": rev["authored_by"],
                                "direction": rev["direction"],
                                "review_rounds": rev["rounds"],
                                "final_clean": rev["final_clean"],
                            })
                        return ToolResult(ok=False, error=rev.get("error"))

                    # No vision: LLM authors the HTML creatively (no visual loop).
                    from llm_deck_generator import generate_llm_deck
                    gen = generate_llm_deck(
                        title=title, slides_content=slides, lang=lang,
                        request=design_request, subtitle=subtitle,
                        theme_id=inputs.get("theme_id"), llm_fn=llm_fn)
                    html_str = gen["html"]
                    theme_id = gen["theme"]
                    authored_by = gen["authored_by"]
                else:
                    # deterministic themed template
                    from html_deck_generator import generate_deck_html
                    html_str, theme_id = generate_deck_html(
                        title=title, slides=slides, request=design_request,
                        lang=lang, subtitle=subtitle, closing=closing,
                        custom_color=inputs.get("custom_color"),
                        theme_id=inputs.get("theme_id"),
                        font=inputs.get("font"))
                    authored_by = "template"

                r = html_to_pptx(html_str, output, is_string=True)
                if r.get("ok"):
                    return ToolResult(ok=True, data={
                        "output_path": output, "engine": "html2pptx",
                        "theme": theme_id, "authored_by": authored_by,
                        "direction": "RTL" if lang == "ar" else "LTR",
                    })
                if engine in ("html2pptx", "llm"):
                    return ToolResult(ok=False, error=r.get("error"))
                # otherwise fall through to native builder
            except Exception:
                if engine in ("html2pptx", "llm"):
                    raise
                # fall through

        # ── fallback path: native python-pptx builder (navy/gold) ──
        try:
            from build_pptx import build_deck
            path = build_deck(title=title, slides=slides, subtitle=subtitle,
                              output_path=output, lang=lang, closing=closing)
            return ToolResult(ok=True, data={
                "output_path": path, "engine": "build_deck",
                "direction": "RTL" if lang == "ar" else "LTR",
            })
        except ImportError:
            return ToolResult(ok=False,
                error="python-pptx not available (pip install python-pptx)")

    async def _read(self, inputs: dict) -> ToolResult:
        path = inputs.get("path", "").strip()
        if not path or not os.path.exists(path):
            return ToolResult(ok=False, error=f"file not found: {path}")

        vendored = _vendored_dir()
        if vendored not in sys.path:
            sys.path.insert(0, vendored)
        try:
            from markitdown import MarkItDown
            md = MarkItDown()
            result = md.convert(path)
            return ToolResult(ok=True, data={
                "text": result.text_content, "engine": "markitdown",
            })
        except Exception as e:
            return ToolResult(ok=False, error=f"could not read pptx: {e}")


async def run(inputs: dict) -> ToolResult:
    return await PowerPointTool().run(inputs)
