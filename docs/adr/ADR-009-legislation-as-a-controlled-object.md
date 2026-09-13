# ADR-009: Legislation is a controlled, versioned object bound to controls

**Status:** Accepted

## Context

Regulatory duties under the FSR Act, COFI, FAIS, CISCA, FICA, POPIA and tax law drive most of a manco's behaviour. On incumbent platforms they are implicit in settings and procedures. Nobody can prove coverage or trace a decision to a duty.

## Decision

- Every Act, standard and notice is an object in a **platform legislation library**. Versioned, effective-dated, cited.
- Each instrument breaks into typed **obligations**: gate, limit, record, report, disclosure, timing, attestation.
- Each tenant keeps an **obligation register** it manages: applicability, owner, bindings to kernel controls, pack rules or manual procedures, attestations.
- The register is under the kernel's control model: maker ≠ checker, effective dating, provenance, immutability, breaks.
- A **coverage gate** blocks pack release while an applicable in-force obligation has no binding or justified exclusion.
- Commands record the obligations they evaluated. A regulatory trail query reads them back.

## Consequences

- Coverage is measurable per Act. COFI readiness is a report, not a project.
- A legislative change is a library version with impact analysis and regenerated pack rules.
- The manco cannot delete or loosen a library obligation. It can add, bind, attest and justify.
- Legislation appears wherever a decision is made: on rules, controls, blocked actions, documents and dashboards.
