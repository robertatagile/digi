# 6. Valuation: calculate, don't store

## The principle

> **Quantities and prices are facts. Values are views.**

The platform stores what happened: units moved, cash moved, a price was published. It does not store what something is worth. Worth is computed on read, from the last known price, every time.

## Facts versus views

| Stored as a fact | Derived on read |
|------------------|-----------------|
| Instructions, with received-at | Holding units (fold of unit postings) |
| Deals: units, amount, price reference | Units in issue per class |
| Unit postings, cash postings | Holding value, account value, fund size |
| Bank lines | Fee accrual to date |
| Published prices, every version | Distribution entitlements before allocation |
| Distribution declarations | Expected net flow per pricing point |
| Executed fee claims | Statements, tax figures, performance |
| Approvals, pack versions | Cash forecast |

**Allowed caches:** position snapshots keyed by event version, daily valuation projections keyed by price versions, rendered statements keyed by knowledge time. A test proves each cache equals a pure recompute. A version change invalidates the cache.

The word "almost" in the brief lands here. Published prices are stored. They are legal facts. Investor values are never stored as facts.

## Position derivation

```
units(account, class, E, K) = Σ unit postings
                              where effective_date ≤ E
                              and posted_at ≤ K
```

- **E** is the effective as-at date.
- **K** is the knowledge as-at time. Default: now.

Snapshots per day make this O(postings since snapshot). The snapshot is a cache.

## Price selection

A price series per class holds every published price and every version.

| Policy | Picks |
|--------|-------|
| `official-latest` | Latest official price with pricing date ≤ E and published ≤ K. Highest version. |
| `official-at(point)` | Exactly that pricing point. Used for deals. |
| `indicative-latest` | The latest indicative price if newer than the official one. Flagged as indicative. |

Every selected price returns **provenance**: pricing date, version, kind, published-at, and age in days relative to E.

**Stale prices are shown, never hidden.** Past a pack-defined age the value is flagged stale. The number is still computed.

## Value

```
value = units × price_cpu ÷ 100
```

Rounded to cents at the end, not per component.

An account value is the sum of its lines. The account view reports:

- **oldest price date** across lines,
- **coverage**: share of value priced within one day of E,
- each line's own price basis.

The honesty rule: **no total without its price basis.**

## Near real time

Nothing runs to "revalue". Values are recomputed on read.

- A `PricePublished` event for a class invalidates cache keys that include that class.
- Subscribers (screens, APIs) receive the new value on the next read or by push.
- Units did not change, so the recompute is a multiplication.

For a portfolio manager before the pricing point:

```
expected net flow(class, today) = Σ priced deals today
                                + Σ unpriced deals today valued at last known price
```

This is a view too. It sharpens as instructions arrive up to cut-off.

## Fund NAV interface

The kernel does not compute the NAV in v1. It defines how a NAV enters.

`PublishPrice` carries:

- class, pricing point, cents per unit, kind (official or indicative), version,
- tolerance check results against the previous official and the latest indicative,
- two distinct signers for an official price,
- a source reference to the fund accounting run.

The kernel rejects an official price without four eyes. It rejects a tolerance breach without an override reason. It never overwrites. A later version for a used pricing point starts the correction block.

A future fund accounting module follows the same principle: instrument positions and instrument prices are facts, NAV is a view, and the **official NAV is a signed snapshot** created at the pricing point.

## Bitemporal views in practice

| Question | Query |
|----------|-------|
| Statement for March, as sent | E = 31 March, K = the time it was sent |
| Statement for March, corrected | E = 31 March, K = now |
| What did we think units in issue were at the pricing point | E = the date, K = the pricing time |
| What are units in issue for that date after backdating | E = the date, K = now |

The NAV published for a date used the K = pricing time view. It is not restated when a backdated deal lands. Reconciliations compare per knowledge date. Doc 07 explains the delta.

## Worked examples

**Investor value.** 10 000 units. Official price 1 500.00 cpu published this morning for yesterday's pricing point.

```
value = 10 000 × 1 500.00 ÷ 100 = R150 000.00
price basis: official, 2026-09-11, v1, age 1 day
```

**Account with mixed price dates.** One own fund and two external funds from two mancos. Prices dated 11, 11 and 10 September. The total is shown with oldest price date 10 September and coverage 66%. A one-fund account gets the same view with one line.

**Adviser fee, 0.50% p.a., monthly in arrears.**

```
fee = Σ over days (units_d × official_price_d ÷ 100 × 0.50% ÷ 365)
```

Computed at the fee run from facts. The fee becomes a fact only when executed as a unit cancellation.

**Money market class.** Price constant at 100.00 cpu. Daily declared rate accrues as an entitlement view. It capitalises monthly into units. Between runs nothing is stored.

## What this buys

- A corrected price fixes every screen instantly. No re-run.
- A statement can be reproduced exactly as it was sent, and as it should be today.
- Reconciliation compares facts to facts. Never a stored balance to a stored balance.
- Fund accounting and the register agree on the same definition of units in issue per knowledge date.
