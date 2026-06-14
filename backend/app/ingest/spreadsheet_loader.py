"""Spreadsheet loader (pandas + openpyxl).

Renders each sheet to a compact text form with cell coordinates so the model can
cite a location (e.g. 'Integrations!A2') and so grounding can match cell values.
"""
from __future__ import annotations

from pathlib import Path

from .loaders import ExtractedDoc


def _col_letter(idx: int) -> str:
    """0-based column index -> spreadsheet column letter (A, B, ... Z, AA)."""
    letters = ""
    idx += 1
    while idx:
        idx, rem = divmod(idx - 1, 26)
        letters = chr(65 + rem) + letters
    return letters


def _render_sheet(name: str, df) -> str:
    lines = [f"Sheet: {name}"]
    cols = list(df.columns)
    lines.append("Columns: " + " | ".join(str(c) for c in cols))
    for r_idx, (_, row) in enumerate(df.iterrows(), start=2):  # row 1 = header
        cells = []
        for c_idx, col in enumerate(cols):
            val = row[col]
            if val is None or (isinstance(val, float) and str(val) == "nan"):
                continue
            ref = f"{_col_letter(c_idx)}{r_idx}"
            cells.append(f"{ref}({col})={val}")
        if cells:
            lines.append("  " + " | ".join(cells))
    return "\n".join(lines)


def load_spreadsheet(path: Path) -> ExtractedDoc:
    import pandas as pd

    warnings: list[str] = []
    parts: list[str] = []
    ext = path.suffix.lower()
    if ext == ".csv":
        df = pd.read_csv(path, dtype=str, keep_default_na=False)
        parts.append(_render_sheet(path.stem, df))
    else:
        xls = pd.ExcelFile(path)
        for sheet in xls.sheet_names:
            df = xls.parse(sheet, dtype=str, keep_default_na=False)
            if df.empty:
                warnings.append(f"Sheet '{sheet}' is empty.")
                continue
            parts.append(_render_sheet(sheet, df))

    text = "\n\n".join(parts).strip()
    if not text:
        warnings.append("Spreadsheet contained no readable rows.")
    return ExtractedDoc(
        name=path.name,
        path=str(path),
        media_type="spreadsheet",
        text=text,
        pages=1,
        ingest_method="pandas",
        warnings=warnings,
    )
