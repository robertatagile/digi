# ADR-008: Provenance on every generated rule

**Status:** Accepted

## Context

Auditors, trustees and operations need to know why a fee, a cut-off or a policy is what it is. Generated content needs that more, not less.

## Decision

- Every pack rule carries a `source` with document, section and quote, or an explicit `assumption` with an owner.
- Ambiguities become **open questions** that block release until answered.
- The kernel stamps the pack version on every command and journal.

## Consequences

- A fee on a statement traces to a deed paragraph.
- Generation quality is measurable: share of rules with a real source.
- Documents must be ingested with stable references.
