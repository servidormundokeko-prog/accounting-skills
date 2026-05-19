"""
Detect anomalies in a variance table.

Anomaly types:
    SIGN_CHANGE        balance flipped sign between current and prior
    NEW_ACCOUNT        bal_prior == 0 and bal_current != 0
    MISSING_ACCOUNT    bal_prior != 0 and bal_current == 0
    BUDGET_OVERSHOOT   |bal_current| > 2 * |bal_budget| (and budget != 0)
    BUDGET_UNDERSHOOT  |bal_current| < 0.5 * |bal_budget| (and budget != 0)
    RECURRING_VARIANCE same-direction material variance N months running
                       (requires history DataFrame; otherwise skipped)

Input: variance DataFrame produced by compute_variances.compute()

Optional: history DataFrame with columns
    period (str, e.g. "2026-02"), account_number, var_pm_dollar, flag_material

Returns a long-form DataFrame with columns:
    account_number, account_name, anomaly_type, detail

Usage:
    from anomaly_detect import detect
    anomalies = detect(variance_df)
    anomalies = detect(variance_df, history=history_df, recurring_months=2)
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

DEFAULT_RECURRING_MONTHS = 2


def detect(
    variances: pd.DataFrame,
    history: pd.DataFrame | None = None,
    recurring_months: int = DEFAULT_RECURRING_MONTHS,
) -> pd.DataFrame:
    rows: list[dict] = []

    for _, r in variances.iterrows():
        acct = r["account_number"]
        name = r.get("account_name", "")

        cur_sign = _sign(r["bal_current"])
        prior_sign = _sign(r["bal_prior"])
        if cur_sign and prior_sign and cur_sign != prior_sign:
            rows.append(
                {
                    "account_number": acct,
                    "account_name": name,
                    "anomaly_type": "SIGN_CHANGE",
                    "detail": f"prior {r['bal_prior']:,.2f} -> current {r['bal_current']:,.2f}",
                }
            )

        if r.get("flag_new_account"):
            rows.append(
                {
                    "account_number": acct,
                    "account_name": name,
                    "anomaly_type": "NEW_ACCOUNT",
                    "detail": f"first appearance, balance {r['bal_current']:,.2f}",
                }
            )

        if r.get("flag_missing_account"):
            rows.append(
                {
                    "account_number": acct,
                    "account_name": name,
                    "anomaly_type": "MISSING_ACCOUNT",
                    "detail": f"prior {r['bal_prior']:,.2f}, now zero",
                }
            )

        bud = r["bal_budget"]
        cur = r["bal_current"]
        if bud != 0:
            ratio = abs(cur) / abs(bud)
            if ratio > 2.0:
                rows.append(
                    {
                        "account_number": acct,
                        "account_name": name,
                        "anomaly_type": "BUDGET_OVERSHOOT",
                        "detail": f"|actual|/|budget| = {ratio:.2f}x ({cur:,.2f} vs {bud:,.2f})",
                    }
                )
            elif ratio < 0.5:
                rows.append(
                    {
                        "account_number": acct,
                        "account_name": name,
                        "anomaly_type": "BUDGET_UNDERSHOOT",
                        "detail": f"|actual|/|budget| = {ratio:.2f}x ({cur:,.2f} vs {bud:,.2f})",
                    }
                )

    if history is not None and not history.empty:
        rows.extend(_recurring_variances(variances, history, recurring_months))

    return pd.DataFrame(rows)


def _sign(x: float) -> int:
    if x > 0:
        return 1
    if x < 0:
        return -1
    return 0


def _recurring_variances(
    variances: pd.DataFrame, history: pd.DataFrame, n: int
) -> list[dict]:
    out: list[dict] = []
    hist = history.copy()
    hist.columns = [c.strip().lower() for c in hist.columns]
    required = {"period", "account_number", "var_pm_dollar", "flag_material"}
    if not required.issubset(hist.columns):
        return []
    hist["period"] = hist["period"].astype(str)
    hist["account_number"] = hist["account_number"].astype(str)
    hist = hist[hist["flag_material"] == True]  # noqa: E712
    hist["sign"] = hist["var_pm_dollar"].apply(_sign)

    periods_desc = sorted(hist["period"].unique(), reverse=True)[: n - 1]

    for _, r in variances.iterrows():
        if not r["flag_material"]:
            continue
        cur_sign = _sign(r["var_pm_dollar"])
        if cur_sign == 0:
            continue
        prev = hist[hist["account_number"] == r["account_number"]]
        prev = prev[prev["period"].isin(periods_desc)]
        if len(prev) < n - 1:
            continue
        if (prev["sign"] == cur_sign).all():
            out.append(
                {
                    "account_number": r["account_number"],
                    "account_name": r.get("account_name", ""),
                    "anomaly_type": "RECURRING_VARIANCE",
                    "detail": f"material variance same direction {n} months running",
                }
            )
    return out


def _load(path: Path) -> pd.DataFrame:
    if path.suffix.lower() == ".csv":
        return pd.read_csv(path)
    return pd.read_excel(path)


def _cli(argv=None) -> int:
    p = argparse.ArgumentParser(description="Detect variance anomalies.")
    p.add_argument("variances", type=Path, help="Output of compute_variances")
    p.add_argument("--history", type=Path, help="Optional history file")
    p.add_argument("--recurring-months", type=int, default=DEFAULT_RECURRING_MONTHS)
    p.add_argument("--out", type=Path, default=Path("anomalies.csv"))
    args = p.parse_args(argv)

    var_df = _load(args.variances)
    hist_df = _load(args.history) if args.history else None
    anomalies = detect(var_df, history=hist_df, recurring_months=args.recurring_months)

    if args.out.suffix.lower() == ".csv":
        anomalies.to_csv(args.out, index=False)
    else:
        anomalies.to_excel(args.out, index=False)

    if not anomalies.empty:
        print(anomalies["anomaly_type"].value_counts().to_string())
    else:
        print("No anomalies detected.")
    print(f"Wrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(_cli())
