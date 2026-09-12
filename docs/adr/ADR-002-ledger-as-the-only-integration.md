# ADR-002: The ledger is the only integration between blocks

**Status:** Accepted

## Context

When blocks call each other directly, a failure halfway leaves value nowhere. Reconciliation then compares stored balances to stored balances.

## Decision

- Every block ends with **one balanced journal** and an event.
- Journals balance in **money per currency** and in **units per class**.
- Every posting has an **effective date** and a **posted-at** time.
- Blocks hand over value through **control accounts** with owners, clearing rules and tolerances.

## Consequences

- Any failure is visible as a control account balance.
- Reconciliation compares facts to facts.
- Backdating is a normal posting with an earlier effective date.
- The ledger needs to be fast at as-at queries. Snapshots handle that.
