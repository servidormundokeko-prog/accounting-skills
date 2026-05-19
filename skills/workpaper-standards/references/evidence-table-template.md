# Evidence table template

Every workpaper produced by a skill in this bundle ships with an `Evidence` tab in this exact format. No exceptions.

## Required columns

| Column | Type | Description |
|---|---|---|
| `Output Cell/Field` | text | Where the output appears (e.g., `Summary!B14`, `JE_001 Debit`, `Flux row 42`) |
| `Source File` | text | Filename of the source. For multi-sheet workbooks, just the file name. |
| `Sheet` | text | Sheet/tab name in the source file. Blank for non-spreadsheet sources. |
| `Row/Range` | text | Cell, row, or range in the source (e.g., `B23`, `A2:A50`, `page 3`) |
| `Source Value` | number/text | The value as it appears in the source. Preserve original sign and precision. |
| `Calculation` | text | If the output is derived, the formula and inputs (e.g., `=Source!B23 * 12 / 365`). Blank if 1:1 pass-through. |
| `Confidence` | enum | `HIGH`, `MEDIUM`, `LOW` — see thresholds below |

## Confidence thresholds

- **HIGH** — direct read from a structured source (XLSX cell, CSV column with known header) with no transformation, or a calculation whose inputs are all `HIGH`.
- **MEDIUM** — fuzzy match (description matching, OCR-extracted field), or a derived value whose inputs include at least one `MEDIUM` input.
- **LOW** — inferred from context (e.g., service period guessed from invoice line description), OCR with low character confidence, or any value the skill itself flagged for review. **`LOW` items must also appear in `Review_Notes`.**

## Example rows

| Output Cell/Field | Source File | Sheet | Row/Range | Source Value | Calculation | Confidence |
|---|---|---|---|---|---|---|
| `Summary!B14` (Cash per GL) | `GL_cash_2026-04.xlsx` | `Detail` | `H847` | `1,248,392.14` | | HIGH |
| `Summary!B15` (Cash per bank) | `Chase_stmt_2026-04.pdf` | | `page 1` | `1,253,118.62` | | HIGH |
| `Summary!B16` (Difference) | | | | | `=B14-B15` | HIGH |
| `JE_003 Debit $4,500` | `INV-2398.pdf` | | `page 1` | `4,500.00` | | HIGH |
| `Prepaid_Sched!C8 (months)` | `INV-2398.pdf` | | `page 1, line: "annual subscription"` | `annual subscription` | `=12 (inferred from "annual")` | MEDIUM |

## Format rules

- One row per output value. If `Summary!B14:B20` are seven independent values, that's seven evidence rows.
- For passthrough values, leave `Calculation` blank — the absence of a formula is the signal that this is a 1:1 read.
- For values derived from multiple sources, list each source on its own row keyed to the same `Output Cell/Field`, then add a final row with the `Calculation` referencing the prior rows.
- Never collapse multiple distinct sources into one row. The point is auditability.

## What this is not

This is not a "summary of work performed." It is a per-value source trace. Narrative goes in `Review_Notes`.
