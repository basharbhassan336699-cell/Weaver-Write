"""
capabilities/tools/tool_pdf.py
===============================
Tool 10: PDF operations.

Read text/tables: via pdfplumber (vendored).
OCR scanned PDFs: via pdf2image + pytesseract (vendored) — works without GPU.
Build/merge/split: via pypdf/reportlab (requirements).

Complements the doc_read tool: doc_read is the generic multi-format reader;
this tool is the PDF specialist (tables, OCR, page geometry).
"""
from __future__ import annotations
import os
import sys
from . import BaseTool, ToolResult

TOOL_SPEC = {
    "name": "pdf",
    "description": "Read PDF text/tables, OCR scanned PDFs (no GPU), or build/merge PDFs. Via pdfplumber/pdf2image/pytesseract.",
    "triggers": ["PDF", "ملف PDF", "جداول PDF", "ملف ممسوح", "OCR",
                 "pdf tables", "scanned pdf", "read pdf", "merge pdf"],
    "layers": [2, 8],
}


def _vendored_dir():
    base = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.join(base, "engines", "office-core", "vendored")


class PdfTool(BaseTool):
    TOOL_SPEC = TOOL_SPEC

    def _ensure_vendored(self):
        v = _vendored_dir()
        if v not in sys.path:
            sys.path.insert(0, v)

    async def _execute(self, inputs: dict) -> ToolResult:
        action = inputs.get("action", "read")  # read | tables | ocr | merge
        if action == "tables":
            return await self._tables(inputs)
        if action == "ocr":
            return await self._ocr(inputs)
        if action == "merge":
            return await self._merge(inputs)
        if action == "advanced":
            return await self._advanced(inputs)
        return await self._read(inputs)

    # ── read text page by page ───────────────────────────────
    async def _read(self, inputs: dict) -> ToolResult:
        path = inputs.get("path", "").strip()
        if not path or not os.path.exists(path):
            return ToolResult(ok=False, error=f"file not found: {path}")

        self._ensure_vendored()
        try:
            import pdfplumber
        except ImportError:
            return ToolResult(ok=False, error="pdfplumber not available")

        pages = []
        with pdfplumber.open(path) as pdf:
            for i, page in enumerate(pdf.pages, start=1):
                text = page.extract_text() or ""
                if text.strip():
                    pages.append({"page": i, "text": text})
        return ToolResult(ok=True, data={
            "pages": pages, "count": len(pages), "engine": "pdfplumber",
        })

    # ── extract tables ───────────────────────────────────────
    async def _tables(self, inputs: dict) -> ToolResult:
        path = inputs.get("path", "").strip()
        if not path or not os.path.exists(path):
            return ToolResult(ok=False, error=f"file not found: {path}")

        self._ensure_vendored()
        try:
            import pdfplumber
        except ImportError:
            return ToolResult(ok=False, error="pdfplumber not available")

        all_tables = []
        with pdfplumber.open(path) as pdf:
            for i, page in enumerate(pdf.pages, start=1):
                for t in page.extract_tables():
                    all_tables.append({"page": i, "table": t})
        return ToolResult(ok=True, data={
            "tables": all_tables, "count": len(all_tables), "engine": "pdfplumber",
        })

    # ── OCR scanned PDF (no GPU) ─────────────────────────────
    async def _ocr(self, inputs: dict) -> ToolResult:
        path = inputs.get("path", "").strip()
        if not path or not os.path.exists(path):
            return ToolResult(ok=False, error=f"file not found: {path}")

        self._ensure_vendored()
        try:
            from pdf2image import convert_from_path
            import pytesseract
        except ImportError:
            return ToolResult(ok=False,
                error="pdf2image/pytesseract not available (needs poppler + tesseract)")

        lang = inputs.get("ocr_lang", "ara+eng")
        images = convert_from_path(path, dpi=inputs.get("dpi", 200))
        pages = []
        for i, img in enumerate(images, start=1):
            text = pytesseract.image_to_string(img, lang=lang)
            if text.strip():
                pages.append({"page": i, "text": text})
        return ToolResult(ok=True, data={
            "pages": pages, "count": len(pages), "engine": "pdf2image+pytesseract",
        })

    # ── advanced conversion (docling) ────────────────────────
    async def _advanced(self, inputs: dict) -> ToolResult:
        """Complex-layout PDF -> structured markdown via docling (vendored)."""
        path = inputs.get("path", "").strip()
        if not path or not os.path.exists(path):
            return ToolResult(ok=False, error=f"file not found: {path}")
        self._ensure_vendored()
        try:
            from docling.document_converter import DocumentConverter
        except ImportError:
            return ToolResult(ok=False,
                error="docling not available; use action=read for simple PDFs")
        converter = DocumentConverter()
        result = converter.convert(path)
        return ToolResult(ok=True, data={
            "markdown": result.document.export_to_markdown(),
            "engine": "docling",
        })

    # ── merge PDFs ───────────────────────────────────────────
    async def _merge(self, inputs: dict) -> ToolResult:
        paths = inputs.get("paths", [])
        output = inputs.get("output_path", "./output/merged.pdf")
        if len(paths) < 2:
            return ToolResult(ok=False, error="at least two paths are required")

        os.makedirs(os.path.dirname(output) or ".", exist_ok=True)
        try:
            from pypdf import PdfWriter
        except ImportError:
            return ToolResult(ok=False, error="pypdf not available")

        writer = PdfWriter()
        for p in paths:
            if os.path.exists(p):
                writer.append(p)
        with open(output, "wb") as f:
            writer.write(f)
        return ToolResult(ok=True, data={"output_path": output, "engine": "pypdf"})


async def run(inputs: dict) -> ToolResult:
    return await PdfTool().run(inputs)
