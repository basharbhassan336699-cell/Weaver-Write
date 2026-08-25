"""
طبقة المحركات — تستدعي كل أداة أصلية دون تعديل منطقها.

كل دالة هنا مجرد "غلاف" (adapter) يترجم واجهة UniDoc الموحّدة
إلى استدعاء الأداة الأصلية كما هي.
"""

from __future__ import annotations
from pathlib import Path
from typing import Optional

from .router import Engine, OutputFormat, DeviceCapabilities


def run_engine(
    engine: Engine,
    filepath: str | Path,
    output: OutputFormat,
    device: DeviceCapabilities,
    **kwargs,
) -> tuple[str, list]:
    """
    يشغّل المحرك المختار ويُعيد (المحتوى، الأصول/الصور).
    """
    filepath = str(filepath)

    if engine == Engine.ANYDOC:
        return _run_anydoc(filepath, output, **kwargs)
    if engine == Engine.OLMOCR:
        return _run_olmocr(filepath, output, device, **kwargs)
    if engine == Engine.CHANDRA:
        return _run_chandra(filepath, output, device, **kwargs)
    if engine == Engine.TESSERACT:
        return _run_tesseract(filepath, output, **kwargs)

    raise ValueError(f"محرك غير معروف: {engine}")


# ─────────────────────────────────────────────────────────
# anydoc — Office المهيكل (بلا تعديل منطق)
# ─────────────────────────────────────────────────────────

def _run_anydoc(filepath: str, output: OutputFormat, **kwargs) -> tuple[str, list]:
    """
    يستدعي anydoc.to_markdown كما هو.
    الكود الأصلي في engines_src_anydoc/ — لا يُعدَّل.
    """
    try:
        import anydoc  # الحزمة الأصلية (pip install firecrawl-anydoc)
    except ImportError:
        raise ImportError(
            "anydoc غير مثبت. ثبّته: pip install firecrawl-anydoc\n"
            "أو ابنه من engines_src_anydoc/ عبر maturin."
        )

    md = anydoc.to_markdown(filepath)

    # anydoc يُخرج Markdown فقط
    if output != OutputFormat.MARKDOWN:
        raise ValueError(
            f"anydoc يدعم Markdown فقط، طُلب {output.value}. "
            "استخدم chandra لـ HTML/JSON."
        )

    # استخراج الأصول إن وُجدت
    assets = []
    try:
        with open(filepath, "rb") as f:
            data = f.read()
        ext = Path(filepath).suffix.lower().lstrip(".")
        doc = anydoc.to_document(data, format=ext)
        assets = list(getattr(doc, "assets", []))
    except Exception:
        pass  # الأصول اختيارية

    return md, assets


# ─────────────────────────────────────────────────────────
# olmocr — PDF/صور عبر VLM (بلا تعديل منطق)
# ─────────────────────────────────────────────────────────

def _run_olmocr(
    filepath: str,
    output: OutputFormat,
    device: DeviceCapabilities,
    **kwargs,
) -> tuple[str, list]:
    """
    يستدعي olmocr pipeline كما هو.
    الكود الأصلي في engines_src_olmocr/olmocr/ — لا يُعدَّل.
    """
    if output != OutputFormat.MARKDOWN:
        raise ValueError(
            f"olmocr يدعم Markdown فقط، طُلب {output.value}. استخدم chandra."
        )

    try:
        # نستخدم دوال olmocr الأصلية للعرض والـ anchor
        from olmocr.data.renderpdf import render_pdf_to_base64png
        from olmocr.prompts.anchor import get_anchor_text
    except ImportError:
        raise ImportError(
            "olmocr غير مثبت. ثبّته من engines_src_olmocr/:\n"
            "  pip install -e engines_src_olmocr/[gpu]\n"
            "يتطلب GPU + vllm."
        )

    # olmocr يعمل عبر pipeline كامل مع خادم vLLM
    # هنا نستدعي الـ pipeline الأصلي دون تعديل
    from olmocr.pipeline import build_page_query  # noqa

    # ملاحظة: التشغيل الفعلي يتم عبر:
    #   python -m olmocr.pipeline <workspace> --pdfs <filepath>
    # الغلاف يوجّه لذلك المسار الأصلي
    raise NotImplementedError(
        "olmocr يُشغَّل عبر pipeline كامل مع خادم vLLM.\n"
        "استخدم الأمر الأصلي:\n"
        f"  python -m olmocr.pipeline ./workspace --pdfs {filepath}\n"
        "أو استخدم chandra للاستدعاء المباشر داخل Python."
    )


# ─────────────────────────────────────────────────────────
# chandra — PDF/صور بدقة عالية (بلا تعديل منطق)
# ─────────────────────────────────────────────────────────

def _run_chandra(
    filepath: str,
    output: OutputFormat,
    device: DeviceCapabilities,
    **kwargs,
) -> tuple[str, list]:
    """
    يستدعي chandra InferenceManager كما هو.
    الكود الأصلي في engines_src_chandra/chandra/ — لا يُعدَّل.
    """
    try:
        from chandra.input import load_file
        from chandra.model import InferenceManager
        from chandra.model.schema import BatchInputItem
        from chandra.output import parse_markdown, parse_html, parse_chunks
    except ImportError:
        raise ImportError(
            "chandra غير مثبت. ثبّته من engines_src_chandra/:\n"
            "  pip install -e engines_src_chandra/[hf]   # محلي GPU\n"
            "  pip install -e engines_src_chandra/       # remote vLLM\n"
        )

    # اختيار طريقة الاستدلال: hf (محلي GPU) أو vllm (بعيد)
    method = "hf" if device.has_gpu else "vllm"
    manager = InferenceManager(method=method)

    # تحميل الملف (الدالة الأصلية)
    images = load_file(filepath)

    # بناء دفعة الإدخال (الـ schema الأصلي)
    batch = [BatchInputItem(image=img) for img in images]

    # الاستدلال (المنطق الأصلي كما هو)
    include_images = output in (OutputFormat.HTML, OutputFormat.JSON)
    results = manager.generate(batch, include_images=include_images)

    # تجميع المخرجات حسب الصيغة
    parts = []
    assets = []
    for res in results:
        raw = res.output if hasattr(res, "output") else str(res)
        if output == OutputFormat.MARKDOWN:
            parts.append(parse_markdown(raw))
        elif output == OutputFormat.HTML:
            parts.append(parse_html(raw))
        elif output == OutputFormat.JSON:
            chunks = parse_chunks(raw)
            parts.append(chunks)
        # جمع الصور المستخرجة
        if hasattr(res, "images") and res.images:
            assets.extend(res.images)

    if output == OutputFormat.JSON:
        import json
        return json.dumps(parts, ensure_ascii=False, indent=2), assets

    return "\n\n".join(str(p) for p in parts), assets


# ─────────────────────────────────────────────────────────
# Tesseract — fallback للأجهزة الصغيرة (Termux/CPU)
# ─────────────────────────────────────────────────────────

def _run_tesseract(filepath: str, output: OutputFormat, **kwargs) -> tuple[str, list]:
    """
    fallback بسيط عبر Tesseract OCR — للأجهزة بلا GPU.
    يعمل مع pdf2image لقراءة PDF الممسوحة.
    """
    if output != OutputFormat.MARKDOWN:
        raise ValueError(f"Tesseract fallback يدعم نصاً فقط، طُلب {output.value}.")

    try:
        import pytesseract
        from PIL import Image
    except ImportError:
        raise ImportError(
            "Tesseract fallback يحتاج: pip install pytesseract pillow pdf2image"
        )

    ext = Path(filepath).suffix.lower()
    lang = kwargs.get("lang", "ara+eng")  # عربي + إنجليزي افتراضياً

    if ext == ".pdf":
        try:
            from pdf2image import convert_from_path
        except ImportError:
            raise ImportError("PDF يحتاج: pip install pdf2image (+ poppler)")
        pages = convert_from_path(filepath)
        texts = [pytesseract.image_to_string(p, lang=lang) for p in pages]
        return "\n\n---\n\n".join(texts), []

    # صورة مفردة
    img = Image.open(filepath)
    return pytesseract.image_to_string(img, lang=lang), []
