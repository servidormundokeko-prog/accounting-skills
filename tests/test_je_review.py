import pandas as pd

from risk_patterns import detect
from validate_je import validate


def _coa():
    return pd.DataFrame(
        [
            {"account_number": "1010", "account_name": "Cash", "account_type": "Asset", "natural_balance": "Debit", "is_active": "Y"},
            {"account_number": "4010", "account_name": "Revenue", "account_type": "Revenue", "natural_balance": "Credit", "is_active": "Y"},
            {"account_number": "6310", "account_name": "Rent", "account_type": "Expense", "natural_balance": "Debit", "is_active": "Y"},
            {"account_number": "2010", "account_name": "AP", "account_type": "Liability", "natural_balance": "Credit", "is_active": "Y"},
        ]
    )


def _je(rows):
    return pd.DataFrame(rows)


def test_validate_passes_clean_entry():
    jes = _je(
        [
            {"JE_ID": "JE_001", "Date": "2026-04-30", "Account": "6310", "Debit": 8500, "Credit": 0, "Memo": "Rent April per lease #2024-114", "Support Reference": "Lease.pdf p.2"},
            {"JE_ID": "JE_001", "Date": "2026-04-30", "Account": "2010", "Debit": 0, "Credit": 8500, "Memo": "Rent April per lease #2024-114", "Support Reference": "Lease.pdf p.2"},
        ]
    )
    result = validate(jes, coa_df=_coa(), open_periods=["2026-04"])
    row = result.iloc[0]
    assert row["failed_checks"] == ""
    assert bool(row["BALANCED"])


def test_validate_catches_unbalanced_and_bad_account_and_closed_period():
    jes = _je(
        [
            {"JE_ID": "JE_002", "Date": "2026-01-30", "Account": "6310", "Debit": 100, "Credit": 0, "Memo": "x", "Support Reference": "y"},
            {"JE_ID": "JE_002", "Date": "2026-01-30", "Account": "9999", "Debit": 0, "Credit": 50, "Memo": "x", "Support Reference": "y"},
        ]
    )
    result = validate(jes, coa_df=_coa(), open_periods=["2026-04"])
    failed = result.iloc[0]["failed_checks"]
    assert "BALANCED" in failed
    assert "ACCOUNT_VALID" in failed
    assert "DATE_IN_OPEN_PERIOD" in failed


def test_risk_round_dollar_and_revenue_manual_and_above_authority():
    jes = _je(
        [
            {"JE_ID": "JE_010", "Date": "2026-04-30", "Account": "1010", "Debit": 50000, "Credit": 0, "Memo": "m", "Support Reference": "s"},
            {"JE_ID": "JE_010", "Date": "2026-04-30", "Account": "4010", "Debit": 0, "Credit": 50000, "Memo": "m", "Support Reference": "s"},
        ]
    )
    patterns = detect(jes, preparer_authority=25_000)
    types = set(patterns["pattern"])
    assert "ROUND_DOLLAR_ABOVE_THRESHOLD" in types
    assert "REVENUE_MANUAL_ENTRY" in types
    assert "CASH_MANUAL_ENTRY" in types
    assert "ABOVE_PREPARER_AUTHORITY" in types


def test_risk_near_duplicate():
    jes = _je(
        [
            {"JE_ID": "JE_020", "Date": "2026-04-30", "Account": "6310", "Debit": 1000, "Credit": 0, "Memo": "m", "Support Reference": "s"},
            {"JE_ID": "JE_020", "Date": "2026-04-30", "Account": "2010", "Debit": 0, "Credit": 1000, "Memo": "m", "Support Reference": "s"},
            {"JE_ID": "JE_021", "Date": "2026-04-30", "Account": "6310", "Debit": 1000, "Credit": 0, "Memo": "m", "Support Reference": "s"},
            {"JE_ID": "JE_021", "Date": "2026-04-30", "Account": "2010", "Debit": 0, "Credit": 1000, "Memo": "m", "Support Reference": "s"},
        ]
    )
    patterns = detect(jes)
    dups = patterns[patterns["pattern"] == "NEAR_DUPLICATE_WITHIN_BATCH"]
    assert len(dups) == 2
