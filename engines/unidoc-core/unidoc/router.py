"""
UniDoc Router — يختار المحرك المناسب تلقائياً لكل مستند.

يجمع ثلاثة محركات دون تعديل منطق أي منها:

  ┌─────────────┬──────────────────────────────┬─────────────────┐
  │ المحرك       │ التخصص                        │ المتطلبات        │
  ├─────────────┼──────────────────────────────┼─────────────────┤
  │ anydoc      │ DOCX/PPTX/XLSX/RTF/EPUB/ODF   │ CPU فقط (سريع)  │
  │             │ → Markdown مباشر بلا AI       │                 │
  ├─────────────┼──────────────────────────────┼─────────────────┤
  │ olmocr      │ PDF/صور ممسوحة → Markdown     │ GPU (7B VLM)    │
  │             │ إزالة رؤوس/تذييل، ترتيب طبيعي  │                 │
  ├─────────────┼──────────────────────────────┼─────────────────┤
  │ chandra     │ PDF/صور → HTML/MD/JSON        │ GPU أو remote   │
  │             │ 90+ لغة، جداول، رياضيات، نماذج │ vLLM            │
  └─────────────┴──────────────────────────────┴─────────────────┘

منطق الاختيار:
  1. صيغ Office المهيكلة (docx, pptx…) → anydoc (لا حاجة لـ AI)
  2. PDF/صورة + حاجة لدقة عالية (جداول/رياضيات/متعدد اللغات) → chandra
  3. PDF/صورة + GPU متاح → olmocr
  4. PDF/صورة + لا GPU → fallback إلى chandra remote أو Tesseract
"""

from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional


# ── الصيغ المدعومة لكل محرك ────────────────────────────────

OFFICE_FORMATS = {
    ".doc", ".docx", ".ppt", ".pptx", ".xls", ".xlsx",
    ".rtf", ".epub", ".odt", ".ods", ".odp", ".csv",
}

IMAGE_PDF_FORMATS = {
    ".pdf", ".png", ".jpg", ".jpeg", ".gif", ".webp", ".tiff", ".bmp",
}


class Engine(str, Enum):
    ANYDOC = "anydoc"
    OLMOCR = "olmocr"
    CHANDRA = "chandra"
    TESSERACT = "tesseract"


class OutputFormat(str, Enum):
    MARKDOWN = "markdown"
    HTML = "html"
    JSON = "json"


@dataclass
class RouteDecision:
    """قرار التوجيه — أي محرك ولماذا."""
    engine: Engine
    reason: str
    output_formats: list[OutputFormat] = field(default_factory=list)
    requires_gpu: bool = False
    fallback: Optional[Engine] = None


@dataclass
class DeviceCapabilities:
    """قدرات الجهاز الحالي."""
    has_gpu: bool = False
    has_vllm_remote: bool = False   # خادم vLLM بعيد متاح
    remote_url: Optional[str] = None
    allow_tesseract: bool = True    # fallback للأجهزة الصغيرة (Termux)


def _needs_high_fidelity(
    need_tables: bool,
    need_math: bool,
    need_multilingual: bool,
    need_forms: bool,
    need_json: bool,
) -> bool:
    """هل المستند يحتاج دقة chandra العالية؟"""
    return any([need_tables, need_math, need_multilingual, need_forms, need_json])


def route(
    filepath: str | Path,
    device: DeviceCapabilities,
    *,
    need_tables: bool = False,
    need_math: bool = False,
    need_multilingual: bool = False,
    need_forms: bool = False,
    output: OutputFormat = OutputFormat.MARKDOWN,
    prefer_engine: Optional[Engine] = None,
) -> RouteDecision:
    """
    يقرر المحرك المناسب لمستند معيّن.

    Args:
        filepath: مسار المستند
        device: قدرات الجهاز
        need_tables/math/multilingual/forms: متطلبات الدقة
        output: صيغة الإخراج المطلوبة
        prefer_engine: إجبار محرك محدد (يتجاوز المنطق التلقائي)

    Returns:
        RouteDecision يحوي المحرك المختار والسبب
    """
    ext = Path(filepath).suffix.lower()
    need_json = output == OutputFormat.JSON
    need_html = output == OutputFormat.HTML

    # ── تجاوز يدوي ──
    if prefer_engine is not None:
        return RouteDecision(
            engine=prefer_engine,
            reason=f"محرك محدد يدوياً: {prefer_engine.value}",
            output_formats=[output],
            requires_gpu=prefer_engine in (Engine.OLMOCR, Engine.CHANDRA) and not device.has_vllm_remote,
        )

    # ── ١. صيغ Office المهيكلة → anydoc (لا AI، CPU فقط) ──
    if ext in OFFICE_FORMATS:
        return RouteDecision(
            engine=Engine.ANYDOC,
            reason=f"صيغة Office مهيكلة ({ext}) — anydoc يقرأها مباشرة بلا AI",
            output_formats=[OutputFormat.MARKDOWN],
            requires_gpu=False,
        )

    # ── ٢. PDF/صور → محرك OCR ──
    if ext in IMAGE_PDF_FORMATS:
        high_fidelity = _needs_high_fidelity(
            need_tables, need_math, need_multilingual, need_forms, need_json
        )

        # HTML أو JSON → chandra فقط (olmocr يُخرج Markdown فقط)
        if need_html or need_json:
            return _chandra_decision(device, output,
                reason=f"إخراج {output.value} مطلوب — chandra يدعمه (olmocr لا)")

        # دقة عالية → chandra
        if high_fidelity:
            reasons = []
            if need_tables: reasons.append("جداول")
            if need_math: reasons.append("رياضيات")
            if need_multilingual: reasons.append("متعدد اللغات 90+")
            if need_forms: reasons.append("نماذج/checkboxes")
            return _chandra_decision(device, output,
                reason=f"دقة عالية مطلوبة ({'، '.join(reasons)}) — chandra متخصص")

        # نص عادي + GPU → olmocr (أرخص، $200/مليون صفحة)
        if device.has_gpu:
            return RouteDecision(
                engine=Engine.OLMOCR,
                reason="PDF/صورة نصية + GPU متاح — olmocr اقتصادي وسريع",
                output_formats=[OutputFormat.MARKDOWN],
                requires_gpu=True,
                fallback=Engine.CHANDRA,
            )

        # لا GPU → chandra remote أو Tesseract
        return _no_gpu_decision(device, output)

    # ── صيغة غير مدعومة ──
    raise ValueError(
        f"صيغة غير مدعومة: {ext}. "
        f"المدعوم: {sorted(OFFICE_FORMATS | IMAGE_PDF_FORMATS)}"
    )


def _chandra_decision(
    device: DeviceCapabilities,
    output: OutputFormat,
    reason: str,
) -> RouteDecision:
    """قرار chandra مع مراعاة GPU/remote."""
    if device.has_gpu:
        return RouteDecision(
            engine=Engine.CHANDRA, reason=reason + " (محلي HF)",
            output_formats=[output], requires_gpu=True,
        )
    if device.has_vllm_remote:
        return RouteDecision(
            engine=Engine.CHANDRA, reason=reason + " (خادم vLLM بعيد)",
            output_formats=[output], requires_gpu=False,
        )
    # chandra يحتاج GPU أو remote — لا بديل لـ HTML/JSON
    if output in (OutputFormat.HTML, OutputFormat.JSON):
        raise RuntimeError(
            f"إخراج {output.value} يحتاج chandra، لكن لا GPU ولا خادم بعيد متاح. "
            "شغّل خادم vLLM أو فعّل GPU."
        )
    return _no_gpu_decision(device, output)


def _no_gpu_decision(
    device: DeviceCapabilities,
    output: OutputFormat,
) -> RouteDecision:
    """لا GPU متاح — Tesseract fallback للأجهزة الصغيرة."""
    if device.has_vllm_remote:
        return RouteDecision(
            engine=Engine.CHANDRA,
            reason="لا GPU محلي — استخدام خادم vLLM البعيد",
            output_formats=[output], requires_gpu=False,
        )
    if device.allow_tesseract:
        return RouteDecision(
            engine=Engine.TESSERACT,
            reason="لا GPU ولا خادم — Tesseract OCR fallback (Termux/CPU)",
            output_formats=[OutputFormat.MARKDOWN], requires_gpu=False,
        )
    raise RuntimeError(
        "لا GPU، لا خادم بعيد، وTesseract معطّل. "
        "فعّل أحدها لمعالجة PDF/الصور."
    )
