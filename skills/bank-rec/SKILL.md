---
name: bank-rec
description: Performs bank reconciliations between a bank statement export and GL cash detail. Use when the user provides a bank statement file (CSV, XLSX, or PDF) and a GL cash detail file and asks to reconcile, match transactions, identify outstanding items, or produce a bank rec workpaper. Outputs a matched/unmatched workbook, aged reconciling items, proposed adjusting JEs, and an evidence table.
---

# Bank Reconciliation

Reconciles a bank statement against the GL cash detail for one account and one period. Best run in Cowork — two files in, workbook out.

## Required inputs

- **Bank statement** — CSV, XLSX, or PDF. Must contain date, description, amount (with sign), and ideally a reference/check number.
- **GL cash detail** — CSV or XLSX. Must contain posting date, description, debit, credit (or signed amount), and entry/reference number.
- **Period** — the close period being reconciled (e.g., `2026-04`).

If any of these is missing, output what's missing instead of guessing.

## Workflow

1. **Load and validate.** Open both files. Confirm period and currency match. Confirm the bank account in the statement matches the GL account in the cash detail (compare to `firm-config/references/chart-of-accounts.csv`).

2. **Match transactions.** Run `scripts/match_transactions.py` with priority order:
   - Exact amount + exact date (`HIGH` confidence)
   - Exact amount + date within ±3 days (`HIGH`)
   - Exact amount + matching reference/check number (`HIGH`)
   - Fuzzy description match + same amount (`MEDIUM` — never auto-confirmed)

3. **Bucket the output.** The script returns four sets:
   - `exact_matches` — auto-included in the reconciliation
   - `probable_matches` — go to a `Probable_Matches` review tab; preparer confirms
   - `unmatched_bank` — bank items with no GL match
   - `unmatched_book` — GL items with no bank match

4. **Age unmatched items.** Run `scripts/age_items.py`. Buckets: `0–30`, `31–60`, `61+` days from period end. Items aged 61+ get a red flag and go to `Review_Notes`.

5. **Classify unmatched items.** For each, pick the best fit from `workpaper-standards/references/review-flags.md`:
   - `OUTSTANDING_CHECK` — book debit (cash out), no bank match, recent
   - `DEPOSIT_IN_TRANSIT` — book credit (cash in), no bank match, recent
   - `BANK_FEE_NOT_BOOKED` — bank debit, no book match, small/recurring description (`SERVICE CHARGE`, `WIRE FEE`, etc.)
   - `NSF_RETURN` — bank credit reversal with `NSF` / `RETURNED` in description
   - `DUPLICATE_ENTRY` — same amount, same date appearing twice on one side
   - `UNKNOWN` — anything else, escalated to `MANUAL_REVIEW_REQUIRED`

6. **Propose adjusting JEs.** For each classifiable item that requires a book adjustment (bank fees, NSF returns, missed deposits), draft a JE using `workpaper-standards/references/je-template.md`. Bank fees credit cash and debit `6900 - Bank Fees`. NSF returns reverse the original deposit. Outstanding checks and deposits in transit are **not** booked — they're reconciling items.

7. **Build the reconciliation summary.** Tie GL balance to bank balance:

   ```
   Balance per bank (statement)             X
   Plus: deposits in transit                +
   Less: outstanding checks                 -
   Plus/less: other reconciling items       ±
   Balance per books (after adjustments)    Y
   Less: GL balance per cash detail         -
   = Unreconciled difference (should be 0)  Z
   ```

   If `Z` is within `materiality.bank_rec_difference_tolerance` (default $0.01), the rec ties. If not, the skill says so and quantifies `Z` — it does **not** plug to force a tie.

8. **Output workbook tabs** per `workpaper-standards`:
   - `Cover` — header, period, accounts, status
   - `Source_Bank` — raw bank file
   - `Source_GL` — raw GL detail
   - `Matched` — exact matches with confidence column
   - `Probable_Matches` — review-required matches
   - `Unmatched_Bank`, `Unmatched_Book` — with aging columns
   - `Reconciling_Items` — classified, with proposed JEs
   - `Summary` — the tie-out shown above
   - `JEs_Proposed` — feeds directly to `je-review`
   - `Evidence` — every number on `Summary` traced back
   - `Review_Notes` — questions, flagged items, aged items

## Invariants

- **Probable matches are never auto-confirmed.** They appear on their own tab.
- **If the rec doesn't tie, say so.** Never plug.
- **The proposed JEs go through `je-review` before posting.** That is the composition pattern.
- **One account, one period per workpaper.** If the user has multiple accounts, run once per account.

## When to say "I don't know"

- Bank statement and GL appear to be different accounts → stop and ask.
- Bank statement is in a different currency than GL → stop and ask about FX treatment.
- More than 30% of items are `UNKNOWN` after classification → likely a data quality issue with the inputs; surface in `Review_Notes` and don't pretend the rec is healthy.
