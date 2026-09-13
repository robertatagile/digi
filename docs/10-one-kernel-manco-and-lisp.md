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

## Product wrappers are guards on the same blocks

A tax-free savings account or a retirement annuity is not a different kind of thing. Money goes **into an instrument** through the investment block. Money comes **out** through the redemption block. The wrapper adds three things, and only three:

1. **Guards** on the blocks. A guard can refuse. It cannot post or change anything.
2. **Holds** on a payable. A held payable cannot be paid until the hold is released with a reference.
3. **Tax side effects and reporting.** Withholding postings, certificates, directives.

The kernel supplies the primitives. The pack, generated per tenant, supplies the rules.

| Kernel primitive | What it is |
|------------------|------------|
| **Pack guard** | A named rule attached to a block command. Runs after the kernel's own checks. Refuses with a message that names the rule and the law. Its tag lands in the journal's evidence. |
| **Component** | A sub-account written `ACCOUNT:component`. Separate unit balances on the same register. FICA and party data live on the root. Two-pot needs three: vested, savings, retirement. |
| **Contribution counter** | Derived from instructions with a cash fact for a period. Never stored. |
| **Hold** | A named condition on a payable, for example `tax_directive`. Releasing it needs a reference and may post withholding. |
| **Scheduled redemption with bounds** | For living annuity income. A regular instruction whose amount must stay inside pack limits. |
| **Transfer block** | Units move without a price. Section 14 transfers and in specie moves at retirement. |

### Product by block

| Product | Investment block | Redemption block | Transfer or switch | Before payment | Tax and reporting |
|---------|------------------|------------------|--------------------|----------------|-------------------|
| **Tax-free savings** | Guard: annual and lifetime contribution counters. Excess refused at cash matching, stays refundable | Unrestricted. Withdrawals do not restore contribution room | Transfers between providers only, no cash out | None | No dividends tax withheld. IT3(s) |
| **Retirement annuity** | Contributions recorded for the IT3(f) certificate. Split across components per the two-pot rules | Guard: retirement and vested components locked before retirement age. Savings component: one withdrawal per tax year, above the minimum | Section 14 transfer. At retirement, an in specie transfer into a living annuity or a lump sum redemption | Hold: `tax_directive`. The release posts the withholding SARS prescribes | Directive per lump sum. Regulation 28 look-through |
| **Preservation fund** | Transfers in only, no contributions | Guard: the one pre-retirement withdrawal rule plus the two-pot component rules | Section 14 in and out | Hold: `tax_directive` | Directive per lump sum |
| **Living annuity** | Funded by transfer in, not by contributions | Scheduled redemptions bounded by the regulated minimum and maximum. Annual review changes the schedule | Transfer between insurers | Hold: `paye` on the income schedule | PAYE per payment. IRP5 |
| **Endowment** | Guard: the contribution rule inside the restriction period | Guard: one surrender inside the restriction period | Cession is a transfer | None | Taxed inside the policyholder fund. No IT3 to the investor |

Every cell is a guard, a hold or a report on a block that already exists. No new blocks.

### A retirement annuity withdrawal, end to end

1. The investor asks for R5 000 from the **savings component**. The kernel receives a redemption on `RA-7:savings`.
2. **Lock units.** The kernel checks available units. Then the pack guard `ra-withdrawal` runs: no earlier savings withdrawal this tax year, amount above the minimum. The journal carries `rule:ra-withdrawal`.
3. **Price.** Units are cancelled at the pricing point. The payable is created **held** for `tax_directive`.
4. **Directive.** Tax operations request the directive from SARS. When it arrives, the hold is released with the directive number. The prescribed tax posts `Dr REDEMPTIONS_PAYABLE · Cr TAX_WITHHELD_PAYABLE`. The evidence carries `obligation:ITA-TAX-DIRECTIVE`.
5. **Pay.** The payment pipeline runs as for any redemption: FICA current, maker and checker, in transit, confirmed.

A retirement component withdrawal at age 40 stops at step 2 with "Blocked by pack rule ra-withdrawal: retirement component is locked before age 55". The units never leave the holding.

The reference model runs this scenario and the tax-free savings one in `reference/tests/test_wrappers.py`.

## Model portfolios and rebalancing

- A model is a recipe: instruments and target weights, versioned. Own and external instruments mix freely.
- Rebalancing is a **generated set of switches** per account, computed on last known prices, executed directly for own instruments and in bulk for external ones. Inside a wrapper the same guards apply to every leg.
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
