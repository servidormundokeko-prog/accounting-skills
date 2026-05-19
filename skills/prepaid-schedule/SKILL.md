---
name: prepaid-schedule
description: Builds and maintains prepaid expense amortization schedules. Use when the user provides vendor invoices, service period information, or an existing prepaid template and asks to extract prepaid items, build amortization schedules, calculate monthly expense, or generate journal entries for prepaid recognition and amortization. Produces a formula-driven schedule, not hardcoded tables.
---

# Prepaid Schedule

Extracts prepaid items from invoices and builds amortization schedules. Initial extract is best in Cowork (PDF/image invoices in a folder). Ongoing schedule maintenance is best in the Excel add-in (existing workbook).

## Required inputs

For new items:
- **Invoice files** (PDF, PNG, or structured CSV/XLSX with invoice fields)
- **Period of recognition** — the close period the items are being booked into (e.g., `2026-04`)

For schedule maintenance:
- **Existing prepaid workbook** with the standard tabs (`Schedule`, `Inputs`, `Summary`)

## Workflow — new item extraction

1. **Extract invoice fields.** Run `scripts/extract_invoice_fields.py`. For each invoice, extract:
   - vendor name, invoice number, invoice date
   - amount (USD)
   - service start, service end (or service period descriptor)
   - category (subscription, insurance, rent, license, etc.)
   - confidence per field (`HIGH` / `MEDIUM` / `LOW`)

   Fields the OCR cannot extract with confidence are blank and flagged for preparer. **Don't guess service periods.** If the invoice says "annual subscription" with no dates, mark `service_period_descriptor = "annual"` with `MEDIUM` confidence and let downstream logic infer 12 months (still `MEDIUM`).

2. **Classify treatment.** For each item:
   - `EXPENSE_NOW` — service period closes in current period or earlier, OR amount < `materiality.prepaid_capitalize_threshold` (default $1,000)
   - `PREPAID` — service period extends > `materiality.prepaid_min_months` past period close
   - `REVIEW` — service period ambiguous, vendor unfamiliar, or amount unusually large

3. **Build the amortization schedule.** Run `scripts/build_amortization.py`. The output is **formulas, not values** — schedule cells reference the inputs tab so changes propagate. For each `PREPAID` item:
   - Capitalize full amount on service start month to account `1220 - Prepaid Software/Subscriptions` (or the right prepaid account per category)
   - Amortize `=amount / months` each month into the matching expense account
   - Round the final month to absorb cumulative rounding so the schedule fully amortizes

4. **Generate JEs.**
   - **Initial recognition** (one JE per item): debit `1220`, credit `2010 AP` (or `1010 Cash` if cash basis), full amount.
   - **First-month amortization** (consolidated across items by expense account): debit expense, credit `1220`, monthly amount.
   - Both JE sets go to `JEs_Proposed` for `je-review`.

5. **Build summary views.**
   - **By month** — total prepaid balance roll forward, amortization, ending balance
   - **By vendor** — total open prepaid by vendor
   - **By category** — total amortization by expense account for the current period

## Workflow — schedule maintenance

For an existing workbook:

1. Add new items to `Inputs` tab.
2. Recalculate the `Schedule` tab — formulas pick up new rows automatically if the schedule uses dynamic ranges or table references. If hardcoded ranges, extend them.
3. Verify roll-forward: prior period ending balance + additions − amortization = current period ending balance.
4. Generate the current month's amortization JE.

## Output workbook tabs

- `Cover` — period, preparer, status
- `Inputs` — one row per prepaid item with all extracted fields (this is the data tab; everything else references it)
- `Schedule` — month-by-month amortization, formulas referencing Inputs
- `Summary_By_Month` — totals roll-forward
- `Summary_By_Vendor`
- `JEs_Proposed` — recognition and amortization JEs
- `Evidence` — every Inputs row links back to its source invoice file and page
- `Review_Notes` — items flagged `REVIEW`, MEDIUM/LOW confidence extractions, vendor not previously seen

## Invariants

- **Schedule cells contain formulas, never computed values pasted as numbers.** A reviewer changing an amount or term must see all downstream values update.
- **Service period must be derivable from source.** If only an invoice date is present with no service period or descriptor, the item is `REVIEW`.
- **Every Inputs row has an Evidence row** pointing to the source invoice file and page.
- **The amortization fully resolves to zero by the service end month** — rounding handled in the final month.

## When to say "I don't know"

- Invoice has no clear service period and no period descriptor → `REVIEW`, ask the preparer.
- Vendor name is unreadable (OCR low confidence) → `REVIEW`, ask the preparer to confirm.
- Amount is materially different from prior invoices from the same vendor → flag for confirmation before adding to schedule.
