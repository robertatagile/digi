# Design documents

Read in order. Each document stands alone.

| # | Document | One line |
|---|----------|----------|
| 01 | [Vision](01-vision.md) | Fixed kernel, generated fit. Principles and scope. |
| 02 | [Architecture](02-architecture.md) | Kernel components, Tenant Packs, time model, runtime shape. |
| 03 | [Domain model](03-domain-model.md) | Entities, relationships, kernel invariants, glossary. |
| 04 | [Building blocks](04-building-blocks.md) | Every block: what is fixed, what the pack decides, the postings. |
| 05 | [Financial controls](05-financial-controls.md) | Control accounts, reconciliations, maker-checker, day close. |
| 06 | [Valuation](06-valuation.md) | Facts versus views. Price selection. Near real-time recompute. |
| 07 | [Backdating and corrections](07-backdating-and-corrections.md) | Two time axes. The delta formula. Loss allocation matrix. |
| 08 | [Cash management](08-cash-management.md) | Money in, money out, settlement, bank reconciliation. |
| 09 | [Tenant Packs, AI generated](09-tenant-packs-ai-generated.md) | The Pack DSL, the generation pipeline, the gates. |
| 10 | [LISP layer](10-lisp-layer.md) | Nominee holdings, bulk dealing, products, fees, tax. |
| 11 | [Regulatory and integration](11-regulatory-and-integration.md) | SA regimes mapped to platform parts. Integration map. |
| 12 | [Roadmap](12-roadmap.md) | Phases, pilot approach, risks, open decisions. |

**Decisions:** [adr/](adr/) holds the architecture decision records.

**Example:** [examples/example-manco-pack/](examples/example-manco-pack/) is a generated pack for a fictional manco.

**Executable model:** [../reference/](../reference/) proves the core invariants in code.
