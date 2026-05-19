"""
Deterministic bank-to-book transaction matcher.

Matching priority (each pass consumes both sides — a matched item is removed
from the pool before the next pass):

  1. Exact amount + exact date                          confidence HIGH
  2. Exact amount + date within ±3 days                 confidence HIGH
  3. Exact amount + matching reference / check number   confidence HIGH
  4. Exact amount + fuzzy description (>=85)            confidence MEDIUM (review)

Outputs four DataFrames:
  exact_matches      — passes 1–3, auto-included in the rec
  probable_matches   — pass 4, requires human confirmation
  unmatched_bank     — bank rows with no match
  unmatched_book     — book rows with no match

Usage:
    from match_transactions import match
    result = match(bank_df, book_df)
    result.exact_matches      # pd.DataFrame
    result.probable_matches   # pd.DataFrame
    result.unmatched_bank     # pd.DataFrame
    result.unmatched_book     # pd.DataFrame

Input DataFrames must have these columns (case-insensitive):
    date         (datetime64 or parseable)
    description  (str)
    amount       (float; signed: positive = cash in, negative = cash out)
    reference    (str; check #, transaction ID, etc. — may be empty)

Standalone CLI:
    python match_transactions.py bank.csv book.csv --out matched.xlsx
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from datetime import timedelta
from pathlib import Path
from typing import Iterable

import pandas as pd

try:
    from rapidfuzz import fuzz
except ImportError:  # pragma: no cover
    fuzz = None


REQUIRED_COLS = ("date", "description", "amount", "reference")
DATE_TOLERANCE_DAYS = 3
FUZZY_DESCRIPTION_MIN = 85
AMOUNT_EPS = 0.005  # half a cent — protects against float roundtrip noise


@dataclass
class MatchResult:
    exact_matches: pd.DataFrame
    probable_matches: pd.DataFrame
    unmatched_bank: pd.DataFrame
    unmatched_book: pd.DataFrame
    stats: dict = field(default_factory=dict)


def _normalize(df: pd.DataFrame, side: str) -> pd.DataFrame:
    """Lowercase columns, validate required, parse dates, ensure reference is str."""
    out = df.copy()
    out.columns = [c.strip().lower() for c in out.columns]
    missing = [c for c in REQUIRED_COLS if c not in out.columns]
    if missing:
        raise ValueError(f"{side} missing required columns: {missing}")
    out["date"] = pd.to_datetime(out["date"], errors="coerce")
    if out["date"].isna().any():
        bad = int(out["date"].isna().sum())
        raise ValueError(f"{side}: {bad} row(s) have unparseable dates")
    out["amount"] = pd.to_numeric(out["amount"], errors="coerce")
    if out["amount"].isna().any():
        bad = int(out["amount"].isna().sum())
        raise ValueError(f"{side}: {bad} row(s) have unparseable amounts")
    out["reference"] = out["reference"].fillna("").astype(str).str.strip()
    out["description"] = out["description"].fillna("").astype(str).str.strip()
    out["_side"] = side
    out["_orig_idx"] = out.index
    return out.reset_index(drop=True)


def _amounts_equal(a: float, b: float) -> bool:
    return abs(a - b) < AMOUNT_EPS


def _index_by_amount(df: pd.DataFrame) -> dict[float, list[int]]:
    """Map rounded amount -> list of row indices. Avoids pandas groupby.get_group quirks."""
    idx: dict[float, list[int]] = {}
    for i, amt in enumerate(df["amount"]):
        idx.setdefault(round(float(amt), 2), []).append(i)
    return idx


def _pass_exact_amount_date(
    bank: pd.DataFrame, book: pd.DataFrame
) -> tuple[list[dict], set[int], set[int]]:
    matched: list[dict] = []
    used_bank: set[int] = set()
    used_book: set[int] = set()
    book_by_amt = _index_by_amount(book)
    for bi, brow in bank.iterrows():
        if bi in used_bank:
            continue
        key = round(float(brow["amount"]), 2)
        for ki in book_by_amt.get(key, []):
            if ki in used_book:
                continue
            krow = book.iloc[ki]
            if krow["date"] == brow["date"]:
                matched.append(_match_row(brow, krow, "HIGH", "exact_amount_date"))
                used_bank.add(bi)
                used_book.add(ki)
                break
    return matched, used_bank, used_book


def _pass_amount_near_date(
    bank: pd.DataFrame, book: pd.DataFrame, used_bank: set[int], used_book: set[int]
) -> list[dict]:
    matched: list[dict] = []
    book_by_amt = _index_by_amount(book)
    for bi, brow in bank.iterrows():
        if bi in used_bank:
            continue
        key = round(float(brow["amount"]), 2)
        best = None
        best_delta = None
        for ki in book_by_amt.get(key, []):
            if ki in used_book:
                continue
            krow = book.iloc[ki]
            delta = abs((brow["date"] - krow["date"]).days)
            if delta <= DATE_TOLERANCE_DAYS and (best_delta is None or delta < best_delta):
                best = (ki, krow)
                best_delta = delta
        if best is not None:
            ki, krow = best
            matched.append(_match_row(brow, krow, "HIGH", f"amount_near_date_{best_delta}d"))
            used_bank.add(bi)
            used_book.add(ki)
    return matched


def _pass_amount_reference(
    bank: pd.DataFrame, book: pd.DataFrame, used_bank: set[int], used_book: set[int]
) -> list[dict]:
    matched: list[dict] = []
    book_by_amt = _index_by_amount(book)
    for bi, brow in bank.iterrows():
        if bi in used_bank or not brow["reference"]:
            continue
        key = round(float(brow["amount"]), 2)
        for ki in book_by_amt.get(key, []):
            if ki in used_book:
                continue
            krow = book.iloc[ki]
            if not krow["reference"]:
                continue
            if brow["reference"].lower() == krow["reference"].lower():
                matched.append(_match_row(brow, krow, "HIGH", "amount_reference"))
                used_bank.add(bi)
                used_book.add(ki)
                break
    return matched


def _pass_amount_fuzzy_description(
    bank: pd.DataFrame, book: pd.DataFrame, used_bank: set[int], used_book: set[int]
) -> list[dict]:
    if fuzz is None:
        return []
    matched: list[dict] = []
    book_by_amt = _index_by_amount(book)
    for bi, brow in bank.iterrows():
        if bi in used_bank:
            continue
        key = round(float(brow["amount"]), 2)
        best_score = 0
        best = None
        for ki in book_by_amt.get(key, []):
            if ki in used_book:
                continue
            krow = book.iloc[ki]
            score = fuzz.token_set_ratio(brow["description"], krow["description"])
            if score >= FUZZY_DESCRIPTION_MIN and score > best_score:
                best_score = score
                best = (ki, krow)
        if best is not None:
            ki, krow = best
            matched.append(_match_row(brow, krow, "MEDIUM", f"fuzzy_description_{best_score}"))
            used_bank.add(bi)
            used_book.add(ki)
    return matched


def _match_row(brow: pd.Series, krow: pd.Series, confidence: str, rule: str) -> dict:
    return {
        "bank_date": brow["date"],
        "bank_description": brow["description"],
        "bank_amount": brow["amount"],
        "bank_reference": brow["reference"],
        "book_date": krow["date"],
        "book_description": krow["description"],
        "book_amount": krow["amount"],
        "book_reference": krow["reference"],
        "confidence": confidence,
        "rule": rule,
    }


def match(bank_df: pd.DataFrame, book_df: pd.DataFrame) -> MatchResult:
    bank = _normalize(bank_df, "bank")
    book = _normalize(book_df, "book")

    all_matches: list[dict] = []
    used_bank: set[int] = set()
    used_book: set[int] = set()

    m1, ub1, uk1 = _pass_exact_amount_date(bank, book)
    all_matches.extend(m1)
    used_bank |= ub1
    used_book |= uk1

    all_matches.extend(_pass_amount_near_date(bank, book, used_bank, used_book))
    all_matches.extend(_pass_amount_reference(bank, book, used_bank, used_book))

    exact = pd.DataFrame([m for m in all_matches if m["confidence"] == "HIGH"])

    probable_list = _pass_amount_fuzzy_description(bank, book, used_bank, used_book)
    probable = pd.DataFrame(probable_list)

    unmatched_bank = bank.loc[~bank.index.isin(used_bank)].drop(columns=["_side", "_orig_idx"])
    unmatched_book = book.loc[~book.index.isin(used_book)].drop(columns=["_side", "_orig_idx"])

    stats = {
        "bank_rows": len(bank),
        "book_rows": len(book),
        "exact_matches": len(exact),
        "probable_matches": len(probable),
        "unmatched_bank": len(unmatched_bank),
        "unmatched_book": len(unmatched_book),
    }

    return MatchResult(
        exact_matches=exact,
        probable_matches=probable,
        unmatched_bank=unmatched_bank.reset_index(drop=True),
        unmatched_book=unmatched_book.reset_index(drop=True),
        stats=stats,
    )


def _load(path: Path) -> pd.DataFrame:
    if path.suffix.lower() == ".csv":
        return pd.read_csv(path)
    if path.suffix.lower() in (".xlsx", ".xls"):
        return pd.read_excel(path)
    raise ValueError(f"Unsupported file type: {path.suffix}")


def _cli(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Match bank transactions to GL cash detail.")
    parser.add_argument("bank", type=Path, help="Bank statement file (CSV or XLSX)")
    parser.add_argument("book", type=Path, help="GL cash detail file (CSV or XLSX)")
    parser.add_argument("--out", type=Path, default=Path("matched.xlsx"), help="Output XLSX")
    args = parser.parse_args(argv)

    bank_df = _load(args.bank)
    book_df = _load(args.book)
    result = match(bank_df, book_df)

    with pd.ExcelWriter(args.out, engine="openpyxl") as xl:
        result.exact_matches.to_excel(xl, sheet_name="Matched", index=False)
        result.probable_matches.to_excel(xl, sheet_name="Probable_Matches", index=False)
        result.unmatched_bank.to_excel(xl, sheet_name="Unmatched_Bank", index=False)
        result.unmatched_book.to_excel(xl, sheet_name="Unmatched_Book", index=False)
        pd.DataFrame([result.stats]).to_excel(xl, sheet_name="Stats", index=False)

    for k, v in result.stats.items():
        print(f"  {k}: {v}")
    print(f"Wrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(_cli())
