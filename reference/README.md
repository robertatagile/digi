# Reference model

An **executable specification** of the kernel's core. Python 3.11 or later. Standard library only.

It exists to make the invariants in [docs/03-domain-model.md](../docs/03-domain-model.md) concrete and testable. It is **not production code**. There is no persistence, no API, no concurrency.

```bash
python3 -m unittest discover -s reference/tests -v
```

## Modules

The scale data layout and its benchmark live in [`scale/`](scale/README.md).

| Module | Covers |
|--------|--------|
| `digi_kernel/ledger.py` | I1 balanced in money and units. I5 immutable, reversal only. I12 actor and pack version. Bitemporal balances. |
| `digi_kernel/prices.py` | I10 versions never overwrite. Four eyes on official prices. Movement tolerance. Price selection with provenance. |
| `digi_kernel/register.py` | I2 holder side = control side, whether the control is units in issue (own class) or the nominee bulk (external class). Positions derived from postings. Any number of instruments per account. |
| `digi_kernel/valuation.py` | I6 values computed on read, with price basis, age and staleness. |
| `digi_kernel/controls.py` | I9 maker ≠ checker. Loss policy for I7. Day close with no reopen for I11. |
| `digi_kernel/blocks.py` | Investment, redemption, switch (both legs or neither), transfer (units only), distribution (record-date entitlements derived, rounding account, reinvest or pay out), fees (accrual from daily facts, collection by unit cancellation), payment (I8), settlement exposure (I4), backdating with delta (I7), reversal, price correction, day close gates. FICA-CDD gate on dealing and payment, FAIS licence gate on fee release, obligation tags on journals, regulatory trail query. Instruments with an issuer; bulk dealing and allocation for external instruments. Pack guards on blocks (refuse only), payment holds, contributions derived from facts: the primitives product wrappers are built from. |
| `digi_kernel/obligations.py` | Legislation as a controlled object (ADR-009). Versioned, effective-dated library with two approvers. Tenant register with bindings, justified exclusions and the coverage gate (C11). |

## Test to invariant map

| Test file | Proves |
|-----------|--------|
| `tests/test_ledger.py` | Unbalanced journals are rejected. No update or delete exists. Reversals reference the original. Balances as at both time axes. |
| `tests/test_valuation.py` | A new price changes every value with no re-run. Knowledge-time views. Stale prices are shown and flagged. Indicative versus official policy. |
| `tests/test_backdating.py` | The delta formula in both directions for investments and redemptions. No owner, no posting. Maker cannot approve. Two approvers minimum. Closed days refuse ordinary pricing. Unpaid collections reverse with an owner. |
| `tests/test_blocks.py` | No units without cash or exposure. Exposure limits. No payment without a payable. Payment approvals. Price corrections version and reprice. Day close gates. |
| `tests/test_bulk.py` | One account holds an own fund and an external fund on one statement. External instruments deal in bulk: the confirmation becomes the price, allocation rounds to a holder-side account, the nominee bulk is the control total, a whole-unit mismatch is a break. |
| `tests/test_composed_blocks.py` | A switch posts both legs in one journal or nothing, and switch clearing nets to zero. A transfer moves units with no price and no money. A distribution derives entitlements at the record date even after a later redemption, withholds tax, exempts the tax-free wrapper, posts rounding to its own account, reinvests at the pay-date price or pays out. A fee accrues from daily units and prices, is collected by unit cancellation, and is paid only through the FAIS licence gate. |
| `tests/test_wrappers.py` | TFSA and RA are the same investment and redemption blocks with guards. A TFSA over-contribution is refused at cash matching and stays refundable. An RA retirement component is locked before retirement age; the savings component allows one withdrawal per tax year; payment waits for the tax directive and the release posts the withholding. |
| `tests/test_obligations.py` | Library changes need two approvers and a source. Obligations are effective-dated; COFI sits pending. An unbound obligation blocks release. Not applicable needs a reason and approvals. The FICA gate blocks a payment and names the law. The regulatory trail reads obligation tags back. |

## Conventions

- Debits are positive, credits are negative, in both dimensions.
- Holder unit accounts carry credit balances. `UNITS_IN_ISSUE:<class>` carries the matching debit balance.
- Units round half-up to 4 decimals. Money rounds half-up to cents. A pack decides these in the real platform.
