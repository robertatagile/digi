# ADR-005: Packs are a total DSL in a sandbox

**Status:** Accepted

## Context

Generated code must be safe to run against investor money and easy to validate.

## Decision

- Packs are written in a **declarative, typed, total, deterministic** DSL with a small expression language.
- Packs run in a **sandbox** with no network, clock or randomness. The kernel passes time and prices in.
- Packs can issue **kernel commands only**.

## Consequences

- Validation is static and complete: schema, totality, tighten-only, coverage, segregation.
- Some workflows will feel constrained. The DSL grows by adding kernel primitives, not by allowing arbitrary code.
- WebAssembly is the recommended runtime. An in-process interpreter is the fallback.
