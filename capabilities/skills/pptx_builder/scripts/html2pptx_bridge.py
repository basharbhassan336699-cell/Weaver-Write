"""
html2pptx_bridge.py — convert themed HTML to native PPTX (working script)
=========================================================================
Bridges Python -> the vendored Node.js html2pptx engine
(engines/html2pptx-core). Given an HTML deck, it produces a native,
editable .pptx (not an image), preserving the CSS design.

This is the "Claude way": design in HTML/CSS, convert to real PPTX shapes.

Requires: Node.js + the engine deps (adm-zip, cheerio, css, pptxgenjs),
installed once in engines/html2pptx-core/.
"""
from __future__ import annotations
import argparse
import os
import subprocess
import tempfile
import shutil

_ENGINE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.dirname(os.path.abspath(__file__)))))),
    "engines", "html2pptx-core")


def html_to_pptx(html_path_or_str, output_path, is_string=False):
    """
    Convert an HTML file (or HTML string) to native PPTX via the Node engine.
    Returns {"ok": bool, "output_path": str, "engine": str, "error": str?}
    """
    node = shutil.which("node")
    if not node:
        return {"ok": False, "error": "Node.js not installed (needed for html2pptx). "
                                      "Termux: pkg install nodejs"}

    lib = os.path.join(_ENGINE, "lib", "html2pptx.js")
    if not os.path.exists(lib):
        return {"ok": False, "error": f"html2pptx engine not found at {lib}"}

    # engine deps must be installed
    if not os.path.isdir(os.path.join(_ENGINE, "node_modules")):
        return {"ok": False,
                "error": "html2pptx deps not installed. Run once: "
                         f"cd {_ENGINE} && npm install"}

    # materialize HTML to a temp file if given as string
    cleanup = None
    if is_string:
        fd, html_path = tempfile.mkstemp(suffix=".html")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(html_path_or_str)
        cleanup = html_path
    else:
        html_path = html_path_or_str

    output_path = os.path.abspath(output_path)
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

    # small Node runner
    runner = (
        "const {convertHTML2PPTX}=require(process.argv[1]);"
        "convertHTML2PPTX(process.argv[2],process.argv[3])"
        ".then(r=>{console.log('OK');process.exit(0);})"
        ".catch(e=>{console.error(e.message);process.exit(1);});"
    )
    try:
        proc = subprocess.run(
            [node, "-e", runner, lib, html_path, output_path],
            capture_output=True, text=True, timeout=120, cwd=_ENGINE)
    finally:
        if cleanup:
            try: os.unlink(cleanup)
            except Exception: pass

    if proc.returncode != 0:
        return {"ok": False, "error": proc.stderr.strip() or "conversion failed"}
    return {"ok": True, "output_path": output_path, "engine": "html2pptx"}


def _main():
    p = argparse.ArgumentParser(description="Convert HTML to native PPTX")
    p.add_argument("--input", required=True, help="HTML file path")
    p.add_argument("--output", default="deck.pptx")
    args = p.parse_args()
    r = html_to_pptx(args.input, args.output)
    if r["ok"]:
        print(f"Created: {r['output_path']}")
    else:
        print(f"Error: {r['error']}")


if __name__ == "__main__":
    _main()
