# Review flag vocabulary

The only flags any skill in this bundle should produce. Don't invent new ones — if an item doesn't fit, it's `MANUAL_REVIEW_REQUIRED`.

## Item-level flags

| Flag | Meaning | Required follow-up |
|---|---|---|
| `READY_TO_POST` | JE passes all mechanical and risk checks. | Reviewer sign-off, then post. |
| `READY_FOR_REVIEW` | Non-JE deliverable (workpaper, schedule, package) meets all criteria. | Reviewer sign-off. |
| `NEEDS_CLARIFICATION` | Answerable with one round of preparer questions. The skill drafts the questions. | Preparer responds to the questions in `Review_Notes`, item is re-evaluated. |
| `MANUAL_REVIEW_REQUIRED` | Requires judgment the skill cannot confidently apply (unusual transactions, policy questions, item outside the skill's scope). | Senior accountant or manager reviews directly. |
| `REJECT` | Fails a hard rule. Cannot be fixed in place. | Preparer reworks and resubmits. |

## Reconciliation-specific status

| Flag | Meaning |
|---|---|
| `OUTSTANDING_CHECK` | Issued check, not yet cleared |
| `DEPOSIT_IN_TRANSIT` | Booked deposit, not yet cleared |
| `BANK_FEE_NOT_BOOKED` | Bank charge missing from GL |
| `NSF_RETURN` | Returned deposit |
| `DUPLICATE_ENTRY` | Likely double-posted on one side |
| `UNKNOWN` | Cannot classify with available information — drops to `MANUAL_REVIEW_REQUIRED` |

## Variance-specific status

| Flag | Meaning |
|---|---|
| `TIMING` | Variance explained by period cutoff |
| `RECLASS` | Variance explained by a known reclassification |
| `BUSINESS_DRIVER` | Variance explained by an identified operational change with a source |
| `LIKELY_ERROR` | Variance pattern matches a known error mode (sign flip, decimal slip, account swap) |
| `UNKNOWN` | No supported explanation — generates a preparer question |

## PBC-specific status

| Flag | Meaning |
|---|---|
| `COMPLETE` | High-confidence file match (>= 0.7) |
| `PARTIAL` | Some support, gaps identified |
| `MISSING` | No matching support |
| `MANAGEMENT_RESPONSE_REQUIRED` | Request asks for narrative, not a document |

## Rules

- Flags are uppercase, snake_case.
- One primary flag per item. Reconciliation/variance/PBC sub-flags coexist with a primary flag (a `BANK_FEE_NOT_BOOKED` item is also `NEEDS_CLARIFICATION` or `READY_TO_POST` once classified).
- If you're tempted to invent a new flag, the item is `MANUAL_REVIEW_REQUIRED` and you write the reason in `Review_Notes`.
