"""
capabilities/tools/tool_web_document.py
=========================================
Tool 18: fetch a remote document from a URL and read it — including
scanned PDFs and images — completing the web → OCR loop.

This is the missing bridge. Previously:
  - web_extract read HTML text only (stopped at a file link)
  - doc_read / pdf handled ONLY locally-uploaded files

This tool closes the gap: given a URL, it downloads the file, detects its
type, and routes it to the right reader — reusing the existing doc_read /
pdf logic instead of duplicating it.

Routing:
    HTML          -> trafilatura (clean article text)
    text PDF      -> pdfplumber (page by page)
    scanned PDF   -> pdf2image + pytesseract (OCR, no GPU)
    image         -> pytesseract (OCR)
    docx/other    -> doc_read tool

The scanned-vs-text PDF decision is automatic: if pdfplumber extracts
almost no text, the PDF is treated as scanned and sent to OCR.
"""
from __future__ import annotations
import os
import sys
import tempfile
import urllib.request
import urllib.parse
from . import BaseTool, ToolResult

TOOL_SPEC = {
    "name": "web_document",
    "description": "Download a document from a URL and read it (HTML/PDF/scanned-PDF/image) with automatic OCR. Bridges web discovery to document reading.",
    "triggers": ["نزّل واقرأ", "اقرأ رابط ملف", "مرجع من الإنترنت", "ملف من رابط",
                 "PDF من الإنترنت", "download and read", "read url file", "remote pdf",
                 "fetch document", "online reference", "رابط", "من الإنترنت", "من رابط", "url"],
    "layers": [2, 4],
}

# If pdfplumber gets fewer than this many chars per page on average,
# treat the PDF as scanned and fall back to OCR.
_SCANNED_THRESHOLD = 40


def _tools_dir():
    return os.path.dirname(os.path.abspath(__file__))


class WebDocumentTool(BaseTool):
    TOOL_SPEC = TOOL_SPEC

    async def _execute(self, inputs: dict) -> ToolResult:
        url = inputs.get("url", "").strip()
        if not url:
            return ToolResult(ok=False, error="url is required")

        ocr_lang = inputs.get("ocr_lang", "ara+eng")
        force = inputs.get("force_type")  # optional: html|pdf|image

        # ── 1. detect type from URL/extension first ──────────
        path_part = urllib.parse.urlparse(url).path.lower()
        ext = os.path.splitext(path_part)[1]

        is_html_like = force == "html" or (
            not ext or ext in (".html", ".htm", ".php", ".asp", ".aspx")
        )

        # HTML pages → trafilatura (no download-to-disk needed)
        if force != "pdf" and force != "image" and is_html_like:
            html_result = self._read_html(url)
            if html_result.ok:
                return html_result
            # if HTML extraction failed, fall through to file download

        # ── 2. download the file to a temp path ──────────────
        try:
            tmp_path = self._download(url, inputs.get("timeout", 30))
        except Exception as e:
            return ToolResult(ok=False, error=f"download failed: {e}")

        try:
            # ── 3. route by real content ─────────────────────
            real_ext = force or self._sniff(tmp_path, ext)

            if real_ext in (".pdf", "pdf"):
                return self._read_pdf(tmp_path, url, ocr_lang)
            if real_ext in (".png", ".jpg", ".jpeg", ".tiff", ".bmp", "image"):
                return self._read_image(tmp_path, url, ocr_lang)
            # docx/other → delegate to doc_read
            return self._read_via_docread(tmp_path, url)
        finally:
            try:
                os.unlink(tmp_path)
            except Exception:
                pass

    # ── HTML ─────────────────────────────────────────────────
    def _read_html(self, url: str) -> ToolResult:
        base = os.path.dirname(os.path.dirname(_tools_dir()))
        uniweb = os.path.join(base, "engines", "uniweb-core")
        if uniweb not in sys.path:
            sys.path.insert(0, uniweb)
        try:
            from trafilatura import fetch_url, extract
        except ImportError:
            return ToolResult(ok=False, error="trafilatura not available")
        downloaded = fetch_url(url)
        if not downloaded:
            return ToolResult(ok=False, error="could not fetch HTML")
        text = extract(downloaded, output_format="markdown",
                       include_comments=False, include_tables=True)
        if not text:
            return ToolResult(ok=False, error="no article text extracted")
        return ToolResult(ok=True, data={
            "url": url, "text": text, "type": "html", "engine": "trafilatura",
        })

    # ── PDF (auto text vs scanned) ───────────────────────────
    def _read_pdf(self, path: str, url: str, ocr_lang: str) -> ToolResult:
        # try text extraction first
        pages = []
        total_chars = 0
        try:
            import pdfplumber
            with pdfplumber.open(path) as pdf:
                for i, page in enumerate(pdf.pages, start=1):
                    text = page.extract_text() or ""
                    total_chars += len(text)
                    pages.append({"page": i, "text": text})
            n = len(pages) or 1
            avg = total_chars / n
        except ImportError:
            return ToolResult(ok=False, error="pdfplumber not available")
        except Exception as e:
            return ToolResult(ok=False, error=f"pdf read failed: {e}")

        # enough text → it's a text PDF
        if avg >= _SCANNED_THRESHOLD:
            return ToolResult(ok=True, data={
                "url": url, "pages": [p for p in pages if p["text"].strip()],
                "count": len([p for p in pages if p["text"].strip()]),
                "type": "pdf_text", "engine": "pdfplumber",
            })

        # too little text → scanned PDF → OCR
        try:
            from pdf2image import convert_from_path
            import pytesseract
        except ImportError:
            # return whatever little text we got, flagged
            return ToolResult(ok=True, data={
                "url": url, "pages": pages, "type": "pdf_lowtext",
                "engine": "pdfplumber",
                "warning": "looks scanned but OCR deps missing "
                           "(install poppler + tesseract for OCR)",
            })

        images = convert_from_path(path, dpi=200)
        ocr_pages = []
        for i, img in enumerate(images, start=1):
            text = pytesseract.image_to_string(img, lang=ocr_lang)
            if text.strip():
                ocr_pages.append({"page": i, "text": text})
        return ToolResult(ok=True, data={
            "url": url, "pages": ocr_pages, "count": len(ocr_pages),
            "type": "pdf_scanned", "engine": "pdf2image+pytesseract",
        })

    # ── image → OCR ──────────────────────────────────────────
    def _read_image(self, path: str, url: str, ocr_lang: str) -> ToolResult:
        try:
            import pytesseract
            from PIL import Image
        except ImportError:
            return ToolResult(ok=False,
                error="pytesseract/PIL not available (install tesseract)")
        text = pytesseract.image_to_string(Image.open(path), lang=ocr_lang)
        return ToolResult(ok=True, data={
            "url": url, "text": text, "type": "image_ocr",
            "engine": "pytesseract",
        })

    # ── delegate docx/other to doc_read (read inline, no async) ──
    def _read_via_docread(self, path: str, url: str) -> ToolResult:
        ext = os.path.splitext(path)[1].lower()
        # DOCX via mammoth (same engine doc_read uses)
        if ext in (".docx", ".doc"):
            try:
                import mammoth
                with open(path, "rb") as f:
                    r = mammoth.extract_raw_text(f)
                return ToolResult(ok=True, data={
                    "url": url, "text": r.value, "type": "docx", "engine": "mammoth",
                })
            except ImportError:
                return ToolResult(ok=False, error="mammoth not available for docx")
        # plain text fallback
        try:
            with open(path, encoding="utf-8", errors="ignore") as f:
                return ToolResult(ok=True, data={
                    "url": url, "text": f.read(), "type": "text", "engine": "plain",
                })
        except Exception as e:
            return ToolResult(ok=False, error=f"unsupported document type: {e}")

    # ── helpers ──────────────────────────────────────────────
    @staticmethod
    def _download(url: str, timeout: int) -> str:
        req = urllib.request.Request(url, headers={"User-Agent": "WeaverWrite/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = resp.read()
        suffix = os.path.splitext(urllib.parse.urlparse(url).path)[1] or ".bin"
        fd, tmp_path = tempfile.mkstemp(suffix=suffix)
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        return tmp_path

    @staticmethod
    def _sniff(path: str, ext_hint: str) -> str:
        """Detect real type from magic bytes when the extension is unclear."""
        try:
            with open(path, "rb") as f:
                head = f.read(8)
        except Exception:
            return ext_hint or ".bin"
        if head.startswith(b"%PDF"):
            return ".pdf"
        if head.startswith(b"\x89PNG"):
            return ".png"
        if head.startswith(b"\xff\xd8\xff"):
            return ".jpg"
        if head[:2] == b"PK":       # zip-based (docx/xlsx/pptx)
            return ext_hint or ".docx"
        return ext_hint or ".bin"


async def run(inputs: dict) -> ToolResult:
    return await WebDocumentTool().run(inputs)
