"""
UniMemory MCP Server — مستوحى من OpenMemory MCP.

يعرّض UniMemory كأدوات MCP يستخدمها Claude/الوكلاء مباشرة:
  unimemory_add       — إضافة ذكرى
  unimemory_search    — بحث في الذاكرة
  unimemory_stats     — إحصاءات
  unimemory_distill   — استخلاص دروس من محادثة
  unimemory_consolidate — صيانة (نسيان/ضغط المتلاشي)

التشغيل:
    python -m unimemory.mcp
أو في إعداد Claude:
    { "command": "python", "args": ["-m", "unimemory.mcp"] }
"""

from __future__ import annotations
import asyncio
import json
import os
import sys

try:
    from mcp.server import Server
    from mcp.server.stdio import stdio_server
    from mcp.types import Tool, TextContent
except ImportError:
    Server = None

from .engine import UniMemory


def _get_memory() -> UniMemory:
    """ينشئ محرك ذاكرة من متغيرات البيئة."""
    db = os.environ.get("UNIMEM_DB", "./unimemory.db")
    user = os.environ.get("UNIMEM_USER", "default")
    return UniMemory(db, user_id=user)


async def run_mcp_server():
    if Server is None:
        print("خطأ: حزمة 'mcp' غير مثبتة. ثبّتها: pip install mcp", file=sys.stderr)
        sys.exit(1)

    server = Server("unimemory")
    mem = _get_memory()

    @server.list_tools()
    async def list_tools() -> list:
        return [
            Tool(
                name="unimemory_add",
                description="أضف ذكرى جديدة للذاكرة طويلة المدى (يكتشف النوع ويستخرج الكيانات ويفحص التناقض)",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "content": {"type": "string", "description": "نص الذكرى"},
                        "node": {
                            "type": "string",
                            "enum": ["observe", "plan", "act", "reflect", "emotion"],
                            "default": "observe",
                            "description": "نوع الفعل: observe=حدث, plan=معرفة, act=إجراء, reflect=استنتاج, emotion=تفضيل",
                        },
                        "tags": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["content"],
                },
            ),
            Tool(
                name="unimemory_search",
                description="ابحث في الذاكرة (بحث دلالي + graph + ترتيب بالأهمية بعد التلاشي)",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "نص البحث"},
                        "limit": {"type": "integer", "default": 5},
                        "sector": {
                            "type": "string",
                            "enum": ["episodic", "semantic", "procedural", "reflective", "emotional"],
                            "description": "تقييد البحث بقطاع معيّن (اختياري)",
                        },
                    },
                    "required": ["query"],
                },
            ),
            Tool(
                name="unimemory_stats",
                description="إحصاءات الذاكرة: العدد، التوزيع بالقطاعات، المتلاشي",
                inputSchema={"type": "object", "properties": {}},
            ),
            Tool(
                name="unimemory_distill",
                description="استخلص دروساً دائمة من محادثة وخزّنها (للاستدعاء عند نهاية جلسة)",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "messages": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "role": {"type": "string"},
                                    "content": {"type": "string"},
                                },
                            },
                            "description": "رسائل المحادثة",
                        },
                    },
                    "required": ["messages"],
                },
            ),
            Tool(
                name="unimemory_consolidate",
                description="صيانة الذاكرة: ضغط المتلاشي أو نسيانه (يحاكي النسيان الطبيعي)",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "mode": {
                            "type": "string",
                            "enum": ["compress", "forget"],
                            "default": "compress",
                            "description": "compress=ضغط الجوهر, forget=حذف المتلاشي",
                        },
                    },
                },
            ),
        ]

    @server.call_tool()
    async def call_tool(name: str, arguments: dict) -> list:
        try:
            if name == "unimemory_add":
                m = mem.add(
                    arguments["content"],
                    node=arguments.get("node", "observe"),
                    tags=arguments.get("tags", []),
                )
                result = {
                    "id": m.id, "sector": m.sector.value,
                    "entities": m.entities, "salience": m.salience,
                }

            elif name == "unimemory_search":
                results = mem.search(
                    arguments["query"],
                    limit=arguments.get("limit", 5),
                    sector=arguments.get("sector"),
                )
                result = [
                    {
                        "content": r.content, "sector": r.sector.value,
                        "salience": round(r.current_salience(), 3),
                        "entities": r.entities,
                    }
                    for r in results
                ]

            elif name == "unimemory_stats":
                result = mem.stats()

            elif name == "unimemory_distill":
                lessons = mem.distill_session(arguments["messages"])
                result = {
                    "distilled": len(lessons),
                    "lessons": [{"lesson": l.lesson, "sector": l.sector} for l in lessons],
                }

            elif name == "unimemory_consolidate":
                mode = arguments.get("mode", "compress")
                if mode == "compress":
                    count = mem.compress_faded()
                    result = {"compressed": count}
                else:
                    count = mem.consolidate()
                    result = {"forgotten": count}

            else:
                result = {"error": f"أداة غير معروفة: {name}"}

            return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]

        except Exception as e:
            return [TextContent(type="text", text=json.dumps({"error": str(e)}, ensure_ascii=False))]

    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())


def main():
    asyncio.run(run_mcp_server())


if __name__ == "__main__":
    main()
