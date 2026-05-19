"""
Detect risk patterns in proposed journal entries.

Patterns:
    ROUND_DOLLAR_ABOVE_THRESHOLD
        absolute entry size >= round_dollar_threshold AND amount is whole
        hundreds/thousands (no cents and divisible by 100)
    REVENUE_MANUAL_ENTRY
        any line credits a revenue account (4xxx) and abs(amount) >=
        revenue_manual_threshold
    CASH_MANUAL_ENTRY
        any line touches a cash account (10xx) and abs(amount) >=
        cash_manual_threshold (manual = not from sub-ledger auto-posting,
        which is approximated here by assuming JEs passed in are manual)
    NEAR_DUPLICATE_WITHIN_BATCH
        different JE_IDs in this batch share account set, dates, and same
        total amount within $0.01
    REVERSAL_OF_PRIOR
        within this batch or prior history, opposite signed lines on the
        same accounts and same amount within 90 days
    ABOVE_PREPARER_AUTHORITY
        abs(entry_amount) > preparer_authority

Returns long-form DataFrame:
    JE_ID, pattern, detail

Usage:
    from risk_patterns import detect
    patterns = detect(jes_df,
                      round_dollar_threshold=10_000,
                      revenue_manual_threshold=5_000,
                      cash_manual_threshold=5_000,
                      preparer_authority=25_000,
                      history_df=None)
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

DEFAULT_ROUND_DOLLAR = 10_000.0
DEFAULT_REVENUE_MANUAL = 5_000.0
DEFAULT_CASH_MANUAL = 5_000.0
DEFAULT_PREPARER_AUTHORITY = 25_000.0
REVERSAL_WINDOW_DAYS = 90


def detect(
    jes: pd.DataFrame,
    round_dollar_threshold: float = DEFAULT_ROUND_DOLLAR,
    revenue_manual_threshold: float = DEFAULT_REVENUE_MANUAL,
    cash_manual_threshold: float = DEFAULT_CASH_MANUAL,
    preparer_authority: float = DEFAULT_PREPARER_AUTHORITY,
    history_df: pd.DataFrame | None = None,
) -> pd.DataFrame:
    df = jes.copy()
    df.columns = [c.strip() for c in df.columns]
    df["Debit"] = pd.to_numeric(df["Debit"], errors="coerce").fillna(0.0)
    df["Credit"] = pd.to_numeric(df["Credit"], errors="coerce").fillna(0.0)
    df["Account"] = df["Account"].astype(str).str.strip()
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")

    rows: list[dict] = []

    grouped = list(df.groupby("JE_ID"))

    for je_id, lines in grouped:
        entry_amount = max(lines["Debit"].sum(), lines["Credit"].sum())
        if entry_amount >= round_dollar_threshold and entry_amount == int(entry_amount) and int(entry_amount) % 100 == 0:
            rows.append(
                {
                    "JE_ID": je_id,
                    "pattern": "ROUND_DOLLAR_ABOVE_THRESHOLD",
                    "detail": f"${entry_amount:,.2f}",
                }
            )

        for _, ln in lines.iterrows():
            acct = ln["Account"]
            credit = ln["Credit"]
            debit = ln["Debit"]
            line_amt = max(credit, debit)
            if acct.startswith("4") and len(acct) == 4 and line_amt >= revenue_manual_threshold:
                rows.append(
                    {
                        "JE_ID": je_id,
                        "pattern": "REVENUE_MANUAL_ENTRY",
                        "detail": f"Account {acct}, ${line_amt:,.2f}",
                    }
                )
            if acct.startswith("10") and len(acct) == 4 and line_amt >= cash_manual_threshold:
                rows.append(
                    {
                        "JE_ID": je_id,
                        "pattern": "CASH_MANUAL_ENTRY",
                        "detail": f"Account {acct}, ${line_amt:,.2f}",
                    }
                )

        if entry_amount > preparer_authority:
            rows.append(
                {
                    "JE_ID": je_id,
                    "pattern": "ABOVE_PREPARER_AUTHORITY",
                    "detail": f"${entry_amount:,.2f} > preparer authority ${preparer_authority:,.2f}",
                }
            )

    rows.extend(_near_duplicates(grouped))
    rows.extend(_reversals(grouped, history_df))

    return pd.DataFrame(rows)


def _near_duplicates(grouped: list) -> list[dict]:
    out: list[dict] = []
    sigs: dict[tuple, list[str]] = {}
    for je_id, lines in grouped:
        accounts = tuple(sorted(lines["Account"].unique()))
        date = lines["Date"].iloc[0]
        total = round(max(lines["Debit"].sum(), lines["Credit"].sum()), 2)
        key = (accounts, date.isoformat() if pd.notna(date) else "", total)
        sigs.setdefault(key, []).append(str(je_id))
    for key, ids in sigs.items():
        if len(ids) > 1:
            for jid in ids:
                others = [i for i in ids if i != jid]
                out.append(
                    {
                        "JE_ID": jid,
                        "pattern": "NEAR_DUPLICATE_WITHIN_BATCH",
                        "detail": f"Same accounts/date/amount as: {', '.join(others)}",
                    }
                )
    return out


def _reversals(grouped: list, history_df: pd.DataFrame | None) -> list[dict]:
    out: list[dict] = []
    candidates = []
    for je_id, lines in grouped:
        for _, ln in lines.iterrows():
            candidates.append(
                (
                    str(je_id),
                    ln["Account"],
                    ln["Date"],
                    float(ln["Debit"]) - float(ln["Credit"]),
                )
            )

    history = []
    if history_df is not None and not history_df.empty:
        h = history_df.copy()
        h.columns = [c.strip() for c in h.columns]
        h["Debit"] = pd.to_numeric(h.get("Debit", 0), errors="coerce").fillna(0.0)
        h["Credit"] = pd.to_numeric(h.get("Credit", 0), errors="coerce").fillna(0.0)
        h["Date"] = pd.to_datetime(h["Date"], errors="coerce")
        for _, r in h.iterrows():
            history.append(
                (
                    str(r.get("JE_ID", "")),
                    str(r["Account"]),
                    r["Date"],
                    float(r["Debit"]) - float(r["Credit"]),
                )
            )

    for je_id, acct, date, signed_amt in candidates:
        if signed_amt == 0:
            continue
        for h_id, h_acct, h_date, h_signed in history:
            if h_id == je_id or h_acct != acct or pd.isna(h_date) or pd.isna(date):
                continue
            if abs((date - h_date).days) > REVERSAL_WINDOW_DAYS:
                continue
            if abs(signed_amt + h_signed) < 0.01 and signed_amt != 0:
                out.append(
                    {
                        "JE_ID": je_id,
                        "pattern": "REVERSAL_OF_PRIOR",
                        "detail": f"Reverses prior {h_id} on account {acct} ({h_signed:+.2f}); confirm memo references original",
                    }
                )
                break
    return out


def _load(path: Path) -> pd.DataFrame:
    if path.suffix.lower() == ".csv":
        return pd.read_csv(path)
    return pd.read_excel(path)


def _cli(argv=None) -> int:
    p = argparse.ArgumentParser(description="Detect JE risk patterns.")
    p.add_argument("jes", type=Path)
    p.add_argument("--history", type=Path)
    p.add_argument("--round-dollar-threshold", type=float, default=DEFAULT_ROUND_DOLLAR)
    p.add_argument("--revenue-manual-threshold", type=float, default=DEFAULT_REVENUE_MANUAL)
    p.add_argument("--cash-manual-threshold", type=float, default=DEFAULT_CASH_MANUAL)
    p.add_argument("--preparer-authority", type=float, default=DEFAULT_PREPARER_AUTHORITY)
    p.add_argument("--out", type=Path, default=Path("risk_patterns.csv"))
    args = p.parse_args(argv)

    jes = _load(args.jes)
    history = _load(args.history) if args.history else None
    patterns = detect(
        jes,
        round_dollar_threshold=args.round_dollar_threshold,
        revenue_manual_threshold=args.revenue_manual_threshold,
        cash_manual_threshold=args.cash_manual_threshold,
        preparer_authority=args.preparer_authority,
        history_df=history,
    )

    if args.out.suffix.lower() == ".csv":
        patterns.to_csv(args.out, index=False)
    else:
        patterns.to_excel(args.out, index=False)

    if not patterns.empty:
        print(patterns["pattern"].value_counts().to_string())
    else:
        print("No risk patterns detected.")
    print(f"Wrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(_cli())
