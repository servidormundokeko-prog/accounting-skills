# Materiality thresholds

**TEMPLATE — REPLACE with your firm's thresholds before production use.**

Other skills reference these by name (e.g., `materiality.flux_threshold_dollar`). Keep the names; change the numbers.

## Flux / variance analysis

Used by `flux-analysis`. An account triggers commentary if **either** threshold is exceeded.

| Key | Value | Notes |
|---|---|---|
| `flux_threshold_dollar` | `$10,000` | Absolute $ change from prior period OR budget |
| `flux_threshold_pct` | `5%` | Percent change from prior period OR budget |
| `flux_de_minimis_dollar` | `$1,000` | Accounts with absolute balance below this are excluded from flux entirely |
| `flux_anomaly_recurring_months` | `2` | Same-sign material variance N months in a row is flagged as a pattern |

## Journal entry review

Used by `je-review`.

| Key | Value | Notes |
|---|---|---|
| `je_preparer_authority` | `$25,000` | JEs above this require escalation regardless of mechanical correctness |
| `je_round_dollar_threshold` | `$10,000` | Round-dollar entries at/above this amount are flagged for memo scrutiny |
| `je_revenue_manual_threshold` | `$5,000` | Manual entries to revenue accounts (4xxx) at/above this trigger `NEEDS_CLARIFICATION` |
| `je_cash_manual_threshold` | `$5,000` | Manual entries to cash accounts (10xx) at/above this trigger `NEEDS_CLARIFICATION` |
| `je_late_posting_workday` | `WD5` | Entries posted after this workday for the prior period are flagged |

## Bank reconciliation

Used by `bank-rec`.

| Key | Value | Notes |
|---|---|---|
| `bank_rec_difference_tolerance` | `$0.01` | Acceptable rounding difference; anything else is unreconciled |
| `bank_rec_old_item_days` | `60` | Reconciling items older than this are escalated |
| `bank_rec_unmatched_dollar_threshold` | `$1,000` | Individual unmatched items at/above this go to senior review |

## Prepaid schedule

Used by `prepaid-schedule`.

| Key | Value | Notes |
|---|---|---|
| `prepaid_capitalize_threshold` | `$1,000` | Invoices below this expense immediately regardless of service period |
| `prepaid_min_months` | `2` | Service period must exceed this many months past period close to qualify as prepaid |

## PBC package

Used by `pbc-package`.

| Key | Value | Notes |
|---|---|---|
| `pbc_match_confidence_threshold` | `0.70` | Below this, request is `PARTIAL` not `COMPLETE` |
| `pbc_priority_high_default` | `5 days before deadline` | Items not started by this point are escalated |

## How to change

Edit this file. Other skills re-read on every run. No code change is needed.

If you add a new threshold, also reference it in the relevant skill's `SKILL.md` so the skill knows to apply it.
