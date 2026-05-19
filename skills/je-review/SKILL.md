---
name: je-review
description: Reviews proposed journal entries for posting readiness. Use when the user provides a list or file of journal entries and asks to review, validate, check for errors, or approve for posting. Verifies debit/credit balance, account coding, support adequacy, memo quality, period appropriateness, duplicate risk, and unusual patterns. Classifies each entry as ready, needs clarification, or reject.
---

# Journal Entry Review

Pre-posting review of proposed JEs. Mechanical validation + risk-pattern detection. Best in Cowork when supporting files accompany the JE listing; Excel add-in when the JEs are in a workbook.

## Required inputs

- **JE listing** — CSV, XLSX, or the `JEs_Proposed` tab from another skill's output. Must conform to `workpaper-standards/references/je-template.md`:
  - `JE_ID`, `Date`, `Account`, `Debit`, `Credit`, `Memo`, `Support Reference`, `Preparer`, `Reviewer`
- *Optional but recommended:* **support folder** — files referenced in `Support Reference` so the skill can verify they exist.
- **firm-config** — uses `materiality.je_*` and `approval-matrix.md`.

## Workflow

1. **Validate mechanics.** Run `scripts/validate_je.py`:
   - Debits equal credits per entry (within $0.01)
   - All `Account` values exist in `chart-of-accounts.csv` and are active
   - `Date` falls within an open period per `close-calendar.md`
   - `Memo` non-empty
   - `Support Reference` non-empty
   - At least one debit line and one credit line per entry

   Any failure → `REJECT` with the specific reason.

2. **Detect risk patterns.** Run `scripts/risk_patterns.py`:
   - **Round dollar above threshold** — amount is whole hundreds/thousands and ≥ `materiality.je_round_dollar_threshold`
   - **Manual entry to revenue (4xxx)** ≥ `materiality.je_revenue_manual_threshold`
   - **Manual entry to cash (10xx)** ≥ `materiality.je_cash_manual_threshold`
   - **Late posting** — entry dated in prior period, being posted after `materiality.je_late_posting_workday`
   - **Near-duplicate within batch** — same accounts, same amount, same day, different `JE_ID`
   - **Reversal of prior entry** — opposite signs to a recent prior-period entry on the same accounts; memo must reference the original JE
   - **Above preparer authority** — entry amount exceeds preparer's per-`approval-matrix.md` limit

3. **Classify each entry.** Apply in order:
   - Any mechanical failure → `REJECT`
   - Otherwise, any risk pattern that requires preparer input → `NEEDS_CLARIFICATION`
   - Otherwise, amount above preparer authority → `MANUAL_REVIEW_REQUIRED` (escalate to the role identified by `approval-matrix.md`)
   - Otherwise → `READY_TO_POST`

4. **Generate preparer questions** for `NEEDS_CLARIFICATION` items. Specific to the pattern:
   - Round dollar to revenue: "JE_017 records $50,000 revenue to 4010 as a round dollar amount. Is this an accrual estimate? If so, the memo should reference the source of the estimate and the true-up plan."
   - Late posting: "JE_022 is dated 2026-03-31 but is being posted on 2026-05-08 (WD7 of the May close). Why is this only being posted now? Has the prior period been re-opened?"

5. **Separate high-risk entries** into their own summary for manager attention. High-risk = `MANUAL_REVIEW_REQUIRED` OR multiple risk patterns OR amount > $100K.

6. **Output workbook tabs**:
   - `Cover` — period, totals, batch ID
   - `Source_JEs` — raw input
   - `Validation_Results` — per-entry pass/fail on each mechanical check
   - `Risk_Patterns` — per-entry detected patterns
   - `Classification` — `READY_TO_POST` / `NEEDS_CLARIFICATION` / `MANUAL_REVIEW_REQUIRED` / `REJECT` with reasons
   - `Questions` — preparer questions consolidated
   - `High_Risk` — manager-attention items
   - `Approval_Routing` — for `MANUAL_REVIEW_REQUIRED`, who needs to sign
   - `Summary` — counts by classification, dollar exposure by classification
   - `Evidence` — links each classification back to the rule(s) it triggered
   - `Review_Notes`

## Invariants

- **A balanced entry with weak support is `NEEDS_CLARIFICATION`, not `READY_TO_POST`.** Mechanical correctness is necessary but not sufficient.
- **Never approve entries above the preparer's authority threshold.** Always escalate, regardless of how clean they look.
- **Reversals must reference the original `JE_ID` in the memo.** A reversal with a thin memo is `NEEDS_CLARIFICATION` even if it ties to a prior entry the skill identified.
- **Don't synthesize a "this looks fine" approval.** If the skill flags nothing, it states the checks that passed — not a vague endorsement.

## When to say "I don't know"

- `Support Reference` points to a file the skill can't find → flag as `NEEDS_CLARIFICATION` ("Support file not found at referenced path"). Don't approve.
- Account isn't in the chart but looks like a typo of an active account → flag, suggest the likely intended account, don't auto-correct.
- Entry pattern matches a reversal but no prior entry can be located in the lookback window → flag as `NEEDS_CLARIFICATION`, ask the preparer to provide the original.
