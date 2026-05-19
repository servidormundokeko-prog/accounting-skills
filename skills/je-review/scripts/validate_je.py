"""
Mechanical validation of journal entries.

Checks (per entry, which is identified by JE_ID):
    BALANCED                sum(Debit) == sum(Credit) within $0.01
    HAS_DEBIT               at least one debit line
    HAS_CREDIT              at least one credit line
    ACCOUNT_VALID           all Account values present and active in COA
    DATE_IN_OPEN_PERIOD     Date falls within an open period (from open_periods)
    MEMO_PRESENT            non-empty memo on every line
    SUPPORT_REF_PRESENT     non-empty support reference on every line

Returns a per-entry DataFrame:
    JE_ID, total_debit, total_credit, line_count,
    BALANCED, HAS_DEBIT, HAS_CREDIT, ACCOUNT_VALID, DATE_IN_OPEN_PERIOD,
    MEMO_PRESENT, SUPPORT_REF_PRESENT,
    failed_checks   comma-separated list (empty if all pass)

Usage:
    from validate_je import validate
    coa = pd.read_csv("chart-of-accounts.csv")
    result = validate(je_df, coa_df=coa, open_periods=["2026-04"])

Standalone CLI:
    python validate_je.py jes.csv --coa coa.csv --open-periods 2026-04,2026-05 --out validated.xlsx
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

REQUIRED = ("JE_ID", "Date", "Account", "Debit", "Credit", "Memo", "Support Reference")
BALANCE_EPS = 0.01


def validate(
    jes: pd.DataFrame,
    coa_df: pd.DataFrame | None = None,
    open_periods: list[str] | None = None,
) -> pd.DataFrame:
    df = jes.copy()
    df.columns = [c.strip() for c in df.columns]
    missing = [c for c in REQUIRED if c not in df.columns]
    if missing:
        raise ValueError(f"JEs missing required columns: {missing}")

    df["Debit"] = pd.to_numeric(df["Debit"], errors="coerce").fillna(0.0)
    df["Credit"] = pd.to_numeric(df["Credit"], errors="coerce").fillna(0.0)
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    df["Account"] = df["Account"].astype(str).str.strip()
    df["Memo"] = df["Memo"].fillna("").astype(str).str.strip()
    df["Support Reference"] = df["Support Reference"].fillna("").astype(str).str.strip()

    coa_accounts: set[str] = set()
    if coa_df is not None:
        coa = coa_df.copy()
        coa.columns = [c.strip().lower() for c in coa.columns]
        if "is_active" in coa.columns:
            coa = coa[coa["is_active"].astype(str).str.upper() == "Y"]
        coa_accounts = set(coa["account_number"].astype(str).str.strip())

    open_periods_set = set(open_periods or [])

    results: list[dict] = []
    for je_id, lines in df.groupby("JE_ID"):
        total_d = lines["Debit"].sum()
        total_c = lines["Credit"].sum()
        balanced = abs(total_d - total_c) < BALANCE_EPS
        has_debit = (lines["Debit"] > 0).any()
        has_credit = (lines["Credit"] > 0).any()
        account_valid = True
        if coa_accounts:
            account_valid = bool(lines["Account"].isin(coa_accounts).all())
        if open_periods_set:
            line_periods = lines["Date"].dt.strftime("%Y-%m")
            date_in_open = bool(line_periods.isin(open_periods_set).all())
        else:
            date_in_open = True
        memo_present = bool((lines["Memo"] != "").all())
        support_present = bool((lines["Support Reference"] != "").all())

        failed = []
        if not balanced:
            failed.append("BALANCED")
        if not has_debit:
            failed.append("HAS_DEBIT")
        if not has_credit:
            failed.append("HAS_CREDIT")
        if not account_valid:
            failed.append("ACCOUNT_VALID")
        if not date_in_open:
            failed.append("DATE_IN_OPEN_PERIOD")
        if not memo_present:
            failed.append("MEMO_PRESENT")
        if not support_present:
            failed.append("SUPPORT_REF_PRESENT")

        results.append(
            {
                "JE_ID": je_id,
                "total_debit": round(total_d, 2),
                "total_credit": round(total_c, 2),
                "line_count": len(lines),
                "BALANCED": balanced,
                "HAS_DEBIT": has_debit,
                "HAS_CREDIT": has_credit,
                "ACCOUNT_VALID": account_valid,
                "DATE_IN_OPEN_PERIOD": date_in_open,
                "MEMO_PRESENT": memo_present,
                "SUPPORT_REF_PRESENT": support_present,
                "failed_checks": ",".join(failed),
            }
        )

    return pd.DataFrame(results)


def _load(path: Path) -> pd.DataFrame:
    if path.suffix.lower() == ".csv":
        return pd.read_csv(path)
    return pd.read_excel(path)


def _cli(argv=None) -> int:
    p = argparse.ArgumentParser(description="Validate JEs.")
    p.add_argument("jes", type=Path)
    p.add_argument("--coa", type=Path)
    p.add_argument("--open-periods", default="", help="Comma-separated YYYY-MM")
    p.add_argument("--out", type=Path, default=Path("validated.csv"))
    args = p.parse_args(argv)

    je_df = _load(args.jes)
    coa = _load(args.coa) if args.coa else None
    periods = [s.strip() for s in args.open_periods.split(",") if s.strip()]

    result = validate(je_df, coa_df=coa, open_periods=periods or None)

    if args.out.suffix.lower() == ".csv":
        result.to_csv(args.out, index=False)
    else:
        result.to_excel(args.out, index=False)

    rejects = int((result["failed_checks"] != "").sum())
    print(f"{len(result)} entries validated | {rejects} with failures")
    print(f"Wrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(_cli())
