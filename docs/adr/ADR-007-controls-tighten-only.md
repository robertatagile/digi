# ADR-007: Packs tighten controls, never loosen them

**Status:** Accepted

## Context

If a pack could relax a control, the kernel's guarantees would depend on the pack, and the pack is generated.

## Decision

- The kernel defines minimum approvals, limits, clearing rules and day close gates.
- A pack may lower a limit, add an approver, shorten a clearing time or add a gate.
- The pack validator rejects any pack that raises a limit, removes an approver, extends a clearing time or skips a gate.

## Consequences

- Kernel guarantees hold for every tenant regardless of pack quality.
- Tenants who need looser controls cannot have them. That is deliberate.
