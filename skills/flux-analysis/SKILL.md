---
name: flux-analysis
description: Performs month-end flux/variance analysis against prior period and budget. Use when the user provides a trial balance and asks to analyze variances, explain fluxes, produce variance commentary, or build a flux workpaper. Applies firm materiality thresholds, calculates dollar and percent changes, categorizes variance type, drafts explanations where support exists, and generates targeted preparer questions where it doesn't.
---

# Flux / Variance Analysis

Month-end variance commentary against prior period **and** budget. Run in the Excel add-in when the TB lives in a workbook, or Cowork when the TB is exported.

## Required inputs

- **Current period TB** — current month or YTD trial balance with account number, account name, balance.
- **Prior period TB** — same format. Same account list, ideally — if accounts differ, the skill flags new/missing accounts.
- **Budget** — same format. Period-matched (current period budget for monthly flux, YTD budget for YTD flux).
- **Period identifier** — e.g., `2026-04` (month) or `2026-Q1` (quarter).
- *Optional:* **prior commentary** — prior period's flux workpaper. Used to check whether explanations are recurring (a recurring variance with the same explanation may be a pattern, not noise).

## Workflow

1. **Load and validate.** Read all three TBs. Run `scripts/compute_variances.py` which:
   - Joins on account number.
   - Computes `var_pm_dollar`, `var_pm_pct`, `var_bud_dollar`, `var_bud_pct`.
   - Flags accounts that appear in current but not prior, or in prior but not current.
   - Excludes accounts whose absolute current and prior balances are both below `materiality.flux_de_minimis_dollar`.

2. **Apply materiality.** From `firm-config/references/materiality.md`, load `flux_threshold_dollar` and `flux_threshold_pct`. An account triggers commentary if **either** threshold is exceeded on **either** comparison (prior period or budget). The skill works on the filtered set; smaller variances are listed but not commented.

3. **Detect anomalies.** Run `scripts/anomaly_detect.py`:
   - **Sign change** — balance flipped from debit to credit or vice versa
   - **New account** — exists in current, not in prior
   - **Missing account** — exists in prior, not in current (balance went to zero with no posting)
   - **Recurring variance** — same direction material variance N months in a row (`materiality.flux_anomaly_recurring_months`)
   - **Budget miss** — current actuals are >2x budget or <0.5x budget

4. **Classify each material variance.** Pick one:
   - `TIMING` — variance explained by a period cutoff (e.g., invoice posted to wrong month)
   - `RECLASS` — variance explained by a known reclassification with a referenced JE
   - `BUSINESS_DRIVER` — variance explained by an identified operational change with a source
   - `LIKELY_ERROR` — variance pattern matches a known error mode (sign flip, decimal slip, account swap)
   - `UNKNOWN` — no supported explanation → generates a preparer question

5. **Draft commentary, only when a source supports it.** Acceptable sources:
   - A specific JE in the current period (cite `JE_ID`)
   - A specific accrual or reclass (cite reference)
   - A prior-period explanation that explicitly stated this pattern would continue
   - An operational fact in inputs the user provided (headcount change, new contract)

   If no source supports an explanation, the skill **does not draft one**. It generates a question for the account owner. "Probably driven by Q1 marketing push" is not a commentary — it is a guess.

6. **Generate preparer questions** for `UNKNOWN` items. One question per account, specific:
   - Bad: "Please explain the variance."
   - Good: "Account 6200 Marketing-Advertising shows $42K above budget (+38%) for April. Prior period was on budget. What drove the increase — was there a campaign launch or a reclass from another period?"

7. **Output workbook tabs**:
   - `Cover` — period, comparison basis, status
   - `Source_TB_Current`, `Source_TB_Prior`, `Source_Budget` — raw inputs
   - `Variances` — sortable table: account, balances, $ var, % var, materiality flag, classification, commentary, question
   - `Anomalies` — sign changes, new/missing accounts, recurring patterns
   - `Questions` — preparer questions consolidated for follow-up
   - `Summary` — high-level commentary: largest favorable, largest unfavorable, themes
   - `Evidence` — sources for each commentary line
   - `Review_Notes`

## Invariants

- **Never draft a business explanation without an identifiable source.** "I don't have enough information to explain this variance" is a valid output and preferred over speculation.
- **A `UNKNOWN` classification must always have a corresponding preparer question.**
- **Recurring identical explanations** ("timing — December accrual" for the same account 4 months running) are a smell, not a comfort. Flag as `LIKELY_ERROR` or `MANUAL_REVIEW_REQUIRED`.

## When to say "I don't know"

- Account list doesn't align between current/prior/budget → stop and ask whether there was a chart change.
- Budget is missing for >20% of material accounts → produce flux against prior period only and note the budget gap.
- Prior commentary references things not in inputs → don't invent context; flag for follow-up.
