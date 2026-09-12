# ADR-004: Backdating and reversals need a loss owner

**Status:** Accepted

## Context

A backdated deal at a historical price moves value between the investor, the fund and whoever caused the delay. On incumbent platforms the fund usually absorbs it silently.

## Decision

- The fund always deals at the **current** price.
- The investor is dealt at the historical price.
- The difference is a **delta** posted to a **loss owner** account named by pack policy per reason code.
- Two approvers, neither the maker. Evidence required. A daily register.
- Reversals use the same mechanism.

## Consequences

- A journal without the delta line does not balance. Backdating without an owner is impossible.
- Finance sees the manco's error cost every day.
- The trustee can see any fund-absorbed amounts and their cap.
