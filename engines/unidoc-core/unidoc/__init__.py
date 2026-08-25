"""
UniDoc — أداة موحّدة لتحويل أي مستند إلى نص/Markdown/HTML/JSON.

تجمع ثلاثة محركات دون تعديل منطق أي منها:
  • anydoc  — Office المهيكل (DOCX, PPTX, XLSX, RTF, EPUB, ODF) بلا AI
  • olmocr  — PDF/صور ممسوحة عبر VLM (GPU)، اقتصادي
  • chandra — PDF/صور بدقة عالية: 90+ لغة، جداول، رياضيات، نماذج

الاستخدام الأبسط:
    import unidoc
    md = unidoc.convert("report.docx")           # يختار anydoc تلقائياً
    md = unidoc.convert("scan.pdf")              # يختار olmocr/chandra حسب الجهاز
    html = unidoc.convert("form.pdf", output="html", need_forms=True)  # chandra
"""

from __future__ import annotations
from pathlib import Path
from typing import Optional

from .router import (
    route,
    Engine,
    OutputFormat,
    DeviceCapabilities,
    RouteDecision,
)
from .device import detect_device
from .engines import run_engine

__version__ = "1.0.0"

__all__ = [
    "convert",
    "convert_detailed",
    "route",
    "detect_device",
    "Engine",
    "OutputFormat",
    "DeviceCapabilities",
    "RouteDecision",
]


def convert(
    filepath: str | Path,
    *,
    output: str = "markdown",
    need_tables: bool = False,
    need_math: bool = False,
    need_multilingual: bool = False,
    need_forms: bool = False,
    engine: Optional[str] = None,
    device: Optional[DeviceCapabilities] = None,
    **engine_kwargs,
) -> str:
    """
    تحويل مستند إلى نص. الواجهة الرئيسية.

    Args:
        filepath: مسار المستند
        output: "markdown" | "html" | "json"
        need_tables: المستند يحوي جداول مهمة → chandra
        need_math: معادلات رياضية → chandra
        need_multilingual: لغات متعددة (90+) → chandra
        need_forms: نماذج/checkboxes → chandra
        engine: إجبار محرك "anydoc"|"olmocr"|"chandra"|"tesseract"
        device: قدرات الجهاز (تُكتشف تلقائياً إن لم تُحدَّد)

    Returns:
        النص المحوّل بالصيغة المطلوبة
    """
    result = convert_detailed(
        filepath, output=output,
        need_tables=need_tables, need_math=need_math,
        need_multilingual=need_multilingual, need_forms=need_forms,
        engine=engine, device=device, **engine_kwargs,
    )
    return result["content"]


def convert_detailed(
    filepath: str | Path,
    *,
    output: str = "markdown",
    need_tables: bool = False,
    need_math: bool = False,
    need_multilingual: bool = False,
    need_forms: bool = False,
    engine: Optional[str] = None,
    device: Optional[DeviceCapabilities] = None,
    **engine_kwargs,
) -> dict:
    """
    مثل convert لكن يُعيد تفاصيل كاملة:
      { content, engine, reason, output_format, assets }
    """
    dev = device or detect_device()
    out_fmt = OutputFormat(output)
    prefer = Engine(engine) if engine else None

    decision = route(
        filepath, dev,
        need_tables=need_tables, need_math=need_math,
        need_multilingual=need_multilingual, need_forms=need_forms,
        output=out_fmt, prefer_engine=prefer,
    )

    content, assets = run_engine(
        decision.engine, filepath, out_fmt, dev, **engine_kwargs
    )

    return {
        "content": content,
        "engine": decision.engine.value,
        "reason": decision.reason,
        "output_format": out_fmt.value,
        "assets": assets,
    }
