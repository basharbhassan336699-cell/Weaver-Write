# office-core — Office document engine for Weaver Write

Provides the vendored libraries and the runtime for the four office tools:
`word`, `powerpoint`, `excel`, `pdf` (in capabilities/tools/).

## vendored/ (bundled, no install needed — Termux-friendly)

| Library | Language | Purpose | Used by tool |
|---------|----------|---------|--------------|
| openpyxl | Python | Excel formulas/formatting | excel |
| pdfplumber | Python | PDF text/table extraction | pdf |
| pdf2image | Python | PDF pages → images (OCR) | pdf |
| pytesseract | Python | OCR (no GPU) | pdf |
| markitdown | Python | Office → clean markdown (read) | word, powerpoint |
| docx_js | JavaScript | Build Word (dist build) | word |
| pptxgenjs_js | JavaScript | Build PowerPoint (dist build) | powerpoint |
| office_oxide | Rust/Python | Fast Office text extraction (100x) | word, excel, powerpoint |
| docling | Python | Advanced complex-layout conversion | pdf |

## Heavy libraries via requirements (not vendored)

`pandas`, `pandoc`, `pypdf`, `reportlab`, `python-docx`, `python-pptx`
— see engines/office-core/requirements.txt

## System dependencies (for OCR only)

- `poppler-utils` (pdf2image needs it)
- `tesseract-ocr` + `tesseract-ocr-ara` (Arabic OCR)

On Termux:
    pkg install poppler tesseract tesseract-data-ara

## How the tools use this

Tools add `vendored/` to sys.path at call time, so the bundled libraries
resolve without a system install. Heavy libraries fall back to the
pip-installed versions.
