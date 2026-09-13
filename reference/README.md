# Reference model

An **executable specification** of the kernel's core. Python 3.11 or later. Standard library only.

It exists to make the invariants in [docs/03-domain-model.md](../docs/03-domain-model.md) concrete and testable. It is **not production code**. There is no persistence, no API, no concurrency.

```bash
python3 -m unittest discover -s reference/tests -v
```

## Modules

| Module | Covers |
|--------|--------|
| `digi_kernel/ledger.py` | I1 balanced in money and units. I5 immutable, reversal only. I12 actor and pack version. Bitemporal balances. |
| `digi_kernel/prices.py` | I10 versions never overwrite. Four eyes on official prices. Movement tolerance. Price selection with provenance. |
| `digi_kernel/register.py` | I2 holders = units in issue. Positions derived from postings. |
| `digi_kernel/valuation.py` | I6 values computed on read, with price basis, age and staleness. |
| `digi_kernel/controls.py` | I9 maker ≠ checker. Loss policy for I7. Day close with no reopen for I11. |
| `digi_kernel/blocks.py` | Investment, redemption, payment (I8), settlement exposure (I4), backdating with delta (I7), reversal, price correction, day close gates. FICA-CDD gate on dealing and payment, obligation tags on journals, regulatory trail query. |
| `digi_kernel/obligations.py` | Legislation as a controlled object (ADR-009). Versioned, effective-dated library with two approvers. Tenant register with bindings, justified exclusions and the coverage gate (C11). |

## Test to invariant map

| Test file | Proves |
|-----------|--------|
| `tests/test_ledger.py` | Unbalanced journals are rejected. No update or delete exists. Reversals reference the original. Balances as at both time axes. |
| `tests/test_valuation.py` | A new price changes every value with no re-run. Knowledge-time views. Stale prices are shown and flagged. Indicative versus official policy. |
| `tests/test_backdating.py` | The delta formula in both directions for investments and redemptions. No owner, no posting. Maker cannot approve. Two approvers minimum. Closed days refuse ordinary pricing. Unpaid collections reverse with an owner. |
| `tests/test_blocks.py` | No units without cash or exposure. Exposure limits. No payment without a payable. Payment approvals. Price corrections version and reprice. Day close gates. |
| `tests/test_obligations.py` | Library changes need two approvers and a source. Obligations are effective-dated; COFI sits pending. An unbound obligation blocks release. Not applicable needs a reason and approvals. The FICA gate blocks a payment and names the law. The regulatory trail reads obligation tags back. |

## Conventions

- Debits are positive, credits are negative, in both dimensions.
- Holder unit accounts carry credit balances. `UNITS_IN_ISSUE:<class>` carries the matching debit balance.
- Units round half-up to 4 decimals. Money rounds half-up to cents. A pack decides these in the real platform.
