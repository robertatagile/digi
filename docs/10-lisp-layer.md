# 10. The LISP layer

## Same kernel, different tenant

A LISP is a tenant. It runs the same kernel and the same blocks. Its pack differs.

| Manco tenant | LISP tenant |
|--------------|-------------|
| Issues its own units | Holds other mancos' units in a nominee |
| Publishes prices | Consumes prices from many mancos |
| Units in issue is the control total | The nominee bulk holding per class is the control total |
| Deals at its own pricing point | Deals in bulk with each manco at the manco's cut-off |
| Products are simple accounts | Products are wrappers with rules: TFSA, RA, preservation, living annuity, endowment |
| Fees: initial, adviser | Fees: platform, adviser, rebates, clean classes |

## Nominee register

The control invariant changes shape but not nature.

```
Σ investor holdings(class) = nominee bulk holding at the manco(class)
```

Reconciled daily against the manco's statement, typically through FinSwitch. Differences are breaks with an owner. Unit rounding in allocation posts to `ROUNDING`, never to an investor.

## Bulk dealing

```mermaid
flowchart LR
  II["Investor instructions before LISP cut-off"] --> AG["Aggregate per manco, class, dealing day"]
  AG --> FS["FinSwitch instruction to manco"]
  FS --> CF["Manco confirmation with price"]
  CF --> AL["Allocate units to investors at that price"]
  AL --> RC["Reconcile bulk vs Σ investors"]
```

- The LISP cut-off is earlier than the manco's. The pack sets both.
- Gross or net bulk per manco is a pack choice. Some mancos want gross buys and sells.
- Investor allocation uses the **confirmed** price. Until then the investor deal is unpriced and shows at last known price. Doc 06.
- Cash settles to each manco per its terms. `SUBS_PAYABLE_TO_FUND` and `REDEMPTIONS_DUE_FROM_FUND` work per external class.

## Products as pack rules

Product rules change with legislation. They belong in the pack, generated and effective-dated. The kernel supplies **components** and **restrictions** as primitives.

| Product | Typical pack rules | Kernel primitive |
|---------|--------------------|------------------|
| Discretionary | Free dealing. CGT on switches | Tax lots per deal |
| Tax-free savings | Annual and lifetime contribution limits | Contribution counters per tax year |
| Retirement annuity | No withdrawal before retirement age except as allowed. Regulation 28 limits. Two-pot components | Components with separate unit balances. Restriction flags |
| Preservation fund | One withdrawal rule. Two-pot components. Section 14 transfers | Components. Transfer block |
| Living annuity | Income between the regulated minimum and maximum. Annual anniversary review | Scheduled redemptions with bounds |
| Endowment | Restriction period. Contribution limits within the period | Restriction flags, contribution counters |

Numeric limits and rates are **pack parameters** with a source and an effective date. They are never hard-coded in the kernel.

**Two-pot** is the clearest case for generation over configuration. A savings withdrawal is a redemption limited to one component, once per tax year, with a tax directive. In the kernel it is a redemption on a component with a restriction. In the pack it is a rule with a source and a test.

## Model portfolios and rebalancing

- A model is a recipe: classes and target weights, versioned.
- Rebalancing is a **generated set of switches** per account, computed on last known prices, executed as bulk deals.
- Phasing in is a schedule of switches out of a cash class.
- Drift tolerance, frequency and exclusions are pack rules.

## Fees on the platform

| Fee | Mechanism |
|-----|-----------|
| Platform administration fee | Tiered on account value, computed daily from facts, collected monthly by unit cancellation across holdings |
| Adviser initial fee | Deducted from the amount before units |
| Adviser ongoing fee | Pack formula, collected by unit cancellation, VAT as a separate line |
| Manco rebates | Received from mancos on non-clean classes, allocated to investors or retained per pack rule |
| Clean classes | No rebate. Pack maps each class |

The fee run reconciles claims to cancellations to payments. Fee claims are computed at run time from units and prices. They are stored only once executed.

## Cash on the platform

- Investor trust accounts per LISP, segregated.
- A money market class often acts as the **settlement hub**. Contributions land there, then switch out. Redemptions land there, then pay out.
- Settlement to and from mancos follows each manco's terms. The kernel tracks each leg in the control accounts.

## Tax and reporting

| Output | Source |
|--------|--------|
| IT3(b) interest and dividends | Distribution components per account |
| IT3(c) capital gains | Tax lots per deal, method per pack (weighted average, FIFO, specific) |
| IT3(s) tax-free savings | Contribution counters and balances |
| Dividends tax | Withholding at distribution, exemptions per party |
| Tax directives | Requested from SARS before retirement product withdrawals. Payment waits for the directive |
| Regulation 28 monitoring | Look-through on model and fund data, per account |

Every figure is a query over facts. Certificates record the knowledge time they were produced at.

## Valuation with many mancos

Prices arrive at different times from different mancos. Some are T+1. The account value shows:

- each line with its own price date and version,
- the total with the oldest price date,
- coverage: share of value priced within one day.

A late price from one manco updates that line on the next read. Nothing is re-run.
