"""
capabilities/tools/tool_mcp_connector.py
=========================================
Tool 13: connect to bundled MCP servers (filesystem, git, time).

These extend the pipeline with capabilities it lacked:
  - filesystem : sandboxed file operations for a task workspace
  - git        : version a research project / track document revisions
  - time       : timezone-aware timestamps for citations and logs

Duplicate MCP servers were intentionally NOT bundled:
  - memory  -> already covered by unimemory-core
  - sequentialthinking -> already covered by extended-thinking-hub
  - fetch   -> already covered by web_extract / uniweb-core

The servers live in engines/open-connector-core/mcp-servers/ and are
launched on demand. This tool is a thin dispatcher over them.
"""
from __future__ import annotations
import os
from . import BaseTool, ToolResult

TOOL_SPEC = {
    "name": "mcp_connector",
    "description": "Access bundled MCP servers: filesystem (sandboxed files), git (versioning), time (timezone timestamps).",
    "triggers": ["ملفات المهمة", "نظام الملفات", "git", "إصدارات", "الوقت", "توقيت",
                 "filesystem", "version control", "commit", "time", "timestamp"],
    "layers": [0, 1, 8],
}

AVAILABLE_SERVERS = {
    "filesystem": "sandboxed file operations for the task workspace",
    "git": "version a research project / track document revisions",
    "time": "timezone-aware timestamps",
}


def _servers_dir():
    base = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.join(base, "engines", "open-connector-core", "mcp-servers")


class McpConnectorTool(BaseTool):
    TOOL_SPEC = TOOL_SPEC

    async def _execute(self, inputs: dict) -> ToolResult:
        server = inputs.get("server", "").strip()
        if not server:
            return ToolResult(ok=True, data={
                "available_servers": AVAILABLE_SERVERS,
                "note": "pass server= to use one",
            })

        if server not in AVAILABLE_SERVERS:
            return ToolResult(ok=False,
                error=f"unknown server '{server}'. Available: {list(AVAILABLE_SERVERS)}")

        server_path = os.path.join(_servers_dir(), server)
        if not os.path.isdir(server_path):
            return ToolResult(ok=False, error=f"server not found on disk: {server_path}")

        # This tool registers the server path; actual MCP invocation runs
        # through open-connector-core's client at pipeline runtime.
        return ToolResult(ok=True, data={
            "server": server,
            "path": server_path,
            "purpose": AVAILABLE_SERVERS[server],
            "action": inputs.get("action", ""),
            "params": inputs.get("params", {}),
            "note": "server resolved — invoked via open-connector-core MCP client",
        })


async def run(inputs: dict) -> ToolResult:
    return await McpConnectorTool().run(inputs)
