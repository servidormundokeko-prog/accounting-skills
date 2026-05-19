# Approval matrix

**TEMPLATE — REPLACE with your firm's roles and thresholds.**

Defines who approves what at which dollar threshold. Consumed by `je-review` (escalation routing) and `bank-rec` (over-threshold reconciling items).

## Journal entries

| Amount range | Preparer authority | Required approver |
|---|---|---|
| `$0 – $5,000` | Staff Accountant | Senior Accountant |
| `$5,001 – $25,000` | Senior Accountant | Accounting Manager |
| `$25,001 – $100,000` | Accounting Manager | Controller |
| `$100,001 – $500,000` | Controller | CFO |
| `$500,001+` | CFO | CFO + audit committee notification |

The amount is the absolute value of the larger side of the entry (debits = credits).

## Bank reconciliation adjustments

| Item type | Approver |
|---|---|
| Bank fees < $100 | Auto-post |
| Bank fees $100–$1,000 | Staff Accountant |
| Bank fees > $1,000 | Senior Accountant |
| Unreconciled difference > $1,000 | Controller — escalate immediately |
| Outstanding items > 90 days | Controller review monthly |

## Prepaid items

| Action | Approver |
|---|---|
| New prepaid item < $5,000 | Staff Accountant |
| New prepaid item $5,000–$50,000 | Senior Accountant |
| New prepaid item > $50,000 | Controller |
| Change to amortization schedule (term or amount) | One level above original preparer |

## PBC / audit responses

| Action | Approver |
|---|---|
| Standard document provision | Staff or Senior |
| Management response narrative | Controller drafts, CFO reviews |
| Adjustment proposed by auditor | Controller + CFO |

## Names

**TEMPLATE — REPLACE.**

| Role | Name |
|---|---|
| Staff Accountant (default) | TBD |
| Senior Accountant | TBD |
| Accounting Manager | TBD |
| Controller | TBD |
| CFO | TBD |

## How skills use this

- `je-review` flags any entry where the implied preparer authority is exceeded by the entry amount. The output identifies the required approver by role.
- `bank-rec` routes adjustments to the right approver based on amount and item type.
