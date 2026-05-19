# Close calendar

**TEMPLATE — REPLACE with your firm's calendar.**

Conventions:

- **WD** = workday relative to month-end. `WD1` is the first business day after period close.
- All cutoff times are in your firm's primary time zone.
- "Open" periods accept new postings; "closed" periods reject any JE with a `Date` in that period.

## Workday schedule (typical month)

| Workday | Task | Owner |
|---|---|---|
| WD-1 | AP cutoff: vendor invoices received after EOD post next period | AP |
| WD-1 | Expense report cutoff | All |
| WD1 | Bank statement pulls; cash reconciliations begin | Staff |
| WD2 | Subledger close (AR, AP, FA, Prepaid) | Staff |
| WD2 | Accruals booked (bonus, vacation, expected invoices) | Senior |
| WD3 | Revenue cutoff review; deferred revenue roll | Revenue Accountant |
| WD3 | Intercompany reconciliations | Senior |
| WD4 | Final adjusting JEs | Senior |
| WD5 | **Books closed.** No further JEs without controller approval. | Controller |
| WD5 | Flux/variance analysis begins | Senior |
| WD6 | Flux package to Controller | Senior |
| WD7 | Management package draft | Controller |
| WD8 | Management package final | Controller |
| WD9 | Distribute reporting | Controller |
| WD10 | Close retrospective | All |

## Posting windows

- **Open today** — the period whose books are between WD1 and WD5
- **Re-open** — closed periods can only be re-opened by Controller. JEs with `Date` in a closed period that has not been re-opened are `REJECT` per `je-review`.

## Current period state

**TEMPLATE — REPLACE with your firm's actual open periods.**

| Period | Status | Notes |
|---|---|---|
| 2026-04 (April) | Open | Current close period; WD3 on 2026-05-05 |
| 2026-03 (March) | Closed | Closed 2026-04-07 |
| 2026-02 (February) | Closed | Closed 2026-03-06 |
| 2026-Q1 | Closed | |

When `je-review` checks period validity, it reads this section to determine whether a JE's `Date` is in an open period.

## Special periods

- **Year-end (December)** — extended close: WD1 through WD15. Audit prep begins WD8.
- **Quarter-ends (Mar, Jun, Sep)** — flux package includes quarterly variance commentary in addition to month.

## How to update

After each close, update the "Current period state" table:

- Move the just-closed period from Open → Closed.
- Add the next month as Open.
- Note the actual close date in Notes.
