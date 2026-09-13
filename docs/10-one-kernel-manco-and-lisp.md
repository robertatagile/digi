# 10. One kernel for manco and LISP

## The visible difference is not a structural one

A unit trust investor holds **one fund**. A LISP investor holds **many funds** across many mancos. That is the visible difference. It is not a reason for two systems.

In the kernel an **account holds N positions in N instruments**. The unit trust investor is the case N = 1. The LISP account is the case N = 30. Nothing in the ledger, the register, the valuation, the cash pipeline or the controls depends on N.

What does change is **who issues the instrument**. That is an attribute on the instrument, not a boundary in the platform.

| | Instrument issued by this tenant (own) | Instrument issued by another manco (external) |
|-|-----------------------------------------|------------------------------------------------|
| **Control total per class** | Units in issue | Nominee bulk holding confirmed by the manco |
| **Register invariant** | Σ holders + box = units in issue | Σ holders + rounding = nominee bulk |
| **Price origin** | Own pricing point, two signers | The manco's confirmation, one signer plus the confirmation reference |
| **Dealing** | Each deal priced at the pricing point | Deals aggregated per class and dealing day, allocated at the confirmed price |
| **Settlement counterparty** | Own custodian | The other manco |
| **Reconciliation source** | Fund accounting units in issue | The manco's statement, usually through FinSwitch |

Same blocks. Same control accounts. Same day close. One attribute.

## Why not build the one-fund case first

Because the one-fund case is the **degenerate** case, and building for it first bakes in three assumptions that are expensive to undo later:

- that a price is always published by us, at our pricing point,
- that the control total is always units in issue,
- that a deal is always priced one by one, never aggregated and allocated.

The extra primitives for the general case are small: an issuer attribute, a bulk instruction, an allocation with a rounding account, and a confirmation that enters as a price. They belong in **phase 0**. The reference model already carries them.

Most mancos are also platforms. They sell tax-free savings and retirement annuities on their own funds. Several run a LISP next to the manco. The tenant type in doc 03 is manco, LISP, or **both** for that reason.

## Bulk dealing and allocation

The kernel block for external instruments.

```mermaid
flowchart LR
  II["Investor instructions before the tenant's cut-off"] --> AG["Aggregate per class and dealing day"]
  AG --> FS["Instruction to the manco"]
  FS --> CF["Confirmation: price and units"]
  CF --> AL["Allocate to investors at the confirmed price"]
  AL --> RC["Reconcile Σ investors to the nominee bulk"]
```

- The tenant's cut-off is earlier than the manco's. The pack sets both.
- Gross or net per manco is a pack choice. Both post the same accounts.
- Until confirmation the investor deal is unpriced. It shows at the last known price. Doc 06.
- The confirmation is a **price fact**. It is published once for the class and dealing day. A later confirmation at a different price is a correction, never an overwrite.
- Allocation rounding posts to `ROUNDING_UNITS:<class>`, a holder-side account. An allocation that differs from the confirmed units by a whole unit or more is a break. Nothing posts until a human resolves it.
- Cash settles to the manco per its terms. `SUBS_PAYABLE_TO_FUND` and `REDEMPTIONS_DUE_FROM_FUND` work per external class.

Postings for a bulk investment of total **A** confirmed at price **P** for **U** units:

| Money | Units |
|-------|-------|
| Dr `SUBS_AWAITING_PRICING` A · Cr `SUBS_PAYABLE_TO_FUND` A | Dr `NOMINEE_BULK` U · Cr `HOLDING:<each investor>` U_i · Cr or Dr `ROUNDING_UNITS` (U − Σ U_i) |

One journal. One command. Every investor deal references it.

## Nominee register

```
Σ investor holdings(class) + rounding = nominee bulk holding at the manco(class)
```

Reconciled daily against the manco's statement. Differences are breaks with an owner. Rounding never reaches an investor.

## Products as pack rules

Product rules change with legislation. They belong in the pack, generated and effective-dated. The kernel supplies **components** and **restrictions**. They apply to any tenant that sells the product, manco or LISP.

| Product | Typical pack rules | Kernel primitive |
|---------|--------------------|------------------|
| Discretionary | Free dealing. CGT on switches | Tax lots per deal |
| Tax-free savings | Annual and lifetime contribution limits | Contribution counters per tax year |
| Retirement annuity | No withdrawal before retirement age except as allowed. Regulation 28 limits. Two-pot components | Components with separate unit balances. Restriction flags |
| Preservation fund | One withdrawal rule. Two-pot components. Section 14 transfers | Components. Transfer block |
| Living annuity | Income between the regulated minimum and maximum. Annual review | Scheduled redemptions with bounds |
| Endowment | Restriction period. Contribution limits within the period | Restriction flags, contribution counters |

Numeric limits and rates are **pack parameters** with a source and an effective date. Never hard-coded in the kernel.

**Two-pot** is the clearest case for generation over configuration. In the kernel it is a redemption on a component with a restriction. In the pack it is a rule with a citation and a test.

## Model portfolios and rebalancing

- A model is a recipe: instruments and target weights, versioned. Own and external instruments mix freely.
- Rebalancing is a **generated set of switches** per account, computed on last known prices, executed directly for own instruments and in bulk for external ones.
- Phasing in is a schedule of switches out of a cash instrument.
- Drift tolerance, frequency and exclusions are pack rules.

## Fees across N instruments

| Fee | Mechanism |
|-----|-----------|
| Platform administration fee | Tiered on account value, computed daily from facts, collected monthly by unit cancellation pro rata across holdings |
| Adviser initial fee | Deducted from the amount before units |
| Adviser ongoing fee | Pack formula, collected by unit cancellation, VAT as a separate line |
| Manco rebates | Received on non-clean external classes, allocated to investors or retained per pack rule |
| Clean classes | No rebate. The pack maps each class |

The fee run reconciles claims to cancellations to payments. A fee on an external class is a bulk redemption like any other.

## Cash

- Investor trust accounts per tenant, segregated.
- A money market instrument often acts as the **settlement hub**. Contributions land there, then switch out. Redemptions land there, then pay out.
- Settlement to and from each manco follows that manco's terms. The kernel tracks each leg in the control accounts.

## Tax and reporting

| Output | Source |
|--------|--------|
| IT3(b) interest and dividends | Distribution components per account, across all instruments |
| IT3(c) capital gains | Tax lots per deal, method per pack |
| IT3(s) tax-free savings | Contribution counters and balances |
| Dividends tax | Withholding at distribution, exemptions per party |
| Tax directives | Requested from SARS before retirement product withdrawals. Payment waits for the directive |
| Regulation 28 monitoring | Look-through on model and fund data, per account |

Every figure is a query over facts. Certificates record the knowledge time they were produced at.

## Valuation across many issuers

Prices arrive at different times from different mancos. Some are T+1. The account value shows:

- each line with its own price date and version,
- the total with the oldest price date,
- coverage: share of value priced within one day.

A late price from one manco updates that line on the next read. Nothing is re-run. The one-fund account gets the same view with one line.
