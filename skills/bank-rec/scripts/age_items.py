"""
Age unmatched reconciling items relative to period end.

Buckets:
    0-30 days
    31-60 days
    61+ days     <- escalate per firm-config.materiality.bank_rec_old_item_days

Usage:
    from age_items import age
    aged = age(unmatched_df, period_end="2026-04-30")
    aged["age_days"]    # int
    aged["age_bucket"]  # "0-30" | "31-60" | "61+"
    aged["flag"]        # "" | "OLD_ITEM"

Standalone CLI:
    python age_items.py unmatched.csv --period-end 2026-04-30 --out aged.csv
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

DEFAULT_OLD_ITEM_DAYS = 60


def age(
    df: pd.DataFrame,
    period_end: str | pd.Timestamp,
    date_col: str = "date",
    old_item_days: int = DEFAULT_OLD_ITEM_DAYS,
) -> pd.DataFrame:
    if df.empty:
        out = df.copy()
        out["age_days"] = pd.Series(dtype="int64")
        out["age_bucket"] = pd.Series(dtype="object")
        out["flag"] = pd.Series(dtype="object")
        return out

    period_end_ts = pd.Timestamp(period_end).normalize()
    out = df.copy()
    if date_col not in out.columns:
        raise ValueError(f"Column '{date_col}' not found in input")
    out[date_col] = pd.to_datetime(out[date_col], errors="coerce")
    if out[date_col].isna().any():
        bad = int(out[date_col].isna().sum())
        raise ValueError(f"{bad} row(s) have unparseable dates in '{date_col}'")

    out["age_days"] = (period_end_ts - out[date_col]).dt.days.clip(lower=0)
    out["age_bucket"] = out["age_days"].apply(_bucket)
    out["flag"] = out["age_days"].apply(lambda d: "OLD_ITEM" if d > old_item_days else "")
    return out


def _bucket(days: int) -> str:
    if days <= 30:
        return "0-30"
    if days <= 60:
        return "31-60"
    return "61+"


def _cli(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Age reconciling items.")
    parser.add_argument("input", type=Path, help="CSV or XLSX of unmatched items")
    parser.add_argument("--period-end", required=True, help="Period end date YYYY-MM-DD")
    parser.add_argument("--date-col", default="date", help="Name of the date column")
    parser.add_argument(
        "--old-item-days",
        type=int,
        default=DEFAULT_OLD_ITEM_DAYS,
        help="Days threshold for OLD_ITEM flag",
    )
    parser.add_argument("--out", type=Path, default=Path("aged.csv"), help="Output path")
    args = parser.parse_args(argv)

    if args.input.suffix.lower() == ".csv":
        df = pd.read_csv(args.input)
    else:
        df = pd.read_excel(args.input)

    aged = age(df, args.period_end, args.date_col, args.old_item_days)

    if args.out.suffix.lower() == ".csv":
        aged.to_csv(args.out, index=False)
    else:
        aged.to_excel(args.out, index=False)

    print(f"Aged {len(aged)} rows")
    print(aged["age_bucket"].value_counts().to_string())
    print(f"OLD_ITEM count: {(aged['flag'] == 'OLD_ITEM').sum()}")
    print(f"Wrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(_cli())
