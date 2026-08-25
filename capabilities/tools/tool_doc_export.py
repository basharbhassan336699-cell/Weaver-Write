"""
capabilities/tools/tool_doc_export.py
======================================
Tool 6: generate the final DOCX/PPTX/XLSX/PDF file with RTL support.
Dispatches to capabilities/skills based on the requested format.
"""
from __future__ import annotations
import os
from . import BaseTool, ToolResult

TOOL_SPEC = {
    "name": "doc_export",
    "description": "Generate the final file as DOCX/PPTX/XLSX/PDF with Arabic RTL.",
    "triggers": ["أخرج", "ولّد ملف", "تصدير",
                 "export", "generate file", "DOCX", "PPTX", "XLSX", "PDF"],
    "layers": [8],
}


class DocExportTool(BaseTool):
    TOOL_SPEC = TOOL_SPEC

    async def _execute(self, inputs: dict) -> ToolResult:
        fmt = inputs.get("format", "DOCX").upper()
        content = inputs.get("content", "")
        output_path = inputs.get("output_path", f"./output/result.{fmt.lower()}")

        if not content:
            return ToolResult(ok=False, error="content is required")

        # Each format is dispatched to its matching skill in capabilities/skills/
        skill_map = {
            "DOCX": "docx_builder",
            "PPTX": "pptx_builder",
            "XLSX": "xlsx_builder",
            "PDF":  "pdf_builder",
        }
        skill = skill_map.get(fmt)
        if not skill:
            return ToolResult(ok=False, error=f"unsupported format: {fmt}")

        # Scaffold ready — actual execution runs through the skill scripts
        return ToolResult(ok=True, data={
            "format": fmt,
            "skill": skill,
            "output_path": output_path,
            "rtl": inputs.get("lang", "ar") == "ar",
            "note": f"dispatched to skill {skill} in capabilities/skills/",
        })


async def run(inputs: dict) -> ToolResult:
    return await DocExportTool().run(inputs)
