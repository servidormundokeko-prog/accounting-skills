# accounting-skills

A bundle of Claude Skills for recurring accounting workflows: bank reconciliation, flux/variance analysis, prepaid schedules, PBC packages, and journal-entry review.

These skills are designed to install together. They share two foundation skills (`workpaper-standards` and `firm-config`) that the five workflow skills depend on. Every workflow produces an evidence table tying each output back to its source, and every workflow is licensed to say "I don't have enough information" rather than fabricating an answer.

## Skills in this bundle

| Skill | Purpose | Best environment |
|---|---|---|
| `workpaper-standards` | Firm formatting conventions, evidence-table format, JE template, review flag vocabulary. **Foundation — required dependency.** | All |
| `firm-config` | Chart of accounts, materiality thresholds, close calendar, approval matrix. **Foundation — customize per firm.** | All |
| `bank-rec` | Bank statement vs GL cash reconciliation with deterministic matching and aged reconciling items. | Cowork |
| `flux-analysis` | Month-end variance analysis vs prior period and budget with materiality-driven commentary. | Excel add-in / Cowork |
| `prepaid-schedule` | Extract prepaid items from invoices and build formula-driven amortization schedules. | Cowork → Excel add-in |
| `pbc-package` | Map PBC request lists to support files, identify gaps, draft auditor responses. | Cowork |
| `je-review` | Review proposed JEs for posting readiness — mechanical validation plus risk-pattern detection. | Excel add-in / Cowork |
| `conciliacion-banesco` | Banesco (Venezuela, Bs.) bank reconciliation from scanned "Estado de cuenta" PDFs: line-by-line running-balance validation, Pago Móvil / transfer commission pairing, multi-month rec vs the bank ledger. Builds on `bank-rec`. In Spanish. | Cowork / Claude Code |

## Composition

The workflow skills are independent — install one without the others. But `bank-rec`, `prepaid-schedule`, and any other skill that produces JEs can have their output fed into `je-review` as a sanity layer before posting. That is the most valuable composition pattern.

## Installation

Skills install per-environment. Copy the relevant skill folders into your environment's skills directory:

- **Claude Code:** `~/.claude/skills/` (user-level) or `.claude/skills/` (project-level)
- **Cowork:** upload via the Skills tab in your workspace settings
- **Claude.ai:** upload via Workspace → Capabilities → Skills (requires Code Execution and File Creation enabled)

The two foundation skills (`workpaper-standards`, `firm-config`) must be installed alongside any workflow skill.

## Customizing `firm-config`

`skills/firm-config/references/` ships with realistic template data marked `TEMPLATE — REPLACE`. Before using in production:

1. Replace `chart-of-accounts.csv` with your firm's GL.
2. Set materiality thresholds in `materiality.md`.
3. Adjust the close calendar in `close-calendar.md`.
4. Update the approval matrix in `approval-matrix.md`.

## Python scripts

The deterministic parts of each workflow (matching, variance math, amortization, validation) live in `scripts/` inside each skill and use only `pandas`, `openpyxl`, and the standard library. Run `pip install -r requirements.txt` to install.

Scripts are designed to be invoked by the skill at runtime, but they are plain Python and runnable standalone — useful for testing.

To run the test suite:

```
pip install -r requirements.txt
pytest
```

## Repository layout

```
accounting-skills/
├── skills/
│   ├── workpaper-standards/   foundation
│   ├── firm-config/           foundation (customize per firm)
│   ├── bank-rec/
│   ├── flux-analysis/
│   ├── prepaid-schedule/
│   ├── pbc-package/
│   ├── je-review/
│   └── conciliacion-banesco/  Banesco (VE) — depends on bank-rec
├── tests/                     smoke tests for the scripts
├── requirements.txt
├── LICENSE
└── README.md
```

## Design invariants

These hold across every skill in the bundle:

1. **Every numerical output appears in an evidence table** with its source file, sheet, range, value, and (if calculated) formula. See `skills/workpaper-standards/references/evidence-table-template.md`.
2. **Calculations live in formulas, not hardcoded values** — schedules reference inputs so downstream changes propagate.
3. **Probable matches are never auto-confirmed.** Anything below a confidence threshold goes to a review tab, not the final output.
4. **"I don't know" is a valid output.** If inputs are insufficient, the skill outputs what's missing rather than filling the gap with assumptions.
5. **Mechanical correctness ≠ posting readiness.** A balanced JE with weak support is `NEEDS_CLARIFICATION`, not `READY_TO_POST`.

## License

MIT. See [LICENSE](LICENSE).
