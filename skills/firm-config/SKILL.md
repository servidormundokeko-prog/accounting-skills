---
name: firm-config
description: Loads firm-specific accounting configuration including chart of accounts, materiality thresholds, close calendar, approval matrix, and standard mappings. Use at the start of any workflow that needs to apply firm-specific rules rather than generic accounting conventions.
---

# Firm Config

This skill exposes firm-specific configuration. The other skills in this bundle (`bank-rec`, `flux-analysis`, `prepaid-schedule`, `pbc-package`, `je-review`) consume it. **You will customize this skill per firm.** The files in `references/` ship as templates with realistic placeholder data clearly marked `TEMPLATE — REPLACE`.

## When to load

At the start of any workflow that needs:

- Account validation (is this account in our chart?)
- Materiality threshold application (does this variance exceed our threshold?)
- Period/calendar awareness (is the date in an open close window?)
- Approval routing (who signs off at this amount?)

A workflow skill loads `firm-config` before applying any threshold or validation. If a workflow runs without `firm-config` available, it must say so explicitly in `Review_Notes` and use the defaults stated in each reference file.

## What's in `references/`

| File | Purpose | Consumed by |
|---|---|---|
| `chart-of-accounts.csv` | All valid GL accounts with descriptions and natural balance | `je-review`, `flux-analysis`, `bank-rec` |
| `materiality.md` | Per-workflow thresholds | `flux-analysis`, `je-review`, `prepaid-schedule` |
| `close-calendar.md` | WD1–WD10 task schedule and open/closed periods | `je-review`, all (period awareness) |
| `approval-matrix.md` | Approval routing by dollar threshold | `je-review` (escalation), `bank-rec` (over-threshold reconciling items) |

## Customizing for your firm

Replace each file in `references/`:

1. **Chart of accounts** — export from your GL. The CSV must keep the same column headers (`account_number`, `account_name`, `account_type`, `natural_balance`, `is_active`). Account numbers as strings to preserve leading zeros.
2. **Materiality** — replace the thresholds in `materiality.md`. The threshold names are referenced by other skills, so keep the names; change the numbers.
3. **Close calendar** — update WD1–WD10 task lists, posting cutoffs, and the list of currently open periods.
4. **Approval matrix** — update name placeholders and dollar thresholds.

The template values are reasonable defaults for a mid-market services company at ~$50M revenue. They are not your firm's values.

## Reading config in practice

Other skills reference config values by name, not by hardcoded number. Example from `flux-analysis`:

> Apply `materiality.flux_threshold_pct` and `materiality.flux_threshold_dollar` from `firm-config/references/materiality.md`. An account triggers commentary if it exceeds **either** the dollar threshold OR the percent threshold.

If you change a threshold in `materiality.md`, the change takes effect on the next workflow run. No skill code needs updating.

## What this skill is not

This is not a config-loading library. The files in `references/` are read directly by the workflow skills as part of their context. There is no Python module to import — just markdown and CSV that the skills inspect.
