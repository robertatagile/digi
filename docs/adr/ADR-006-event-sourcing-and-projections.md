# ADR-006: Event sourcing with verifiable projections

**Status:** Accepted

## Context

Bitemporal queries, reproducible statements and audit all need the full history of facts.

## Decision

- Ledger and register events are the **system of record**, append-only.
- Read models are **projections**. Each has a test proving equality with a pure recompute.
- Snapshots exist for performance and carry the event version they cover.

## Consequences

- Any balance can be replayed as at any pair of dates.
- Storage grows with history. Snapshots and archiving handle scale.
- Every projection needs a recompute test. That is a feature.
