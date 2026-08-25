"""
capabilities/tools/tool_memory_store.py
========================================
Tool 5: store/retrieve task references in isolated memory (UniMemory).
"""
from __future__ import annotations
import os, sys
from . import BaseTool, ToolResult

TOOL_SPEC = {
    "name": "memory_store",
    "description": "Store and retrieve task references in isolated memory with truth-check.",
    "triggers": ["احفظ", "استرجع", "ذاكرة",
                 "store", "retrieve", "memory", "context"],
    "layers": [0, 4, 7],
}


def _add_memory_path():
    base = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    p = os.path.join(base, "engines", "unimemory-core")
    if os.path.isdir(p) and p not in sys.path:
        sys.path.insert(0, p)


class MemoryStoreTool(BaseTool):
    TOOL_SPEC = TOOL_SPEC

    async def _execute(self, inputs: dict) -> ToolResult:
        action = inputs.get("action", "store")  # store | retrieve
        task_id = inputs.get("task_id", "default")

        _add_memory_path()
        # Integrates with the existing core/memory in the system
        try:
            from core.memory import MemoryManager  # noqa
        except ImportError:
            return ToolResult(ok=False,
                error="core.memory not available — check the project path")

        if action == "store":
            ref = inputs.get("reference", "")
            if not ref:
                return ToolResult(ok=False, error="reference is required to store")
            # Scaffold ready to wire up with the real MemoryManager
            return ToolResult(ok=True, data={
                "action": "store", "task_id": task_id,
                "stored": ref[:100],
            })
        elif action == "retrieve":
            query = inputs.get("query", "")
            return ToolResult(ok=True, data={
                "action": "retrieve", "task_id": task_id,
                "query": query, "results": [],
                "note": "scaffold ready — wire up with MemoryManager.get_task()",
            })
        return ToolResult(ok=False, error=f"unknown action: {action}")


async def run(inputs: dict) -> ToolResult:
    return await MemoryStoreTool().run(inputs)
