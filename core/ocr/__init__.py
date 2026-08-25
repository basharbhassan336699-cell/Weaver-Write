"""
core/ocr/__init__.py
====================
UniDoc مدمجة كمحرك OCR وقراءة مستندات داخلي.

يُستخدم لـ:
  - قراءة PDFs الأكاديمية (نصية + ممسوحة)
  - استخراج النص مع رقم الصفحة (PyMuPDF4LLM)
  - قراءة ملفات Word/Excel/PPTX
  - تحويل أي مستند → نص منظّم
"""

from __future__ import annotations
import sys
import os
from typing import Optional
from dataclasses import dataclass

UNIDOC_PATH = os.path.join(os.path.dirname(__file__), "../../engines/unidoc-core")
if UNIDOC_PATH not in sys.path:
    sys.path.insert(0, UNIDOC_PATH)

from unidoc import convert, convert_detailed
from unidoc.router import OutputFormat, Engine
from unidoc.device import detect_device


@dataclass
class DocumentPage:
    """صفحة مستند مع نصها ورقمها."""
    page: int
    text: str
    source: str


@dataclass
class ParsedDocument:
    """مستند مُحلَّل كامل مع كل صفحاته."""
    source: str
    pages: list[DocumentPage]
    full_text: str
    engine_used: str
    total_pages: int

    def get_page(self, page_num: int) -> Optional[DocumentPage]:
        """يسترجع صفحة محددة برقمها."""
        for p in self.pages:
            if p.page == page_num:
                return p
        return None


class WeaverOCR:
    """
    محرك OCR وقراءة المستندات الداخلي لـ Weaver Write.

    يختار تلقائياً:
      DOCX/PPTX/XLSX/RTF/EPUB → anydoc (CPU، سريع)
      PDF نصي + GPU           → olmocr
      PDF ممسوح + دقة عالية   → chandra
      PDF + لا GPU             → Tesseract (Termux)
    """

    def __init__(self, force_engine: str = None):
        self.device = detect_device()
        self.force_engine = force_engine

    def read(self, filepath: str, output: str = "markdown") -> str:
        """
        يقرأ أي مستند ويُعيد نصاً.
        أبسط واجهة — للقراءة السريعة.
        """
        return convert(
            filepath,
            output=output,
            engine=self.force_engine,
        )

    def read_with_pages(self, filepath: str) -> ParsedDocument:
        """
        يقرأ مستنداً مع رقم الصفحة لكل مقطع.
        الواجهة الأهم — للاستشهاد الدقيق.

        يستخدم PyMuPDF4LLM لاستخراج رقم الصفحة الحقيقي.
        """
        try:
            # المسار المفضل: PyMuPDF4LLM لرقم الصفحة الحقيقي
            from paperqa_pages import extract_with_pages
            paged = extract_with_pages(filepath)
            pages = [
                DocumentPage(page=c.page, text=c.text, source=filepath)
                for c in paged
            ]
            full_text = "\n\n".join(p.text for p in pages)
            return ParsedDocument(
                source=filepath,
                pages=pages,
                full_text=full_text,
                engine_used="pymupdf4llm",
                total_pages=len(pages),
            )
        except (ImportError, Exception):
            # Fallback: UniDoc بدون أرقام صفحات
            result = convert_detailed(filepath, engine=self.force_engine)
            text = result["content"]
            # تقسيم بسيط للمحاكاة
            chunks = text.split("\n\n")
            pages = [
                DocumentPage(page=i + 1, text=chunk, source=filepath)
                for i, chunk in enumerate(chunks) if chunk.strip()
            ]
            return ParsedDocument(
                source=filepath,
                pages=pages,
                full_text=text,
                engine_used=result.get("engine", "unidoc"),
                total_pages=len(pages),
            )

    def read_url(self, url: str) -> ParsedDocument:
        """
        يجلب PDF من URL ثم يقرأه مع أرقام الصفحات.
        يدعم arXiv, DOI, ResearchGate.
        """
        import tempfile
        import urllib.request

        # تنزيل مؤقت
        suffix = ".pdf"
        if url.startswith("10."):
            url = f"https://doi.org/{url}"
        headers = {"User-Agent": "Mozilla/5.0 (Weaver Write research tool)"}
        req = urllib.request.Request(url, headers=headers)
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            with urllib.request.urlopen(req, timeout=60) as resp:
                tmp.write(resp.read())
            tmp_path = tmp.name
        try:
            return self.read_with_pages(tmp_path)
        finally:
            os.unlink(tmp_path)

    def supported_formats(self) -> list[str]:
        """قائمة الصيغ المدعومة."""
        return [
            "pdf", "docx", "doc", "pptx", "ppt",
            "xlsx", "xls", "rtf", "epub",
            "odt", "ods", "odp", "csv",
            "png", "jpg", "jpeg", "tiff",  # OCR
        ]
