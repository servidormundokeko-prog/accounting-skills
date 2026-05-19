import pandas as pd

from anomaly_detect import detect
from compute_variances import compute


def _tb(rows):
    return pd.DataFrame(rows, columns=["account_number", "account_name", "balance"])


def test_material_flag_triggers_on_dollar_threshold():
    current = _tb([("6200", "Marketing", 60_000)])
    prior = _tb([("6200", "Marketing", 30_000)])
    budget = _tb([("6200", "Marketing", 35_000)])
    df = compute(current, prior, budget, threshold_dollar=10_000, threshold_pct=0.50)
    assert df["flag_material"].iloc[0] is True or df["flag_material"].iloc[0] == True  # noqa: E712


def test_de_minimis_excludes_small_accounts():
    current = _tb([("6700", "Office Supplies", 250)])
    prior = _tb([("6700", "Office Supplies", 100)])
    budget = _tb([("6700", "Office Supplies", 200)])
    df = compute(current, prior, budget, de_minimis_dollar=1_000)
    assert bool(df["excluded_de_minimis"].iloc[0])
    assert not bool(df["flag_material"].iloc[0])


def test_new_and_missing_account_flags():
    current = _tb([("6800", "Depreciation", 5_000)])
    prior = _tb([("6810", "Amortization", 3_000)])
    budget = _tb([])
    df = compute(current, prior, budget)
    new_acct = df[df["account_number"] == "6800"].iloc[0]
    missing_acct = df[df["account_number"] == "6810"].iloc[0]
    assert bool(new_acct["flag_new_account"])
    assert bool(missing_acct["flag_missing_account"])


def test_anomaly_sign_change_and_budget_overshoot():
    current = _tb([("4010", "Revenue Sub", 100_000), ("6200", "Marketing", 50_000)])
    prior = _tb([("4010", "Revenue Sub", -50_000), ("6200", "Marketing", 20_000)])
    budget = _tb([("4010", "Revenue Sub", 90_000), ("6200", "Marketing", 20_000)])
    vars_ = compute(current, prior, budget, threshold_dollar=10_000, threshold_pct=0.05)
    an = detect(vars_)
    types = set(an["anomaly_type"])
    assert "SIGN_CHANGE" in types
    assert "BUDGET_OVERSHOOT" in types
