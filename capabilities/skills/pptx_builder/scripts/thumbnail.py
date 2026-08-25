"""
thumbnail.py — render slide thumbnails for visual review (working script)
========================================================================
Converts a .pptx to per-slide PNG images so the deck can be reviewed
visually before delivery — the same quality-check step Claude performs.

Path: LibreOffice (soffice) converts .pptx -> .pdf, then pdf2image
renders each page to PNG. Both are commonly available on Termux.

Usage:
    python thumbnail.py --input deck.pptx --outdir ./thumbs
"""
from __future__ import annotations
import argparse
import os
import shutil
import subprocess
import tempfile


def generate_thumbnails(pptx_path: str, outdir: str = "./thumbs", dpi: int = 100):
    """Render each slide of a .pptx to a PNG. Returns list of PNG paths."""
    if not os.path.exists(pptx_path):
        raise FileNotFoundError(pptx_path)
    os.makedirs(outdir, exist_ok=True)

    soffice = shutil.which("soffice") or shutil.which("libreoffice")
    if not soffice:
        raise RuntimeError("LibreOffice not installed (needed to render slides). "
                           "Termux: pkg install libreoffice")

    # 1) pptx -> pdf
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run([soffice, "--headless", "--convert-to", "pdf",
                        "--outdir", tmp, pptx_path],
                       check=True, capture_output=True)
        base = os.path.splitext(os.path.basename(pptx_path))[0]
        pdf_path = os.path.join(tmp, base + ".pdf")
        if not os.path.exists(pdf_path):
            raise RuntimeError("pptx -> pdf conversion failed")

        # 2) pdf -> per-page PNG
        try:
            from pdf2image import convert_from_path
        except ImportError:
            raise RuntimeError("pdf2image not available (needs poppler). "
                               "Termux: pkg install poppler")
        images = convert_from_path(pdf_path, dpi=dpi)
        paths = []
        for i, img in enumerate(images, start=1):
            out = os.path.join(outdir, f"slide_{i:02d}.png")
            img.save(out, "PNG")
            paths.append(out)
        return paths


def _main():
    p = argparse.ArgumentParser(description="Render slide thumbnails")
    p.add_argument("--input", required=True)
    p.add_argument("--outdir", default="./thumbs")
    p.add_argument("--dpi", type=int, default=100)
    args = p.parse_args()
    try:
        paths = generate_thumbnails(args.input, args.outdir, args.dpi)
        print(f"Rendered {len(paths)} thumbnails to {args.outdir}")
        for p_ in paths:
            print(f"  {p_}")
    except Exception as e:
        print(f"Error: {e}")


if __name__ == "__main__":
    _main()
