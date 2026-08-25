"""
capabilities/tools/tool_doc_read.py
====================================
Tool 3: read PDF/DOCX/images with page numbers + OCR (UniDoc/Tesseract).
"""
from __future__ import annotations
import os, sys
from . import BaseTool, ToolResult

TOOL_SPEC = {
    "name": "doc_read",
    "description": "Read and extract text from PDF/DOCX/images with page numbers and OCR.",
    "triggers": ["اقرأ ملف", "استخرج نص", "ملف ممسوح", "صورة نص",
                 "read file", "extract text", "PDF", "OCR", "scanned"],
    "layers": [2],
}


class DocReadTool(BaseTool):
    TOOL_SPEC = TOOL_SPEC

    async def _execute(self, inputs: dict) -> ToolResult:
        path = inputs.get("path", "").strip()
        if not path:
            return ToolResult(ok=False, error="path is required")
        if not os.path.exists(path):
            return ToolResult(ok=False, error=f"file not found: {path}")

        ext = os.path.splitext(path)[1].lower()

        # PDF -> extract page by page with real page numbers (PyMuPDF4LLM)
        if ext == ".pdf":
            try:
                import pymupdf4llm
            except ImportError:
                return ToolResult(ok=False,
                    error="PyMuPDF4LLM not available (pip install pymupdf4llm)")
            pages = pymupdf4llm.to_markdown(path, page_chunks=True, show_progress=False)
            out = []
            for pg in pages:
                text = (pg.get("text") or "").strip()
                if not text:
                    continue
                meta = pg.get("metadata", {})
                out.append({
                    "page": meta.get("page_number", meta.get("page", len(out) + 1)),
                    "text": text,
                })
            return ToolResult(ok=True, data={"pages": out, "count": len(out), "type": "pdf"})

        # DOCX
        if ext in (".docx", ".doc"):
            try:
                import mammoth
            except ImportError:
                return ToolResult(ok=False, error="mammoth not available")
            with open(path, "rb") as f:
                result = mammoth.extract_raw_text(f)
            return ToolResult(ok=True, data={
                "text": result.value, "type": "docx",
            })

        # Images -> OCR
        if ext in (".png", ".jpg", ".jpeg", ".tiff", ".bmp"):
            try:
                import pytesseract
                from PIL import Image
            except ImportError:
                return ToolResult(ok=False, error="pytesseract/PIL not available")
            lang = inputs.get("ocr_lang", "ara+eng")
            text = pytesseract.image_to_string(Image.open(path), lang=lang)
            return ToolResult(ok=True, data={"text": text, "type": "image_ocr"})

        # Plain text
        with open(path, encoding="utf-8", errors="ignore") as f:
            return ToolResult(ok=True, data={"text": f.read(), "type": "text"})


async def run(inputs: dict) -> ToolResult:
    return await DocReadTool().run(inputs)
