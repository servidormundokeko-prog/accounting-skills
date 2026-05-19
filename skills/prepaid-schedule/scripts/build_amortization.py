"""
Build a formula-driven prepaid amortization schedule.

Produces an XLSX with three tabs:

  Inputs    one row per prepaid item; data tab. Manual edits go here.
  Schedule  long-form table: one row per (item, month). Amounts are FORMULAS
            referencing the Inputs tab — never computed values pasted in.
  Summary   pivot-like roll-forward by month.

Each `Schedule` row's `amortization_amount` cell is of the form
    =Inputs!E{row}/Inputs!F{row}
(amount divided by months), except the final month per item which absorbs
cumulative rounding via
    =Inputs!E{row} - SUMIFS(...prior months for this item...)
so the schedule fully closes to zero.

Usage:
    from build_amortization import build
    build(items_df, out_path=Path("prepaid.xlsx"), period_close="2026-04-30")

Items DataFrame must have columns (case-insensitive):
    item_id, vendor, invoice_number, invoice_date,
    amount, service_start, service_end, expense_account

Standalone CLI:
    python build_amortization.py items.csv --period-close 2026-04-30 --out prepaid.xlsx
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

import pandas as pd
from openpyxl import Workbook
from openpyxl.utils import get_column_letter

REQUIRED = (
    "item_id",
    "vendor",
    "invoice_number",
    "invoice_date",
    "amount",
    "service_start",
    "service_end",
    "expense_account",
)

PREPAID_ACCOUNT = "1220"  # default; override via column or arg


@dataclass
class BuildResult:
    out_path: Path
    items: int
    schedule_rows: int


def _normalize(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out.columns = [c.strip().lower() for c in out.columns]
    missing = [c for c in REQUIRED if c not in out.columns]
    if missing:
        raise ValueError(f"Items missing required columns: {missing}")
    out["service_start"] = pd.to_datetime(out["service_start"], errors="coerce")
    out["service_end"] = pd.to_datetime(out["service_end"], errors="coerce")
    out["invoice_date"] = pd.to_datetime(out["invoice_date"], errors="coerce")
    out["amount"] = pd.to_numeric(out["amount"], errors="coerce")
    if out["service_start"].isna().any() or out["service_end"].isna().any():
        bad = int((out["service_start"].isna() | out["service_end"].isna()).sum())
        raise ValueError(f"{bad} item(s) missing service period; resolve before scheduling")
    if (out["service_end"] < out["service_start"]).any():
        raise ValueError("service_end before service_start in one or more items")
    return out.reset_index(drop=True)


def _month_range(start: pd.Timestamp, end: pd.Timestamp) -> list[pd.Timestamp]:
    return list(pd.date_range(start.to_period("M").to_timestamp(), end.to_period("M").to_timestamp(), freq="MS"))


def build(items_df: pd.DataFrame, out_path: Path, period_close: str | None = None) -> BuildResult:
    items = _normalize(items_df)

    wb = Workbook()

    # Inputs tab
    ws_in = wb.active
    ws_in.title = "Inputs"
    in_headers = [
        "item_id",
        "vendor",
        "invoice_number",
        "invoice_date",
        "amount",
        "months",
        "service_start",
        "service_end",
        "prepaid_account",
        "expense_account",
        "notes",
    ]
    ws_in.append(in_headers)

    items["months"] = items.apply(
        lambda r: len(_month_range(r["service_start"], r["service_end"])), axis=1
    )
    items["prepaid_account"] = items.get("prepaid_account", pd.Series([PREPAID_ACCOUNT] * len(items)))

    for _, r in items.iterrows():
        ws_in.append(
            [
                r["item_id"],
                r["vendor"],
                r["invoice_number"],
                r["invoice_date"].strftime("%Y-%m-%d") if pd.notna(r["invoice_date"]) else "",
                float(r["amount"]),
                int(r["months"]),
                r["service_start"].strftime("%Y-%m-%d"),
                r["service_end"].strftime("%Y-%m-%d"),
                r.get("prepaid_account", PREPAID_ACCOUNT),
                r["expense_account"],
                r.get("notes", ""),
            ]
        )

    col_amount = get_column_letter(in_headers.index("amount") + 1)        # E
    col_months = get_column_letter(in_headers.index("months") + 1)        # F

    # Schedule tab — formula-driven
    ws_sch = wb.create_sheet("Schedule")
    sch_headers = [
        "item_id",
        "month",
        "expense_account",
        "amortization_amount",
        "is_final_month",
    ]
    ws_sch.append(sch_headers)

    schedule_rows = 0
    item_to_input_row: dict[str, int] = {}
    for i, r in items.iterrows():
        input_row = i + 2  # 1 header + 1-based
        item_to_input_row[str(r["item_id"])] = input_row

        months = _month_range(r["service_start"], r["service_end"])
        for j, month_start in enumerate(months):
            is_final = j == len(months) - 1
            sch_row_excel = ws_sch.max_row + 1
            if is_final:
                prior_rows_start = sch_row_excel - len(months) + 1
                prior_rows_end = sch_row_excel - 1
                formula = (
                    f"=Inputs!{col_amount}{input_row}"
                    f"-SUMIFS(D{prior_rows_start}:D{prior_rows_end},"
                    f"A{prior_rows_start}:A{prior_rows_end},A{sch_row_excel})"
                )
            else:
                formula = f"=Inputs!{col_amount}{input_row}/Inputs!{col_months}{input_row}"
            ws_sch.append(
                [
                    r["item_id"],
                    month_start.strftime("%Y-%m-%d"),
                    r["expense_account"],
                    None,
                    "Y" if is_final else "",
                ]
            )
            ws_sch.cell(row=sch_row_excel, column=4).value = formula
            schedule_rows += 1

    # Summary tab — roll-forward by month
    ws_sum = wb.create_sheet("Summary_By_Month")
    ws_sum.append(["month", "amortization_total"])
    months_in_schedule = sorted({pd.Timestamp(c).strftime("%Y-%m") for c in {row[1].value for row in ws_sch.iter_rows(min_row=2, max_col=2)}})
    for m in months_in_schedule:
        ws_sum.append(
            [
                m,
                f'=SUMPRODUCT((LEFT(Schedule!B2:B{ws_sch.max_row},7)="{m}")*Schedule!D2:D{ws_sch.max_row})',
            ]
        )

    # JEs_Proposed tab — recognition + first-month amortization templates
    ws_je = wb.create_sheet("JEs_Proposed")
    ws_je.append(
        ["JE_ID", "Date", "Account", "Debit", "Credit", "Memo", "Support Reference", "Preparer", "Reviewer"]
    )
    je_seq = 1
    for _, r in items.iterrows():
        memo = (
            f"Capitalize prepaid: {r['vendor']} inv {r['invoice_number']}, "
            f"service {r['service_start'].strftime('%Y-%m-%d')} to {r['service_end'].strftime('%Y-%m-%d')}, "
            f"{int(r['months'])} months"
        )
        ws_je.append([f"JE_{je_seq:03d}", r["invoice_date"].strftime("%Y-%m-%d"), r.get("prepaid_account", PREPAID_ACCOUNT), float(r["amount"]), None, memo, f"{r['invoice_number']}", "", ""])
        ws_je.append([f"JE_{je_seq:03d}", r["invoice_date"].strftime("%Y-%m-%d"), "2010", None, float(r["amount"]), memo, f"{r['invoice_number']}", "", ""])
        je_seq += 1

    if period_close:
        period_close_ts = pd.Timestamp(period_close)
        # Aggregate first-month amortization by expense account for the period
        first_month = period_close_ts.to_period("M").to_timestamp().strftime("%Y-%m-%d")
        by_acct: dict[str, float] = {}
        for _, r in items.iterrows():
            if r["service_start"].to_period("M") <= period_close_ts.to_period("M") <= r["service_end"].to_period("M"):
                per_month = float(r["amount"]) / int(r["months"])
                by_acct[r["expense_account"]] = by_acct.get(r["expense_account"], 0.0) + per_month
        total = sum(by_acct.values())
        if total > 0:
            for acct, amt in by_acct.items():
                ws_je.append(
                    [f"JE_{je_seq:03d}", period_close, acct, round(amt, 2), None,
                     f"Amortize prepaid expenses for {period_close_ts.strftime('%Y-%m')}", "Prepaid_Schedule", "", ""]
                )
            ws_je.append(
                [f"JE_{je_seq:03d}", period_close, PREPAID_ACCOUNT, None, round(total, 2),
                 f"Amortize prepaid expenses for {period_close_ts.strftime('%Y-%m')}", "Prepaid_Schedule", "", ""]
            )

    wb.save(out_path)
    return BuildResult(out_path=out_path, items=len(items), schedule_rows=schedule_rows)


def _load(path: Path) -> pd.DataFrame:
    if path.suffix.lower() == ".csv":
        return pd.read_csv(path)
    return pd.read_excel(path)


def _cli(argv=None) -> int:
    p = argparse.ArgumentParser(description="Build prepaid amortization schedule.")
    p.add_argument("items", type=Path)
    p.add_argument("--period-close", help="YYYY-MM-DD; used for current-month amortization JE")
    p.add_argument("--out", type=Path, default=Path("prepaid.xlsx"))
    args = p.parse_args(argv)

    result = build(_load(args.items), args.out, period_close=args.period_close)
    print(f"Built schedule for {result.items} item(s) -> {result.schedule_rows} schedule rows")
    print(f"Wrote {result.out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(_cli())
