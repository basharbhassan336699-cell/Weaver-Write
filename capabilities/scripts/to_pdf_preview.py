"""
to_pdf_preview.py — convert DOCX/PPTX to PDF for preview (shared script)
========================================================================
Uses LibreOffice (soffice) to convert a file to PDF for previewing the
final look before delivery — same principle as Claude's soffice.py.

Usage:
    python to_pdf_preview.py --input research.docx --outdir ./preview
"""
from __future__ import annotations
import argparse
import subprocess
import os
import shutil


def convert_to_pdf(input_path: str, outdir: str = ".") -> str:
    """Convert an Office file to PDF via LibreOffice."""
    soffice = shutil.which("soffice") or shutil.which("libreoffice")
    if not soffice:
        raise RuntimeError("LibreOffice not installed (apt install libreoffice)")

    os.makedirs(outdir, exist_ok=True)
    subprocess.run([
        soffice, "--headless", "--convert-to", "pdf",
        "--outdir", outdir, input_path,
    ], check=True, capture_output=True)

    base = os.path.splitext(os.path.basename(input_path))[0]
    return os.path.join(outdir, base + ".pdf")


def _main():
    p = argparse.ArgumentParser()
    p.add_argument("--input", required=True)
    p.add_argument("--outdir", default="./preview")
    args = p.parse_args()
    try:
        path = convert_to_pdf(args.input, args.outdir)
        print(f"PDF preview: {path}")
    except Exception as e:
        print(f"Error: {e}")


if __name__ == "__main__":
    _main()
