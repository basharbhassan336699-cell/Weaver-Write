"""
UniWeb CLI — واجهة سطر أوامر موحّدة.

    python -m uniweb fetch https://example.com
    python -m uniweb fetch https://blog.com --clean
    python -m uniweb detect
    python -m uniweb route https://twitter.com/user/status/123
"""

from __future__ import annotations
import argparse
import sys


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="uniweb",
        description="أداة ويب موحّدة (curl-impersonate + autoscraper + firecrawl + browser-use + agent-reach)",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_fetch = sub.add_parser("fetch", help="جلب صفحة")
    p_fetch.add_argument("url")
    p_fetch.add_argument("--clean", action="store_true", help="Markdown نظيف (firecrawl)")
    p_fetch.add_argument("--engine", default=None,
                         choices=["curl_impersonate", "autoscraper", "firecrawl",
                                  "browser_use", "agent_reach"])
    p_fetch.add_argument("--save", default=None)

    sub.add_parser("detect", help="عرض الموارد المتاحة")

    p_route = sub.add_parser("route", help="عرض قرار التوجيه دون تنفيذ")
    p_route.add_argument("url")
    p_route.add_argument("--clean", action="store_true")
    p_route.add_argument("--interact", action="store_true")

    args = parser.parse_args(argv)

    if args.command == "detect":
        return _cmd_detect()
    if args.command == "route":
        return _cmd_route(args)
    if args.command == "fetch":
        return _cmd_fetch(args)


def _cmd_detect():
    from .capabilities import detect_capabilities
    c = detect_capabilities()
    print("الموارد المتاحة:")
    print(f"  curl-impersonate: {'✅' if c.has_curl_impersonate else '❌'}")
    print(f"  firecrawl key:    {'✅' if c.has_firecrawl_key else '❌'}")
    print(f"  متصفح (browser):  {'✅' if c.has_browser else '❌'}")
    print(f"  LLM:              {'✅ ' + (c.llm_provider or '') if c.has_llm else '❌'}")
    return 0


def _cmd_route(args):
    from .capabilities import detect_capabilities
    from .router import route, Task
    c = detect_capabilities()
    task = Task.INTERACT if args.interact else Task.FETCH
    decision = route(
        args.url, c, task=task,
        need_clean_markdown=args.clean,
        need_interaction=args.interact,
    )
    print(f"المحرك المختار: {decision.engine.value}")
    print(f"السبب:         {decision.reason}")
    if decision.fallback:
        print(f"البديل:        {decision.fallback.value}")
    return 0


def _cmd_fetch(args):
    from . import fetch_detailed
    from .router import Task
    result = fetch_detailed(
        args.url, task=Task.FETCH,
        need_clean_markdown=args.clean, engine=args.engine,
    )
    print(f"[المحرك: {result['engine']}] {result['reason']}", file=sys.stderr)
    content = result["content"]
    if args.save:
        from pathlib import Path
        Path(args.save).write_text(str(content), encoding="utf-8")
        print(f"✅ حُفظ في {args.save}", file=sys.stderr)
    else:
        print(content)
    return 0


if __name__ == "__main__":
    sys.exit(main())
