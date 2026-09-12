# 12. Roadmap

## Phases

| Phase | Builds | Exit criteria |
|-------|--------|---------------|
| **0. Kernel core** | Ledger (bitemporal, money and units), register, prices with versions, valuation, investment and redemption blocks, cash matching, maker-checker, day close | Property tests pass: journals balance, register reconciles, values equal pure recompute. Golden scenarios green. |
| **1. Full block set** | Switch, transfer, distribution, fees, regular instructions, backdating and reversals, price corrections, corporate actions, payments, reconciliations | Every block has postings, reversal and control accounts under test. Break register live. |
| **2. Packs** | Pack DSL, validator, sandbox runtime, simulator, generation pipeline, review workspace, release process | One fictional pack generated from documents. Shadow run tooling replays a synthetic history. |
| **3. Manco pilot** | Pack for one real manco. Adapters: bank, fund accounting, FinSwitch inbound | Shadow run parity with legacy for one quarter. Trustee and auditor walkthrough done. |
| **4. LISP tenant** | Nominee register, bulk dealing, products, models, fee runs, tax outputs | Pilot LISP shadow run. IT3 outputs match. |
| **5. Migration and scale** | Legacy migration tooling, regulatory packs, performance work, second and third tenants | Onboarding a tenant in weeks, repeatably. |

## Pilot approach

1. Pick a manco with a few funds and a cooperative operations team.
2. Generate the pack from its documents and legacy configuration export.
3. Run the **shadow run** for a past quarter. Compare every unit, price, fee and payment.
4. Review differences with the manco. Fix the pack or record the legacy defect.
5. Run in parallel for one live month. Day close on both systems.
6. Cut over with the trustee informed and the auditor briefed.

## Risks and mitigations

| Risk | Mitigation |
|------|------------|
| The model invents a rule | Provenance required. Shadow run. Human review. Kernel invariants stop value errors regardless |
| A regulator or trustee distrusts generated behaviour | The pack is readable and cited. The kernel is fixed and audited once. Early trustee walkthroughs |
| Performance of calculate-on-read at scale | Snapshots and projections as verifiable caches. Values are multiplications |
| Mancos want their old flexibility | Flexibility lives in the pack and is regenerated in days. Controls are the selling point |
| Legacy data is wrong | The shadow run finds it. Migration records known differences with sign-off |
| Fund accounting scope creep | Pricing point contract first. Fund accounting module later on the same principles |

## Open decisions

These need a call from the sponsor. Recommendation first.

| Decision | Recommendation | Alternative |
|----------|----------------|-------------|
| First pilot: manco or LISP | **Manco.** Simpler register, proves the kernel and packs | LISP first for market reach |
| Fund accounting in v1 | **No.** Interface only | Build it, doubles scope |
| Pack language | **Typed declarative DSL** with a small expression language | A general language in a sandbox. More power, harder to validate |
| Sandbox technology | **WebAssembly** with capability-based kernel API | Interpreter in the kernel process |
| Event store | **Purpose-built append-only store** on a managed database | Off-the-shelf event store |
