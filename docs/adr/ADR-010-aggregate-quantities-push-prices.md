# ADR-010: Aggregate quantities incrementally. Push prices, not values.

**Status:** Accepted

## Context

Calculate-don't-store puts valuation on the read path. At tens of millions of holdings and thousands of prices a day, a naive read path would sum over holdings for every fund size or adviser book, and a naive write path would invalidate every cached value on every price.

## Decision

- Every unit posting updates the position and a handful of **group aggregates in units**: units in issue, nominee bulk, adviser book, model, product. Group values are O(classes), never O(holdings).
- A price publication writes **one index entry**. Caches are keyed by price version and miss on their own.
- Screens and APIs subscribe to **price versions per class** and recompute their own lines. The platform never pushes a value per holding.
- Positions are **daily snapshots plus deltas**. Snapshots carry the sequence they reflect and are verified by replay.
- Control account balances are **prefix sums over daily totals**. No balance row is ever read, modified and written.
- Bulk runs are **sharded by class, idempotent per holding, checkpointed**, with control totals per shard.

## Consequences

- Publishing a price costs the same for a class with ten holders and a million.
- Fund size and AUM are instant and exact as at a sequence.
- Serialisation points are few and named: an account stream, a class run, an exposure tranche.
- The read path carries the work. It is a multiplication per line, which is the cheapest work there is.
