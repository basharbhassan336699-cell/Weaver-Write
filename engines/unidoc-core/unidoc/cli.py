"""
UniDoc CLI — واجهة سطر أوامر موحّدة.

الاستخدام:
    python -m unidoc convert report.docx
    python -m unidoc convert scan.pdf --output html --need-tables
    python -m unidoc convert form.pdf --engine chandra --need-forms
    python -m unidoc detect                 # عرض قدرات الجهاز
    python -m unidoc route scan.pdf         # عرض قرار التوجيه دون تنفيذ
"""

from __future__ import annotations
import argparse
import sys
from pathlib import Path


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="unidoc",
        description="أداة موحّدة لتحويل المستندات (anydoc + olmocr + chandra)",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # ── convert ──
    p_conv = sub.add_parser("convert", help="تحويل مستند")
    p_conv.add_argument("filepath", help="مسار المستند")
    p_conv.add_argument("-o", "--output", default="markdown",
                        choices=["markdown", "html", "json"])
    p_conv.add_argument("--engine", default=None,
                        choices=["anydoc", "olmocr", "chandra", "tesseract"],
                        help="إجبار محرك محدد")
    p_conv.add_argument("--need-tables", action="store_true")
    p_conv.add_argument("--need-math", action="store_true")
    p_conv.add_argument("--need-multilingual", action="store_true")
    p_conv.add_argument("--need-forms", action="store_true")
    p_conv.add_argument("--save", default=None, help="حفظ الناتج في ملف")

    # ── detect ──
    sub.add_parser("detect", help="عرض قدرات الجهاز")

    # ── route ──
    p_route = sub.add_parser("route", help="عرض قرار التوجيه دون تنفيذ")
    p_route.add_argument("filepath")
    p_route.add_argument("-o", "--output", default="markdown",
                         choices=["markdown", "html", "json"])
    p_route.add_argument("--need-tables", action="store_true")
    p_route.add_argument("--need-math", action="store_true")
    p_route.add_argument("--need-multilingual", action="store_true")
    p_route.add_argument("--need-forms", action="store_true")

    args = parser.parse_args(argv)

    if args.command == "detect":
        return _cmd_detect()
    if args.command == "route":
        return _cmd_route(args)
    if args.command == "convert":
        return _cmd_convert(args)


def _cmd_detect():
    from .device import detect_device
    dev = detect_device()
    print("قدرات الجهاز:")
    print(f"  GPU:            {'✅' if dev.has_gpu else '❌'}")
    print(f"  خادم vLLM بعيد: {'✅ ' + (dev.remote_url or '') if dev.has_vllm_remote else '❌'}")
    print(f"  Tesseract:      {'✅' if dev.allow_tesseract else '❌'}")
    return 0


def _cmd_route(args):
    from .device import detect_device
    from .router import route, OutputFormat
    dev = detect_device()
    decision = route(
        args.filepath, dev,
        need_tables=args.need_tables, need_math=args.need_math,
        need_multilingual=args.need_multilingual, need_forms=args.need_forms,
        output=OutputFormat(args.output),
    )
    print(f"المحرك المختار: {decision.engine.value}")
    print(f"السبب:         {decision.reason}")
    print(f"يحتاج GPU:      {'نعم' if decision.requires_gpu else 'لا'}")
    if decision.fallback:
        print(f"البديل:        {decision.fallback.value}")
    return 0


def _cmd_convert(args):
    from . import convert_detailed
    result = convert_detailed(
        args.filepath, output=args.output, engine=args.engine,
        need_tables=args.need_tables, need_math=args.need_math,
        need_multilingual=args.need_multilingual, need_forms=args.need_forms,
    )
    print(f"[المحرك: {result['engine']}] {result['reason']}", file=sys.stderr)

    if args.save:
        Path(args.save).write_text(result["content"], encoding="utf-8")
        print(f"✅ حُفظ في {args.save}", file=sys.stderr)
    else:
        print(result["content"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
