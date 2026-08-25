"""
recalc.py — recalculate Excel formulas after edits (working script)
===================================================================
openpyxl stores formulas but does not evaluate them. This script forces a
recalculation on next open, and optionally evaluates simple formulas in
place using the `formulas` library if available.

Usage:
    python recalc.py --file data.xlsx
"""
from __future__ import annotations
import argparse


def recalc(xlsx_path: str, evaluate: bool = False) -> dict:
    """
    Mark the workbook to recalculate on open. If evaluate=True and the
    `formulas` library is present, compute values in place.
    """
    from openpyxl import load_workbook

    wb = load_workbook(xlsx_path)
    # force full recalculation when the file is next opened
    try:
        wb.calculation.fullCalcOnLoad = True
    except Exception:
        pass
    wb.save(xlsx_path)

    result = {"path": xlsx_path, "recalc_on_load": True, "evaluated": False}

    if evaluate:
        try:
            import formulas
            xl_model = formulas.ExcelModel().loads(xlsx_path).finish()
            xl_model.calculate()
            xl_model.write(dirpath=".")
            result["evaluated"] = True
        except ImportError:
            result["note"] = ("in-place evaluation needs the 'formulas' library "
                              "(pip install formulas); recalc-on-load is set instead")
    return result


def _main():
    p = argparse.ArgumentParser(description="Recalculate Excel formulas")
    p.add_argument("--file", required=True)
    p.add_argument("--evaluate", action="store_true")
    args = p.parse_args()
    r = recalc(args.file, args.evaluate)
    print(f"Recalc-on-load set: {r['recalc_on_load']}")
    if r.get("note"):
        print(r["note"])


if __name__ == "__main__":
    _main()
