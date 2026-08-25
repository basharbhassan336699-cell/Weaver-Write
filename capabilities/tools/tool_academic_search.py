"""
capabilities/tools/tool_academic_search.py
============================================
Tool 1: academic search (RAG + page-accurate citations)

Wraps PaperQATool in engines/paperqa-core with the unified BaseTool
interface, making it part of the standard tool registry.
"""

from __future__ import annotations
import os
import sys
from . import BaseTool, ToolResult

TOOL_SPEC = {
    "name": "academic_search",
    "description": "Academic RAG search with page-accurate citations via PaperQA2.",
    "triggers": ["بحث علمي", "مراجع أكاديمية", "دراسات سابقة", "استشهاد", "توثيق", "صفحة",
                 "literature review", "academic search", "references", "citation",
                 "arXiv", "DOI", "Semantic Scholar", "page"],
    "layers": [4, 7],
}


def _add_paperqa_path():
    """Add engines/paperqa-core to sys.path."""
    base = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    for p in [
        os.path.join(base, "engines", "paperqa-core"),
        os.path.join(base, "engines", "paperqa-core", "src"),
    ]:
        if p not in sys.path:
            sys.path.insert(0, p)


class AcademicSearchTool(BaseTool):
    TOOL_SPEC = TOOL_SPEC

    async def _execute(self, inputs: dict) -> ToolResult:
        question = inputs.get("question", "").strip()
        if not question:
            return ToolResult(ok=False, error="question is required")

        sources  = inputs.get("sources", [])
        lang     = inputs.get("lang", "arabic")
        mode     = inputs.get("mode", "cloud")
        verbatim = inputs.get("verbatim", False)
        verify   = inputs.get("verify_text")  # if present -> verify mode (layer 7)

        _add_paperqa_path()
        from paperqa_tool import PaperQATool  # the tool built earlier

        tool = PaperQATool(lang=lang, mode=mode)

        # Verify mode (layer 7)
        if verify:
            r = await tool.verify(text=verify, question=question)
            return ToolResult(ok=r.verified, data={
                "verification_report": r.verification_report,
                "citations": r.citations,
            })

        # Search mode (layer 4)
        r = await tool.run({
            "question": question, "sources": sources, "verbatim": verbatim,
        })
        if r.error:
            return ToolResult(ok=False, error=r.error)
        return ToolResult(ok=True, data={
            "answer": r.answer,
            "references": r.references,
            "citations": r.citations,
            "pages_found": r.pages_found,
            "sources_indexed": r.sources_indexed,
        })


# Unified invocation entry point
async def run(inputs: dict) -> ToolResult:
    return await AcademicSearchTool().run(inputs)
