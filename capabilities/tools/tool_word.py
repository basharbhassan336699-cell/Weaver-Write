"""
capabilities/tools/tool_word.py
================================
Tool 7: Word document operations.

Build:  via the `docx` JavaScript library (vendored) or python-docx.
Read:   via markitdown / pandoc / mammoth.

This complements the docx_builder skill: the skill holds the writing
know-how; this tool is the programmatic build/read interface.
"""
from __future__ import annotations
import os
import sys
import subprocess
import json
import tempfile
from . import BaseTool, ToolResult

TOOL_SPEC = {
    "name": "word",
    "description": "Build or read Word (.docx) files with RTL support. Build via docx/python-docx, read via markitdown/pandoc.",
    "triggers": ["Word", "DOCX", "مستند وورد", "ملف Word", "اقرأ وورد",
                 "word document", "read docx", "build docx"],
    "layers": [8],
}


def _vendored_dir():
    base = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.join(base, "engines", "office-core", "vendored")


class WordTool(BaseTool):
    TOOL_SPEC = TOOL_SPEC

    async def _execute(self, inputs: dict) -> ToolResult:
        action = inputs.get("action", "build")  # build | read

        if action == "read":
            return await self._read(inputs)
        return await self._build(inputs)

    # ── build ────────────────────────────────────────────────
    async def _build(self, inputs: dict) -> ToolResult:
        title      = inputs.get("title", "")
        sections   = inputs.get("sections", [])
        references = inputs.get("references", [])
        output     = inputs.get("output_path", "./output/result.docx")
        lang       = inputs.get("lang", "ar")

        os.makedirs(os.path.dirname(output) or ".", exist_ok=True)

        base = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        skill_scripts = os.path.join(base, "capabilities", "skills",
                                     "docx_builder", "scripts")
        if skill_scripts not in sys.path:
            sys.path.insert(0, skill_scripts)

        # rich mode: tables, images, TOC, header/footer, columns, colored headings
        # auto-detected when any section has a table/image, or explicitly requested
        wants_rich = (inputs.get("rich")
                      or inputs.get("toc") or inputs.get("header_text")
                      or inputs.get("two_columns")
                      or any(s.get("table") or s.get("image") for s in sections))
        if wants_rich:
            try:
                from docx_advanced import build_rich_docx
                path = build_rich_docx(
                    title, sections, output_path=output, lang=lang,
                    theme_id=inputs.get("theme_id", "academic_navy"),
                    font=inputs.get("font"), subtitle=inputs.get("subtitle", ""),
                    references=references, header_text=inputs.get("header_text"),
                    page_numbers=inputs.get("page_numbers", True),
                    toc=inputs.get("toc", False),
                    two_columns=inputs.get("two_columns", False))
                return ToolResult(ok=True, data={
                    "output_path": path, "engine": "docx_advanced",
                    "direction": "RTL" if lang == "ar" else "LTR"})
            except ImportError:
                pass  # fall back to the basic builder

        # basic mode: python-docx (works in Termux); reuse the skill's builder
        try:
            from build_docx import build_academic_docx
            path = build_academic_docx(title, sections, references, output, lang,
                                       font=inputs.get("font"),
                                       heading_size=inputs.get("heading_size", 16),
                                       body_size=inputs.get("body_size", 14))
            return ToolResult(ok=True, data={"output_path": path, "engine": "python-docx",
                                             "direction": "RTL" if lang == "ar" else "LTR"})
        except ImportError:
            return ToolResult(ok=False,
                error="python-docx not available (pip install python-docx)")

    # ── read ─────────────────────────────────────────────────
    async def _read(self, inputs: dict) -> ToolResult:
        path = inputs.get("path", "").strip()
        if not path or not os.path.exists(path):
            return ToolResult(ok=False, error=f"file not found: {path}")

        vendored = _vendored_dir()
        if vendored not in sys.path:
            sys.path.insert(0, vendored)

        # Try office-oxide first (Rust core, up to 100x faster)
        try:
            import office_oxide
            text = office_oxide.extract_text(path)
            return ToolResult(ok=True, data={"text": text, "engine": "office-oxide"})
        except Exception:
            pass

        # Try markitdown (vendored) → clean markdown
        try:
            from markitdown import MarkItDown
            md = MarkItDown()
            result = md.convert(path)
            return ToolResult(ok=True, data={
                "text": result.text_content, "engine": "markitdown",
            })
        except Exception:
            pass

        # Fallback: mammoth
        try:
            import mammoth
            with open(path, "rb") as f:
                r = mammoth.extract_raw_text(f)
            return ToolResult(ok=True, data={"text": r.value, "engine": "mammoth"})
        except ImportError:
            return ToolResult(ok=False, error="no Word reader available")


async def run(inputs: dict) -> ToolResult:
    return await WordTool().run(inputs)
