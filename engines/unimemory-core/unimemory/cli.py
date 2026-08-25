"""
UniMemory CLI.

    python -m unimemory add "المستخدم يفضل Python"
    python -m unimemory search "اللغة المفضلة"
    python -m unimemory stats
    python -m unimemory consolidate
"""

from __future__ import annotations
import argparse
import json
import sys


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="unimemory",
        description="محرك الذاكرة الموحّد (Zep + Cognee + mem0 + OpenMemory)",
    )
    parser.add_argument("--db", default="./unimemory.db", help="مسار قاعدة البيانات")
    parser.add_argument("--user", default="default", help="معرّف المستخدم")
    sub = parser.add_subparsers(dest="command", required=True)

    p_add = sub.add_parser("add", help="إضافة ذكرى")
    p_add.add_argument("content")
    p_add.add_argument("--node", default="observe",
                       choices=["observe", "plan", "act", "reflect", "emotion"])
    p_add.add_argument("--tags", nargs="*", default=[])

    p_search = sub.add_parser("search", help="بحث في الذاكرة")
    p_search.add_argument("query")
    p_search.add_argument("--limit", type=int, default=5)
    p_search.add_argument("--sector", default=None)
    p_search.add_argument("--no-graph", action="store_true")

    sub.add_parser("stats", help="إحصاءات الذاكرة")

    p_cons = sub.add_parser("consolidate", help="نسيان الذكريات المتلاشية")
    p_cons.add_argument("--threshold", type=float, default=0.1)

    p_all = sub.add_parser("list", help="عرض كل الذكريات")
    p_all.add_argument("--sector", default=None)

    args = parser.parse_args(argv)

    from .engine import UniMemory
    mem = UniMemory(args.db, user_id=args.user)

    if args.command == "add":
        m = mem.add(args.content, node=args.node, tags=args.tags)
        print(f"✅ أُضيفت [{m.sector.value}] id={m.id[:8]}")
        if m.entities:
            print(f"   الكيانات: {', '.join(m.entities)}")

    elif args.command == "search":
        results = mem.search(args.query, limit=args.limit,
                             sector=args.sector, use_graph=not args.no_graph)
        print(f"نتائج البحث عن: {args.query}\n")
        for i, r in enumerate(results, 1):
            print(f"{i}. [{r.sector.value}] أهمية={r.current_salience():.2f}")
            print(f"   {r.content}")
            if r.entities:
                print(f"   كيانات: {', '.join(r.entities)}")
            print()

    elif args.command == "stats":
        print(json.dumps(mem.stats(), ensure_ascii=False, indent=2))

    elif args.command == "consolidate":
        removed = mem.consolidate(threshold=args.threshold)
        print(f"✅ نُسيت {removed} ذكرى متلاشية")

    elif args.command == "list":
        mems = mem.all(sector=args.sector)
        for m in mems:
            print(f"[{m.sector.value}] {m.current_salience():.2f} | {m.content[:60]}")

    mem.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
