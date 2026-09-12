# ADR-003: Calculate, don't store

**Status:** Accepted

## Context

Stored balances and valuations drift from the facts. A corrected price then needs a re-run, and old reports cannot be reproduced.

## Decision

- Store **units moved, cash moved, published prices** and declarations.
- Compute every value on read: units × selected price, with provenance and age.
- Allow caches keyed by event version and price version. A test proves each cache equals a recompute.

## Consequences

- A corrected price changes every view at once.
- Statements can be reproduced as sent and as corrected.
- Published prices are stored. They are legal facts. That is the "almost" in the brief.
