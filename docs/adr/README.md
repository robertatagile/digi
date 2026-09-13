# Architecture decision records

Short records of the decisions that shape the platform. One file each.

| ADR | Decision |
|-----|----------|
| [001](ADR-001-fixed-kernel-generated-packs.md) | Kernel invariants are fixed. Variability lives in generated Tenant Packs. |
| [002](ADR-002-ledger-as-the-only-integration.md) | A bitemporal, two-dimensional ledger is the only way blocks hand over value. |
| [003](ADR-003-calculate-dont-store.md) | Quantities and prices are facts. Values are computed on read. |
| [004](ADR-004-backdating-needs-a-loss-owner.md) | Every backdated or reversed deal names a loss owner and posts the delta. |
| [005](ADR-005-pack-dsl-in-a-sandbox.md) | Packs are written in a total, deterministic DSL and run in a sandbox. |
| [006](ADR-006-event-sourcing-and-projections.md) | Register and ledger are event sourced. Projections are verifiable caches. |
| [007](ADR-007-controls-tighten-only.md) | Packs can tighten a kernel control. Never loosen one. |
| [008](ADR-008-provenance-on-every-rule.md) | Every generated rule cites its source. |
| [009](ADR-009-legislation-as-a-controlled-object.md) | Legislation is a controlled, versioned object bound to kernel controls and pack rules. |
