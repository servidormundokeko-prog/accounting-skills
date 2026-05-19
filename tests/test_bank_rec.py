from datetime import datetime

import pandas as pd

from age_items import age
from match_transactions import match


def test_exact_amount_date_matches():
    bank = pd.DataFrame(
        [
            {"date": "2026-04-03", "description": "ACH CUSTOMER A", "amount": 1500.00, "reference": "TXN001"},
            {"date": "2026-04-05", "description": "WIRE OUT", "amount": -8500.00, "reference": "TXN002"},
        ]
    )
    book = pd.DataFrame(
        [
            {"date": "2026-04-03", "description": "Cust A payment", "amount": 1500.00, "reference": "DEP001"},
            {"date": "2026-04-05", "description": "Rent payment", "amount": -8500.00, "reference": "CHK1041"},
        ]
    )
    res = match(bank, book)
    assert len(res.exact_matches) == 2
    assert res.unmatched_bank.empty
    assert res.unmatched_book.empty


def test_amount_near_date_match_within_window():
    bank = pd.DataFrame(
        [{"date": "2026-04-03", "description": "DEPOSIT", "amount": 500.00, "reference": ""}]
    )
    book = pd.DataFrame(
        [{"date": "2026-04-01", "description": "Deposit batch", "amount": 500.00, "reference": ""}]
    )
    res = match(bank, book)
    assert len(res.exact_matches) == 1
    assert "amount_near_date" in res.exact_matches.iloc[0]["rule"]


def test_unmatched_bank_and_book_separated():
    bank = pd.DataFrame(
        [{"date": "2026-04-15", "description": "SERVICE CHARGE", "amount": -35.00, "reference": ""}]
    )
    book = pd.DataFrame(
        [{"date": "2026-04-20", "description": "Check 1042", "amount": -1200.00, "reference": "CHK1042"}]
    )
    res = match(bank, book)
    assert res.exact_matches.empty
    assert len(res.unmatched_bank) == 1
    assert len(res.unmatched_book) == 1


def test_age_buckets():
    df = pd.DataFrame(
        [
            {"date": "2026-04-25", "amount": 100},  # 5 days
            {"date": "2026-03-15", "amount": 200},  # 46 days
            {"date": "2026-01-10", "amount": 300},  # 110 days -> old
        ]
    )
    aged = age(df, period_end="2026-04-30")
    assert list(aged["age_bucket"]) == ["0-30", "31-60", "61+"]
    assert aged["flag"].iloc[2] == "OLD_ITEM"
    assert aged["flag"].iloc[0] == ""
