"""
capabilities/tools/tool_credibility_check.py
=============================================
Tool 4: assess academic source credibility (PaperQA2 clients).
Journal quality + retraction status + author metadata.
"""
from __future__ import annotations
import os, sys
from . import BaseTool, ToolResult

TOOL_SPEC = {
    "name": "credibility_check",
    "description": "Assess academic source credibility: journal quality, retraction, author.",
    "triggers": ["مصداقية", "جودة المصدر", "مجلة محكمة", "تراجع",
                 "credibility", "source quality", "peer reviewed", "retraction"],
    "layers": [5],
}


def _add_paperqa_path():
    base = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    for p in [os.path.join(base, "engines", "paperqa-core"),
              os.path.join(base, "engines", "paperqa-core", "src")]:
        if p not in sys.path:
            sys.path.insert(0, p)


class CredibilityCheckTool(BaseTool):
    TOOL_SPEC = TOOL_SPEC

    async def _execute(self, inputs: dict) -> ToolResult:
        doi   = inputs.get("doi", "").strip()
        title = inputs.get("title", "").strip()
        if not (doi or title):
            return ToolResult(ok=False, error="doi or title is required")

        _add_paperqa_path()
        score = {"journal_quality": None, "retracted": None, "notes": []}

        # Journal quality check
        try:
            from paperqa.clients.journal_quality import JournalQualityPostProcessor  # noqa
            score["notes"].append("journal_quality available")
        except Exception:
            score["notes"].append("journal_quality not available in this environment")

        # Retraction check
        try:
            from paperqa.clients.retractions import RetractionDataPostProcessor  # noqa
            score["notes"].append("retractions available")
        except Exception:
            score["notes"].append("retractions not available in this environment")

        # Note: real assessment requires PaperQA2 async clients.
        # This scaffold is ready to wire up once the network is enabled.
        return ToolResult(ok=True, data={
            "doi": doi, "title": title,
            "assessment": score,
            "status": "scaffold ready — requires PaperQA2 clients over the network",
        })


async def run(inputs: dict) -> ToolResult:
    return await CredibilityCheckTool().run(inputs)
