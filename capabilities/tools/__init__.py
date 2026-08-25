"""
capabilities/tools/ — Layer 1: programmed tools
===============================================
Each tool inherits BaseTool and provides:
  - TOOL_SPEC   : name, description, triggers, layers
  - run(inputs) : the single unified invocation interface

This mirrors Claude's tools (web_search, bash_tool...), each with a
name, a description, and a unified invocation interface.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional, Any


@dataclass
class ToolResult:
    """Unified result for every tool."""
    ok: bool = True
    data: dict = field(default_factory=dict)
    error: Optional[str] = None
    tool_name: str = ""

    def to_dict(self) -> dict:
        return {"ok": self.ok, "data": self.data,
                "error": self.error, "tool_name": self.tool_name}


class BaseTool:
    """
    Base for every tool. Enforces a unified run() interface.

    Each subclass sets TOOL_SPEC and implements _execute().
    """

    TOOL_SPEC: dict = {}

    @property
    def name(self) -> str:
        return self.TOOL_SPEC.get("name", self.__class__.__name__)

    async def run(self, inputs: dict) -> ToolResult:
        """Unified interface — wraps _execute with error handling."""
        try:
            result = await self._execute(inputs)
            if isinstance(result, ToolResult):
                result.tool_name = self.name
                return result
            return ToolResult(ok=True, data=result or {}, tool_name=self.name)
        except ImportError as e:
            return ToolResult(ok=False, error=f"Missing library: {e}", tool_name=self.name)
        except Exception as e:
            return ToolResult(ok=False, error=str(e), tool_name=self.name)

    async def _execute(self, inputs: dict) -> Any:
        raise NotImplementedError(f"{self.name} did not implement _execute")


__all__ = ["BaseTool", "ToolResult"]
