# Journal entry template

All JEs produced by skills in this bundle use this exact format. `je-review` validates against it.

## Required columns

| Column | Type | Notes |
|---|---|---|
| `JE_ID` | text | `JE_NNN` within a batch, or firm-assigned ID if posting |
| `Date` | date (`YYYY-MM-DD`) | Posting date. Must fall within an open close period. |
| `Account` | text | Account number from `firm-config/references/chart-of-accounts.csv`. Account number, not name. |
| `Debit` | number | USD. Blank if this line is a credit. |
| `Credit` | number | USD. Blank if this line is a debit. |
| `Memo` | text | Why, not just what. See memo rules below. |
| `Support Reference` | text | File path, workpaper tab, invoice number — anything a reviewer can open. |
| `Preparer` | text | Name or initials |
| `Reviewer` | text | Blank until reviewed |

## Mechanical rules (enforced by `je-review/scripts/validate_je.py`)

1. Each entry has at least one debit line and at least one credit line.
2. Sum of debits equals sum of credits for the entry.
3. Every `Account` exists in `firm-config/references/chart-of-accounts.csv`.
4. `Date` falls within an open close window per `firm-config/references/close-calendar.md`.
5. `Memo` is non-empty.
6. `Support Reference` is non-empty.

A JE that fails any of these is `REJECT`. `NEEDS_CLARIFICATION` is reserved for JEs that are mechanically correct but soft-fail on risk patterns (round-dollar to revenue, near-duplicate, etc.).

## Memo rules

A good memo answers: **what is this entry, why now, and what supports it.**

Bad: `Record May rent`
Better: `Record May rent — building A`
Right: `Record May rent — building A, per lease #2024-114, $8,500/mo through 2027-01`

Bad: `Reclass`
Right: `Reclass Q1 marketing expenses from 6200 to 6210 per controller review 2026-05-12; original entry JE_0412`

Memos that just restate the account names are not memos.

## Example JE

```
JE_ID   Date         Account  Debit     Credit    Memo                                                      Support Reference          Preparer  Reviewer
JE_017  2026-04-30   6310     8500.00              Record May rent - bldg A, lease #2024-114, $8500/mo      Lease_2024-114.pdf p.2     xs
JE_017  2026-04-30   1010              8500.00     Record May rent - bldg A, lease #2024-114, $8500/mo      Lease_2024-114.pdf p.2     xs
```

The memo is identical across lines of the same entry — they're the same transaction.

## Reversing entries

If the entry reverses a prior-period entry, the memo MUST reference the prior JE_ID and state why the reversal is necessary. Example:

`Reverse JE_0412 (Q1 marketing $48K to acct 6210) — original posting was to wrong cost center per controller review 2026-05-12. Reposting in JE_018.`

`je-review` flags reversing entries with thin memos as `NEEDS_CLARIFICATION`.
