"""
Extract structured prepaid-relevant fields from invoices.

Supports two input modes:
  1. PDF invoices — uses pdfplumber to extract text, then regex/heuristics
     to pull vendor, invoice number, date, amount, and service period.
  2. Structured CSV/XLSX — passthrough with column normalization for ops
     that already have parsed invoice data (most ERPs export this).

Each extracted record has a per-field confidence:
  HIGH    direct read from a structured source or unambiguous regex match
  MEDIUM  inferred from descriptor (e.g., "annual" -> 12 months)
  LOW     OCR low character confidence, ambiguous phrasing, or guessed

Records that lack required fields are still returned with the fields blank
and confidence LOW for missing values — surfacing the gap is the point.

Usage:
    from extract_invoice_fields import extract_from_path, extract_records
    records = extract_from_path(Path("invoices/INV-2398.pdf"))
    records = extract_records(structured_df)

Standalone CLI:
    python extract_invoice_fields.py invoices/ --out extracted.csv
    python extract_invoice_fields.py invoices.csv --out extracted.csv
"""
from __future__ import annotations

import argparse
import re
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterable

import pandas as pd

try:
    import pdfplumber
except ImportError:  # pragma: no cover
    pdfplumber = None


MONTHS_BY_DESCRIPTOR = {
    "annual": 12,
    "yearly": 12,
    "year": 12,
    "biannual": 24,
    "semi-annual": 6,
    "semiannual": 6,
    "quarterly": 3,
    "quarter": 3,
    "monthly": 1,
    "month": 1,
}

CATEGORY_BY_KEYWORD = [
    (re.compile(r"\binsurance\b", re.I), "insurance"),
    (re.compile(r"\b(rent|lease)\b", re.I), "rent"),
    (re.compile(r"\b(license|software|saas|subscription)\b", re.I), "subscription"),
    (re.compile(r"\b(maintenance|support contract)\b", re.I), "maintenance"),
]


@dataclass
class InvoiceRecord:
    source_file: str
    source_page: int = 0
    vendor: str = ""
    invoice_number: str = ""
    invoice_date: str = ""
    amount: float | None = None
    service_start: str = ""
    service_end: str = ""
    service_period_descriptor: str = ""
    inferred_months: int | None = None
    category: str = ""
    confidence: dict[str, str] = field(default_factory=dict)
    notes: str = ""


def _conf(rec: InvoiceRecord, **kv: str) -> None:
    rec.confidence.update(kv)


def _parse_pdf(path: Path) -> list[InvoiceRecord]:
    if pdfplumber is None:
        raise RuntimeError("pdfplumber not installed; cannot read PDF invoices")
    records: list[InvoiceRecord] = []
    with pdfplumber.open(path) as pdf:
        for i, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            if not text.strip():
                rec = InvoiceRecord(source_file=str(path), source_page=i)
                _conf(rec, vendor="LOW", amount="LOW", invoice_date="LOW")
                rec.notes = "Page contained no extractable text; likely scanned image."
                records.append(rec)
                continue
            records.append(_extract_from_text(text, str(path), i))
    return records


def _extract_from_text(text: str, source_file: str, page: int) -> InvoiceRecord:
    rec = InvoiceRecord(source_file=source_file, source_page=page)

    m = re.search(r"(?im)^\s*(?:invoice\s*(?:no\.?|#|number)\s*:?\s*)([A-Z0-9\-/]+)", text)
    if m:
        rec.invoice_number = m.group(1).strip()
        _conf(rec, invoice_number="HIGH")
    else:
        _conf(rec, invoice_number="LOW")

    m = re.search(
        r"(?im)(?:invoice\s+date|date)\s*:?\s*(\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{2,4})",
        text,
    )
    if m:
        rec.invoice_date = _normalize_date(m.group(1))
        _conf(rec, invoice_date="HIGH")
    else:
        _conf(rec, invoice_date="LOW")

    m = re.search(
        r"(?im)(?:total|amount\s+due|balance\s+due|invoice\s+total)\s*:?\s*\$?\s*([\d,]+\.\d{2})",
        text,
    )
    if m:
        rec.amount = float(m.group(1).replace(",", ""))
        _conf(rec, amount="HIGH")
    else:
        m2 = re.search(r"\$\s*([\d,]+\.\d{2})", text)
        if m2:
            rec.amount = float(m2.group(1).replace(",", ""))
            _conf(rec, amount="MEDIUM")
            rec.notes = (rec.notes + " Amount inferred from first $ pattern; verify.").strip()
        else:
            _conf(rec, amount="LOW")

    first_line = next((ln.strip() for ln in text.splitlines() if ln.strip()), "")
    if first_line and len(first_line) < 80:
        rec.vendor = first_line
        _conf(rec, vendor="MEDIUM")
    else:
        _conf(rec, vendor="LOW")

    m = re.search(
        r"(?im)service\s+period[:\s]*"
        r"(\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{2,4})"
        r"\s*(?:to|-|–|through)\s*"
        r"(\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{2,4})",
        text,
    )
    if m:
        rec.service_start = _normalize_date(m.group(1))
        rec.service_end = _normalize_date(m.group(2))
        _conf(rec, service_start="HIGH", service_end="HIGH")
    else:
        for desc, months in MONTHS_BY_DESCRIPTOR.items():
            if re.search(rf"\b{re.escape(desc)}\b", text, re.I):
                rec.service_period_descriptor = desc
                rec.inferred_months = months
                _conf(rec, service_start="LOW", service_end="LOW", inferred_months="MEDIUM")
                break
        else:
            _conf(rec, service_start="LOW", service_end="LOW")
            rec.notes = (rec.notes + " No service period found; preparer review required.").strip()

    for pat, cat in CATEGORY_BY_KEYWORD:
        if pat.search(text):
            rec.category = cat
            _conf(rec, category="MEDIUM")
            break
    else:
        _conf(rec, category="LOW")

    return rec


def _normalize_date(raw: str) -> str:
    raw = raw.strip()
    try:
        return pd.to_datetime(raw, errors="raise").strftime("%Y-%m-%d")
    except (ValueError, TypeError):
        return raw


def extract_records(df: pd.DataFrame) -> list[InvoiceRecord]:
    """Passthrough for structured input — normalize columns into InvoiceRecord."""
    out = df.copy()
    out.columns = [c.strip().lower() for c in out.columns]
    records: list[InvoiceRecord] = []
    for i, row in out.iterrows():
        rec = InvoiceRecord(
            source_file=str(row.get("source_file", f"row_{i}")),
            vendor=str(row.get("vendor", "")),
            invoice_number=str(row.get("invoice_number", "")),
            invoice_date=_normalize_date(str(row.get("invoice_date", ""))) if row.get("invoice_date") else "",
            amount=float(row["amount"]) if pd.notna(row.get("amount")) else None,
            service_start=_normalize_date(str(row.get("service_start", ""))) if row.get("service_start") else "",
            service_end=_normalize_date(str(row.get("service_end", ""))) if row.get("service_end") else "",
            service_period_descriptor=str(row.get("service_period_descriptor", "")),
            category=str(row.get("category", "")),
        )
        for k in ("vendor", "invoice_number", "invoice_date", "amount", "service_start", "service_end", "category"):
            _conf(rec, **{k: "HIGH" if getattr(rec, k) not in ("", None) else "LOW"})
        records.append(rec)
    return records


def extract_from_path(path: Path) -> list[InvoiceRecord]:
    if path.is_dir():
        out: list[InvoiceRecord] = []
        for child in sorted(path.iterdir()):
            if child.is_file():
                out.extend(extract_from_path(child))
        return out
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return _parse_pdf(path)
    if suffix in (".csv",):
        return extract_records(pd.read_csv(path))
    if suffix in (".xlsx", ".xls"):
        return extract_records(pd.read_excel(path))
    return []


def records_to_dataframe(records: Iterable[InvoiceRecord]) -> pd.DataFrame:
    rows: list[dict] = []
    for r in records:
        d = asdict(r)
        conf = d.pop("confidence")
        for k, v in conf.items():
            d[f"confidence__{k}"] = v
        rows.append(d)
    return pd.DataFrame(rows)


def _cli(argv=None) -> int:
    p = argparse.ArgumentParser(description="Extract invoice fields.")
    p.add_argument("input", type=Path, help="File or folder of invoices (PDF/CSV/XLSX)")
    p.add_argument("--out", type=Path, default=Path("extracted.csv"))
    args = p.parse_args(argv)

    records = extract_from_path(args.input)
    df = records_to_dataframe(records)

    if args.out.suffix.lower() == ".csv":
        df.to_csv(args.out, index=False)
    else:
        df.to_excel(args.out, index=False)

    print(f"Extracted {len(records)} records from {args.input}")
    print(f"Wrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(_cli())
