"""
core/context/__init__.py
========================
context-mode مدمجة كنافذة سياق واسعة.
"""

from __future__ import annotations
import sys, os

CONTEXT_PATH = os.path.join(os.path.dirname(__file__), "../../engines/context-mode-core")
if CONTEXT_PATH not in sys.path:
    sys.path.insert(0, CONTEXT_PATH)


class ContextWindow:
    """
    نافذة السياق الواسعة لـ Weaver Write.

    بدلاً من حشو كل الأوراق في context النموذج،
    تُفهرس هنا وتُسترجع فقط ما يُحتاج.

    يوفّر 98% من الـ context للصياغة الفعلية.
    """

    def __init__(self, server_url: str = "http://localhost:8765"):
        self.server_url = server_url

    async def index(self, content: str, label: str, task_id: str = None) -> dict:
        """يفهرس محتوى في السياق."""
        return await self._call("ctx_index", {
            "content": content,
            "label": label,
            "metadata": {"task_id": task_id} if task_id else {}
        })

    async def search(self, query: str, limit: int = 5, task_id: str = None) -> list:
        """يبحث في المحتوى المفهرس."""
        params = {"query": query, "limit": limit}
        if task_id:
            params["filter"] = {"task_id": task_id}
        return await self._call("ctx_search", params)

    async def fetch_and_index(self, url: str, label: str, task_id: str = None) -> dict:
        """يجلب URL ويفهرسه."""
        return await self._call("ctx_fetch_and_index", {
            "url": url, "label": label
        })

    async def execute(self, language: str, code: str) -> dict:
        """ينفّذ كوداً في sandbox context-mode."""
        return await self._call("ctx_execute", {"language": language, "code": code})

    async def stats(self) -> dict:
        """إحصاءات استخدام السياق."""
        return await self._call("ctx_stats", {})

    async def _call(self, tool: str, params: dict) -> dict:
        """استدعاء MCP tool عبر HTTP."""
        import urllib.request, json
        try:
            data = json.dumps({"tool": tool, "params": params}).encode()
            req = urllib.request.Request(
                f"{self.server_url}/tool",
                data=data,
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read())
        except Exception:
            # Fallback: رسالة إن لم يعمل server
            return {"error": f"context-mode server غير متاح على {self.server_url}"}
