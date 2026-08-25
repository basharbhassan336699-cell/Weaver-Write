"""
capabilities/tools/tool_web_extract.py
=======================================
Tool 2: clean web text extraction (Trafilatura/UniWeb).
Strips ads and menus, returns the article text only.
"""
from __future__ import annotations
import os, sys
from . import BaseTool, ToolResult

TOOL_SPEC = {
    "name": "web_extract",
    "description": "Clean web page text extraction via Trafilatura.",
    "triggers": ["استخرج من موقع", "محتوى صفحة", "مقال من الإنترنت", "رابط",
                 "web scraping", "web extract", "URL", "article from web"],
    "layers": [2, 4],
}


def _add_uniweb_path():
    base = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    p = os.path.join(base, "engines", "uniweb-core")
    if os.path.isdir(p) and p not in sys.path:
        sys.path.insert(0, p)


class WebExtractTool(BaseTool):
    TOOL_SPEC = TOOL_SPEC

    async def _execute(self, inputs: dict) -> ToolResult:
        url = inputs.get("url", "").strip()
        if not url:
            return ToolResult(ok=False, error="url is required")

        _add_uniweb_path()
        # Trafilatura is integrated into Weaver Write via Direct Code Integration
        try:
            from trafilatura import fetch_url, extract
        except ImportError:
            return ToolResult(ok=False,
                error="Trafilatura not available (pip install trafilatura)")

        downloaded = fetch_url(url)
        if not downloaded:
            return ToolResult(ok=False, error=f"failed to fetch: {url}")

        text = extract(
            downloaded,
            output_format=inputs.get("format", "markdown"),
            include_links=inputs.get("include_links", False),
            include_comments=False,
            include_tables=inputs.get("include_tables", True),
        )
        if not text:
            return ToolResult(ok=False, error="no text extracted from the page")

        return ToolResult(ok=True, data={
            "url": url,
            "text": text,
            "length": len(text),
        })


async def run(inputs: dict) -> ToolResult:
    return await WebExtractTool().run(inputs)
