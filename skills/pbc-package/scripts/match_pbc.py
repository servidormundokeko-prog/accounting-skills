"""
Match PBC request items to support files in an inventory.

Inputs:
    requests_df  — columns (case-insensitive): request_id, description,
                   period (optional), requested_format (optional)
    inventory_df — output of file_inventory.inventory()

Scoring (each component 0.0-1.0, weighted, then summed):
    description_similarity     0.55  fuzzy match of request description vs
                                     (filename + content summary)
    period_match               0.20  request period appears in filename or
                                     modified-date matches
    format_match               0.15  request format (doc/spreadsheet/narrative)
                                     matches file extension category
    keyword_signal             0.10  domain-keyword overlap

Each request gets a list of candidate matches with scores. A match >= threshold
is `COMPLETE`; lower scores are `PARTIAL`; no candidates is `MISSING`.
Narrative requests (detected by keywords) are `MANAGEMENT_RESPONSE_REQUIRED`.

Usage:
    from match_pbc import match
    result = match(requests_df, inventory_df, threshold=0.70)
    result["matches"]      # long-form DataFrame of request_id x file_path x score
    result["status"]       # per-request status + best-match info
    result["orphans"]      # files not matched to any request
    result["duplicates"]   # requests with multiple matches above threshold
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import pandas as pd

try:
    from rapidfuzz import fuzz
except ImportError:  # pragma: no cover
    fuzz = None


W_DESC = 0.55
W_PERIOD = 0.20
W_FORMAT = 0.15
W_KEYWORD = 0.10
DEFAULT_THRESHOLD = 0.70
# Minimum description similarity before a file counts as a candidate at all.
# Below this, format/period alignment is noise — a random PDF shouldn't surface
# as a partial match for a lease request just because both are PDFs.
MIN_DESC_SIM_TO_SURFACE = 0.40

NARRATIVE_KEYWORDS = ("explain", "describe", "narrative", "memo", "policy", "summary")
SPREADSHEET_EXT = {".xlsx", ".xls", ".csv"}
DOCUMENT_EXT = {".pdf", ".docx"}

DOMAIN_KEYWORDS = (
    "reconciliation",
    "roll",
    "schedule",
    "trial balance",
    "tb",
    "general ledger",
    "gl",
    "subledger",
    "support",
    "invoice",
    "lease",
    "loan",
    "agreement",
    "confirmation",
    "bank statement",
    "depreciation",
    "amortization",
    "accrual",
    "prepaid",
    "deferred",
    "headcount",
    "payroll",
    "stock comp",
    "equity",
    "tax",
)


def match(
    requests: pd.DataFrame,
    inventory: pd.DataFrame,
    threshold: float = DEFAULT_THRESHOLD,
) -> dict:
    if fuzz is None:
        raise RuntimeError("rapidfuzz not installed; install requirements.txt")

    req = _normalize_requests(requests)
    inv = _normalize_inventory(inventory)

    matches_rows: list[dict] = []
    status_rows: list[dict] = []
    matched_files: set[str] = set()

    for _, r in req.iterrows():
        is_narrative = _is_narrative(r["description"])
        candidates: list[dict] = []
        if not is_narrative:
            for _, f in inv.iterrows():
                score, desc_sim = _score(r, f)
                if desc_sim < MIN_DESC_SIM_TO_SURFACE:
                    continue
                if score > 0.20:  # don't bother surfacing trivial matches
                    candidates.append(
                        {
                            "request_id": r["request_id"],
                            "file_path": f["path"],
                            "file_name": f["name"],
                            "score": round(score, 3),
                            "above_threshold": score >= threshold,
                        }
                    )
            candidates.sort(key=lambda x: x["score"], reverse=True)
            matches_rows.extend(candidates)

        if is_narrative:
            status = "MANAGEMENT_RESPONSE_REQUIRED"
            best_score = None
            best_file = ""
        elif not candidates:
            status = "MISSING"
            best_score = None
            best_file = ""
        else:
            best = candidates[0]
            best_score = best["score"]
            best_file = best["file_name"]
            if best_score >= threshold:
                status = "COMPLETE"
                for c in candidates:
                    if c["above_threshold"]:
                        matched_files.add(c["file_path"])
            else:
                status = "PARTIAL"

        status_rows.append(
            {
                "request_id": r["request_id"],
                "description": r["description"],
                "status": status,
                "best_match_file": best_file,
                "best_match_score": best_score,
            }
        )

    matches_df = pd.DataFrame(matches_rows)
    status_df = pd.DataFrame(status_rows)

    orphans = inv[~inv["path"].isin(matched_files)][["name", "path", "summary"]].copy()

    if not matches_df.empty:
        dup_groups = (
            matches_df[matches_df["above_threshold"]]
            .groupby("request_id")
            .size()
            .reset_index(name="match_count")
        )
        duplicates = dup_groups[dup_groups["match_count"] > 1]
    else:
        duplicates = pd.DataFrame(columns=["request_id", "match_count"])

    return {
        "matches": matches_df,
        "status": status_df,
        "orphans": orphans.reset_index(drop=True),
        "duplicates": duplicates.reset_index(drop=True),
    }


def _normalize_requests(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out.columns = [c.strip().lower() for c in out.columns]
    for col in ("request_id", "description"):
        if col not in out.columns:
            raise ValueError(f"Requests missing column: {col}")
    out["description"] = out["description"].fillna("").astype(str)
    if "period" not in out.columns:
        out["period"] = ""
    if "requested_format" not in out.columns:
        out["requested_format"] = ""
    return out


def _normalize_inventory(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out.columns = [c.strip().lower() for c in out.columns]
    for col in ("path", "name", "extension", "modified", "summary"):
        if col not in out.columns:
            raise ValueError(f"Inventory missing column: {col}")
    out["summary"] = out["summary"].fillna("").astype(str)
    return out


def _is_narrative(description: str) -> bool:
    d = description.lower()
    return any(k in d for k in NARRATIVE_KEYWORDS)


def _tokenize_for_match(s: str) -> str:
    """Strip extension and replace _, -, . with spaces so fuzzy matchers see real tokens."""
    base = Path(s).stem
    for ch in ("_", "-", "."):
        base = base.replace(ch, " ")
    return base


def _score(req: pd.Series, f: pd.Series) -> tuple[float, float]:
    """Return (total_score, desc_sim). desc_sim is exposed so callers can gate on it."""
    desc = req["description"]
    # Filenames often pack tokens with _ - . — normalize so fuzz tokenizes them properly.
    haystack = _tokenize_for_match(f["name"]) + " " + f["summary"]
    desc_sim = fuzz.token_set_ratio(desc, haystack) / 100.0

    period_score = 0.0
    period = str(req.get("period") or "").strip()
    if period:
        if period in f["name"] or period in f["summary"]:
            period_score = 1.0
        elif _period_in_modified(period, f["modified"]):
            period_score = 0.6

    fmt_score = _format_match(req.get("requested_format", ""), f["extension"], desc)

    kw_score = _keyword_overlap(desc, haystack)

    total = W_DESC * desc_sim + W_PERIOD * period_score + W_FORMAT * fmt_score + W_KEYWORD * kw_score
    return total, desc_sim


def _period_in_modified(period: str, modified: str) -> bool:
    m = re.search(r"(\d{4})-(\d{2})", period)
    if not m:
        return False
    return modified.startswith(f"{m.group(1)}-{m.group(2)}")


def _format_match(requested_format: str, ext: str, description: str) -> float:
    rf = (requested_format or "").lower()
    d = description.lower()
    wants_spreadsheet = (
        rf in ("xlsx", "excel", "spreadsheet")
        or any(k in d for k in ("schedule", "roll", "reconciliation", "tb", "trial balance"))
    )
    wants_document = rf in ("pdf", "doc", "docx", "document") or any(
        k in d for k in ("agreement", "contract", "invoice", "policy")
    )
    if wants_spreadsheet and ext in SPREADSHEET_EXT:
        return 1.0
    if wants_document and ext in DOCUMENT_EXT:
        return 1.0
    if not wants_spreadsheet and not wants_document:
        return 0.5  # neutral
    return 0.0


def _keyword_overlap(description: str, haystack: str) -> float:
    d = description.lower()
    h = haystack.lower()
    hits = sum(1 for kw in DOMAIN_KEYWORDS if kw in d and kw in h)
    if hits == 0:
        return 0.0
    return min(1.0, hits / 3.0)


def _load(path: Path) -> pd.DataFrame:
    if path.suffix.lower() == ".csv":
        return pd.read_csv(path)
    return pd.read_excel(path)


def _cli(argv=None) -> int:
    p = argparse.ArgumentParser(description="Match PBC requests to inventory.")
    p.add_argument("requests", type=Path)
    p.add_argument("inventory", type=Path, help="Output of file_inventory")
    p.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD)
    p.add_argument("--out", type=Path, default=Path("pbc_match.xlsx"))
    args = p.parse_args(argv)

    result = match(_load(args.requests), _load(args.inventory), threshold=args.threshold)

    with pd.ExcelWriter(args.out, engine="openpyxl") as xl:
        result["status"].to_excel(xl, sheet_name="Status", index=False)
        result["matches"].to_excel(xl, sheet_name="Matches", index=False)
        result["orphans"].to_excel(xl, sheet_name="Orphan_Files", index=False)
        result["duplicates"].to_excel(xl, sheet_name="Duplicates", index=False)

    counts = result["status"]["status"].value_counts().to_dict()
    print("Status:", counts)
    print(f"Orphan files: {len(result['orphans'])}")
    print(f"Wrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(_cli())
