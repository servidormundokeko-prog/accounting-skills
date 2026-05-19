from pathlib import Path

import pandas as pd

from file_inventory import inventory
from match_pbc import match


def test_inventory_collects_files(tmp_path: Path):
    (tmp_path / "bank_rec_apr.xlsx").write_bytes(b"")  # zero-length is fine; we just want metadata
    (tmp_path / "lease_agmt.pdf").write_bytes(b"")
    (tmp_path / "notes.txt").write_text("hello world", encoding="utf-8")

    df = inventory(tmp_path)
    names = set(df["name"])
    assert names == {"bank_rec_apr.xlsx", "lease_agmt.pdf", "notes.txt"}
    assert (df[df["name"] == "notes.txt"]["summary"].iloc[0]) == "hello world"


def test_match_classifies_complete_partial_missing_and_narrative(tmp_path: Path):
    inv = pd.DataFrame(
        [
            {
                "path": "/data/bank_reconciliation_2026-04.xlsx",
                "name": "bank_reconciliation_2026-04.xlsx",
                "extension": ".xlsx",
                "modified": "2026-05-02",
                "summary": "bank reconciliation April 2026",
            },
            {
                "path": "/data/random_notes.pdf",
                "name": "random_notes.pdf",
                "extension": ".pdf",
                "modified": "2026-05-02",
                "summary": "lunch meeting notes",
            },
        ]
    )
    reqs = pd.DataFrame(
        [
            {"request_id": "1", "description": "Bank reconciliation for operating account", "period": "2026-04", "requested_format": "xlsx"},
            {"request_id": "2", "description": "Lease agreement for HQ office", "period": "", "requested_format": "pdf"},
            {"request_id": "3", "description": "Please describe revenue recognition policy", "period": "", "requested_format": ""},
        ]
    )
    res = match(reqs, inv, threshold=0.70)
    by_id = res["status"].set_index("request_id")["status"].to_dict()
    assert by_id["1"] == "COMPLETE"
    assert by_id["2"] == "MISSING"
    assert by_id["3"] == "MANAGEMENT_RESPONSE_REQUIRED"
    assert len(res["orphans"]) == 1  # random_notes.pdf is orphan
