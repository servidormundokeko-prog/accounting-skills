---
name: workpaper-standards
description: Use whenever producing an accounting workpaper, schedule, reconciliation, journal entry, or audit deliverable. Defines firm formatting conventions, the evidence-table requirement, journal entry templates, and the standard for source tie-outs. Required dependency for bank-rec, flux-analysis, prepaid-schedule, pbc-package, and je-review skills.
---

# Workpaper Standards

This skill defines the formatting, evidence, and review conventions that every workpaper-producing skill in this bundle inherits. Other skills in this bundle assume these conventions and do not re-state them — read this before acting on any workpaper request.

## Workpaper layout

Every workbook produced by a workflow skill in this bundle has the same tab structure:

1. **`Cover`** — header block (preparer, period, deliverable type, status), table of contents, sign-off lines.
2. **`Source`** — raw inputs loaded as-is. One tab per source file if multiple. Never edit values in this tab.
3. **`Calc`** — derived values. Cells contain formulas referencing `Source` ranges. One tab per logical calculation.
4. **`Summary`** — the answer. References `Calc` cells. This is what a reviewer reads first.
5. **`Evidence`** — the evidence table (see `references/evidence-table-template.md`). Required on every workpaper. No exceptions.
6. **`Review_Notes`** — preparer questions, reviewer comments, items flagged for follow-up.

If the workpaper is being delivered as something other than a workbook (CSV, PDF, narrative), the evidence table still ships alongside it.

## Color and format conventions

- **Blue font** — manual input (preparer-entered)
- **Black font** — formula computing from this workbook
- **Green font** — link to another workbook or external source
- **Red font** — flagged for review (paired with a `Review_Notes` entry)
- **Bold + double underline** — final totals
- **Single underline** — subtotals
- Negative numbers in parentheses, not minus signs
- Dates as `YYYY-MM-DD` in cells; display format may vary
- Currency: USD unless the workpaper header states otherwise
- Account numbers always rendered as text to preserve leading zeros

## The evidence table is non-negotiable

Every numerical output in a workpaper must appear in the evidence table with its source. If a number is calculated rather than sourced, the `Calculation` column must show the formula and its inputs. **Never produce a workpaper without an evidence table.** The format is defined in `references/evidence-table-template.md`.

This is the single rule that makes outputs reviewable instead of impressive. A reviewer should be able to spot-check any number on the `Summary` tab and trace it back to a source in under 30 seconds.

## Journal entry format

All JEs use the format in `references/je-template.md`. Mechanical rules:

- Each entry must have at least one debit and one credit.
- Debits must equal credits per entry.
- Memos describe **why**, not just **what** — "Record May rent" is too thin; "Record May rent per lease #2024-114, signed 2024-01-15, $8,500/mo through 2027-01" is right.
- Every JE references support (file path, page, or workpaper tab) in the `Support Reference` column.

## Review flag vocabulary

Use the controlled flags from `references/review-flags.md`. Don't invent new flags. The four canonical states for any deliverable item are:

- `READY_TO_POST` / `READY_FOR_REVIEW` — meets all criteria
- `NEEDS_CLARIFICATION` — answerable with one round of preparer questions
- `MANUAL_REVIEW_REQUIRED` — requires judgment beyond what the skill can confidently apply
- `REJECT` — fails a hard rule (out of period, unbalanced, missing required field, etc.)

## When to say "I don't know"

If inputs are insufficient for a step, output what's missing instead of filling the gap with assumptions. Acceptable forms:

- "Service period not present on invoice — flagged for preparer."
- "Prior-period variance commentary references invoice INV-3398, which is not in the support folder — cannot verify continuity."
- "Bank statement balance does not reconcile to GL after all identified adjustments; unexplained difference of $X."

A workpaper that surfaces gaps is a better workpaper than one that hides them.
