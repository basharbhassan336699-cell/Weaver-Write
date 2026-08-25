"""
capabilities/tools/tool_web_search.py
======================================
Tool 11: web search via a SearXNG meta-search instance.

Unlike web_extract (which pulls text from ONE known URL), this tool
discovers sources by querying many engines at once through a SearXNG
instance and returns ranked results — the real search entry point the
research pipeline was missing.

SearXNG runs as an HTTP service (self-hosted or public instance); this
tool is a thin client, so nothing heavy is vendored.
"""
from __future__ import annotations
import os
import json
import urllib.parse
import urllib.request
from . import BaseTool, ToolResult

TOOL_SPEC = {
    "name": "web_search",
    "description": "Search the web via a SearXNG meta-search instance; returns ranked results from many engines. Discovers sources (vs web_extract which reads one URL).",
    "triggers": ["ابحث في الإنترنت", "بحث ويب", "ابحث عن", "مصادر عن",
                 "web search", "search the web", "find sources", "look up"],
    "layers": [4],
}

# Default instance — override via WEAVER_SEARXNG_URL
DEFAULT_INSTANCE = os.environ.get("WEAVER_SEARXNG_URL", "http://127.0.0.1:8888")


class WebSearchTool(BaseTool):
    TOOL_SPEC = TOOL_SPEC

    async def _execute(self, inputs: dict) -> ToolResult:
        query = inputs.get("query", "").strip()
        if not query:
            return ToolResult(ok=False, error="query is required")

        instance = inputs.get("instance", DEFAULT_INSTANCE).rstrip("/")
        categories = inputs.get("categories", "general")  # general|science|news
        language = inputs.get("language", "")             # e.g. ar, en
        limit = int(inputs.get("limit", 10))

        params = {"q": query, "format": "json", "categories": categories}
        if language:
            params["language"] = language
        url = f"{instance}/search?" + urllib.parse.urlencode(params)

        try:
            req = urllib.request.Request(url, headers={"User-Agent": "WeaverWrite/1.0"})
            with urllib.request.urlopen(req, timeout=inputs.get("timeout", 20)) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            return ToolResult(ok=False,
                error=f"SearXNG request failed ({instance}): {e}. "
                      "Set WEAVER_SEARXNG_URL or pass instance=.")

        results = []
        for r in data.get("results", [])[:limit]:
            results.append({
                "title": r.get("title", ""),
                "url": r.get("url", ""),
                "content": r.get("content", ""),
                "engine": r.get("engine", ""),
                "score": r.get("score", 0),
            })

        return ToolResult(ok=True, data={
            "query": query,
            "results": results,
            "count": len(results),
            "engine": "searxng",
        })


async def run(inputs: dict) -> ToolResult:
    return await WebSearchTool().run(inputs)
