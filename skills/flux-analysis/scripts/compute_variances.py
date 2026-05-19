"""
Compute variances of current TB vs prior TB and budget.

Input DataFrames must have columns (case-insensitive):
    account_number, account_name, balance

Output one row per account in the union of (current, prior, budget) with:
    account_number, account_name,
    bal_current, bal_prior, bal_budget,
    var_pm_dollar, var_pm_pct,    # current vs prior
    var_bud_dollar, var_bud_pct,  # current vs budget
    flag_material,                # True if exceeds threshold on either comparison
    flag_new_account,             # current present, prior absent
    flag_missing_account,         # prior present, current absent
    excluded_de_minimis           # both current and prior below de minimis

Usage:
    from compute_variances import compute
    df = compute(current_tb, prior_tb, budget_tb,
                 threshold_dollar=10_000, threshold_pct=0.05,
                 de_minimis_dollar=1_000)

Standalone CLI:
    python compute_variances.py current.csv prior.csv budget.csv --out variances.xlsx
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

REQUIRED = ("account_number", "account_name", "balance")
DEFAULT_THRESH_DOLLAR = 10_000.0
DEFAULT_THRESH_PCT = 0.05
DEFAULT_DE_MINIMIS = 1_000.0


def _prep(df: pd.DataFrame, label: str) -> pd.DataFrame:
    out = df.copy()
    out.columns = [c.strip().lower() for c in out.columns]
    missing = [c for c in REQUIRED if c not in out.columns]
    if missing:
        raise ValueError(f"{label} missing required columns: {missing}")
    out["account_number"] = out["account_number"].astype(str).str.strip()
    out["balance"] = pd.to_numeric(out["balance"], errors="coerce").fillna(0.0)
    return out[["account_number", "account_name", "balance"]].rename(
        columns={"balance": f"bal_{label}", "account_name": f"name_{label}"}
    )


def _pct(num: float, den: float) -> float:
    if den == 0:
        return float("inf") if num != 0 else 0.0
    return num / abs(den)


def compute(
    current: pd.DataFrame,
    prior: pd.DataFrame,
    budget: pd.DataFrame,
    threshold_dollar: float = DEFAULT_THRESH_DOLLAR,
    threshold_pct: float = DEFAULT_THRESH_PCT,
    de_minimis_dollar: float = DEFAULT_DE_MINIMIS,
) -> pd.DataFrame:
    c = _prep(current, "current")
    p = _prep(prior, "prior")
    b = _prep(budget, "budget")

    df = c.merge(p, on="account_number", how="outer").merge(b, on="account_number", how="outer")
    for col in ("bal_current", "bal_prior", "bal_budget"):
        df[col] = df[col].fillna(0.0)

    df["account_name"] = (
        df["name_current"].fillna(df["name_prior"]).fillna(df["name_budget"])
    )
    df = df.drop(columns=["name_current", "name_prior", "name_budget"])

    df["var_pm_dollar"] = df["bal_current"] - df["bal_prior"]
    df["var_pm_pct"] = df.apply(
        lambda r: _pct(r["var_pm_dollar"], r["bal_prior"]), axis=1
    )
    df["var_bud_dollar"] = df["bal_current"] - df["bal_budget"]
    df["var_bud_pct"] = df.apply(
        lambda r: _pct(r["var_bud_dollar"], r["bal_budget"]), axis=1
    )

    df["flag_new_account"] = (df["bal_prior"] == 0) & (df["bal_current"] != 0)
    df["flag_missing_account"] = (df["bal_current"] == 0) & (df["bal_prior"] != 0)
    df["excluded_de_minimis"] = (
        df["bal_current"].abs() < de_minimis_dollar
    ) & (df["bal_prior"].abs() < de_minimis_dollar)

    df["flag_material"] = (
        (df["var_pm_dollar"].abs() >= threshold_dollar)
        | (df["var_pm_pct"].abs() >= threshold_pct)
        | (df["var_bud_dollar"].abs() >= threshold_dollar)
        | (df["var_bud_pct"].abs() >= threshold_pct)
    ) & (~df["excluded_de_minimis"])

    cols = [
        "account_number",
        "account_name",
        "bal_current",
        "bal_prior",
        "bal_budget",
        "var_pm_dollar",
        "var_pm_pct",
        "var_bud_dollar",
        "var_bud_pct",
        "flag_material",
        "flag_new_account",
        "flag_missing_account",
        "excluded_de_minimis",
    ]
    return df[cols].sort_values("account_number").reset_index(drop=True)


def _load(path: Path) -> pd.DataFrame:
    if path.suffix.lower() == ".csv":
        return pd.read_csv(path)
    return pd.read_excel(path)


def _cli(argv=None) -> int:
    p = argparse.ArgumentParser(description="Compute flux variances.")
    p.add_argument("current", type=Path)
    p.add_argument("prior", type=Path)
    p.add_argument("budget", type=Path)
    p.add_argument("--threshold-dollar", type=float, default=DEFAULT_THRESH_DOLLAR)
    p.add_argument("--threshold-pct", type=float, default=DEFAULT_THRESH_PCT)
    p.add_argument("--de-minimis-dollar", type=float, default=DEFAULT_DE_MINIMIS)
    p.add_argument("--out", type=Path, default=Path("variances.xlsx"))
    args = p.parse_args(argv)

    df = compute(
        _load(args.current),
        _load(args.prior),
        _load(args.budget),
        threshold_dollar=args.threshold_dollar,
        threshold_pct=args.threshold_pct,
        de_minimis_dollar=args.de_minimis_dollar,
    )

    if args.out.suffix.lower() == ".csv":
        df.to_csv(args.out, index=False)
    else:
        df.to_excel(args.out, index=False)

    print(f"{len(df)} accounts | {int(df['flag_material'].sum())} material")
    print(f"Wrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(_cli())
