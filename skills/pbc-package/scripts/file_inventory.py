"""
Inventory a folder of support files and produce a structured summary.

For each file under the target path (recursive):
    path           absolute path
    rel_path       path relative to root
    name           filename
    extension      .pdf | .xlsx | .csv | .docx | ...
    size_bytes
    modified       ISO date
    summary        1-line content summary; empty string if not extractable

Content summaries:
    .pdf    first non-empty text snippet from page 1 (pdfplumber)
    .xlsx   first non-empty cell from first sheet
    .csv    first header row joined
    .docx   first paragraph (if python-docx available; else blank)
    others  empty (the filename + size is the inventory; no content summary)

Usage:
    from file_inventory import inventory
    df = inventory(Path("./pbc_support"))

Standalone CLI:
    python file_inventory.py ./pbc_support --out inventory.csv
"""
from __future__ import annotations

import argparse
import csv
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

try:
    import pdfplumber
except ImportError:  # pragma: no cover
    pdfplumber = None

try:
    from openpyxl import load_workbook
except ImportError:  # pragma: no cover
    load_workbook = None


SUMMARY_MAX_LEN = 200


def inventory(root: Path) -> pd.DataFrame:
    rows: list[dict] = []
    if not root.exists():
        raise FileNotFoundError(root)
    if root.is_file():
        rows.append(_record(root, root.parent))
    else:
        for path in sorted(root.rglob("*")):
            if path.is_file():
                rows.append(_record(path, root))
    return pd.DataFrame(rows)


def _record(path: Path, root: Path) -> dict:
    stat = path.stat()
    return {
        "path": str(path.resolve()),
        "rel_path": str(path.relative_to(root)),
        "name": path.name,
        "extension": path.suffix.lower(),
        "size_bytes": stat.st_size,
        "modified": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d"),
        "summary": _summarize(path),
    }


def _summarize(path: Path) -> str:
    try:
        suffix = path.suffix.lower()
        if suffix == ".pdf":
            return _summarize_pdf(path)
        if suffix == ".xlsx":
            return _summarize_xlsx(path)
        if suffix == ".csv":
            return _summarize_csv(path)
        if suffix == ".txt":
            return _truncate(path.read_text(encoding="utf-8", errors="replace"))
        return ""
    except Exception as exc:  # pragma: no cover
        return f"[summary failed: {exc.__class__.__name__}]"


def _summarize_pdf(path: Path) -> str:
    if pdfplumber is None:
        return ""
    with pdfplumber.open(path) as pdf:
        if not pdf.pages:
            return ""
        text = pdf.pages[0].extract_text() or ""
        for line in text.splitlines():
            s = line.strip()
            if s:
                return _truncate(s)
    return ""


def _summarize_xlsx(path: Path) -> str:
    if load_workbook is None:
        return ""
    wb = load_workbook(path, read_only=True, data_only=True)
    sheet = wb[wb.sheetnames[0]]
    for row in sheet.iter_rows(values_only=True):
        cells = [str(c) for c in row if c not in (None, "")]
        if cells:
            return _truncate(" | ".join(cells))
    return ""


def _summarize_csv(path: Path) -> str:
    with path.open("r", encoding="utf-8", errors="replace", newline="") as f:
        reader = csv.reader(f)
        for row in reader:
            cells = [c.strip() for c in row if c.strip()]
            if cells:
                return _truncate(" | ".join(cells))
    return ""


def _truncate(s: str) -> str:
    s = " ".join(s.split())
    return s[:SUMMARY_MAX_LEN]


def _cli(argv=None) -> int:
    p = argparse.ArgumentParser(description="Inventory a folder of PBC support files.")
    p.add_argument("root", type=Path)
    p.add_argument("--out", type=Path, default=Path("inventory.csv"))
    args = p.parse_args(argv)

    df = inventory(args.root)
    if args.out.suffix.lower() == ".csv":
        df.to_csv(args.out, index=False)
    else:
        df.to_excel(args.out, index=False)

    print(f"Inventoried {len(df)} files under {args.root}")
    print(f"Wrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(_cli())
