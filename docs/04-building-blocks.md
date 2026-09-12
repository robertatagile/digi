# 4. Building blocks

## The block contract

Every block obeys the same contract. No exceptions.

| Element | Rule |
|---------|------|
| **Command** | Typed. Idempotent by command id. Carries actor, tenant, pack version, evidence references. |
| **Preconditions** | Kernel invariants first. Then pack guards. A pack can only add conditions. |
| **Effect** | Exactly one balanced journal in money and units. Events emitted after commit. |
| **Control accounts** | The block draws from one control account and leaves value in the next. |
| **Postconditions** | Registered with the control plane: expected clearing time and tolerance. |
| **Reversal** | Defined for every block. Never a delete. Always a new journal with a reason and a loss owner where a price is involved. |

## Fixed versus pack-decided

| Block | Kernel fixes | Pack decides |
|-------|--------------|--------------|
| Instruction intake | Received-at, evidence, status machine, in-good-order flag | Channels, document checks, cut-off rules, holds |
| Investment | Postings, control accounts, pricing at a published price | Minimums, initial fee formula, eligibility, units-on-cleared-funds policy |
| Redemption | Available units check, cancellation postings, payable creation | Approval tiers, bank detail cooling-off period, ring-fencing thresholds |
| Switch | Atomic two legs through switch clearing | Which classes may switch, same-day or lagged legs |
| Transfer | Units-only journal, tax lots carried | Which transfers are allowed per product |
| Distribution | Record-date derivation, entitlement maths, rounding account | Frequency, default option, reinvestment price rule |
| Fees | Execution as unit cancellation or cash deduction, payable creation | Formulas, tiers, VAT treatment, beneficiaries, frequency |
| Regular instructions | Scheduling, child instruction lineage, exposure posting | Collection method, retry rules, units-on-collection policy |
| Pricing | Versions, four-eyes on official prices, tolerance check | Tolerance values, pricing points, calendars |
| Backdating and reversals | Delta formula, loss owner required, approvals required | Reason codes, owner per reason, approver roles |
| Corporate actions | Conversion at ratio with rounding account, compulsory redemption | Ratios, dates, communications |
| Day close | Checklist gates, locking | Tighter gates, extra checks |

## Standard control accounts

Money accounts are per fund and currency. Unit accounts are per class.

| Money | Meaning |
|-------|---------|
| `BANK:<account>` | Cash at a specific bank account. |
| `UNALLOCATED_CASH` | Receipts with no matched instruction. |
| `SUBS_AWAITING_PRICING` | Matched cash waiting for the pricing point. |
| `SUBS_PAYABLE_TO_FUND` | Priced, units issued, cash owed to the fund's custodian. |
| `SETTLEMENT_EXPOSURE` | Units issued before cleared funds. Manco risk. |
| `REDEMPTIONS_DUE_FROM_FUND` | Units cancelled, fund must settle. |
| `REDEMPTIONS_PAYABLE` | Cash owed to investors. |
| `PAYMENTS_IN_TRANSIT` | Instructed, not yet confirmed by the bank. |
| `SWITCH_CLEARING` | Between the out leg and the in leg. |
| `DISTRIBUTIONS_PAYABLE` | Declared entitlements not yet paid or reinvested. |
| `FEES_PAYABLE:<beneficiary>` | Adviser, manco, platform. |
| `TAX_WITHHELD_PAYABLE` | DWT, IWT, directive tax. |
| `MANCO_ERROR_ACCOUNT` | The manco's own P&L for deltas it owns. |
| `INTERMEDIARY_ACCOUNT:<party>` | Deltas attributed to a LISP or adviser. |
| `FUND_DILUTION_ACCOUNT` | Deltas the deed allows the fund to absorb. Capped and reported. |
| `ROUNDING` | Rounding differences. |

| Units | Meaning |
|-------|---------|
| `UNITS_IN_ISSUE:<class>` | Control. Debit balance. |
| `HOLDING:<account>:<class>` | Investor position. Credit balance. |
| `HOLDING_LOCKED:<account>:<class>` | Reserved for a pending redemption or fee. Still held. |
| `BOX:<class>` | Manco-owned units. |

## Block by block

### Instruction intake

**Purpose.** Turn an arriving intent into an immutable instruction with a dealing date.

- Kernel records **received-at** from the server clock. Never from the form.
- The pack's cut-off rule maps received-at to a **dealing date**. The kernel stores both and the rule version.
- **In good order** is a kernel flag. The pack decides which documents and checks set it.
- An instruction that is not in good order at cut-off moves to the **next** dealing date. Honouring the original date is a backdating decision. Doc 07.
- Duplicate detection by content hash and channel reference.

Events: `InstructionReceived`, `InstructionHeld`, `InstructionInGoodOrder`, `InstructionRejected`.

### Investment

**Purpose.** Issue units for cash at a published price.

Steps and postings for amount **A**, initial fee **F**, price **P**, units **U = (A − F) ÷ P**:

| Step | Money | Units |
|------|-------|-------|
| Bank line arrives | Dr `BANK` A · Cr `UNALLOCATED_CASH` A | |
| Matched to instruction | Dr `UNALLOCATED_CASH` A · Cr `SUBS_AWAITING_PRICING` A | |
| Priced at pricing point | Dr `SUBS_AWAITING_PRICING` A · Cr `SUBS_PAYABLE_TO_FUND` (A − F) · Cr `FEES_PAYABLE:adviser` F | Dr `UNITS_IN_ISSUE` U · Cr `HOLDING` U |
| Swept to custodian | Dr `SUBS_PAYABLE_TO_FUND` (A − F) · Cr `BANK` (A − F) | |

**Units before cleared funds.** If the pack allows units on receipt or on collection day, the first line is replaced by Dr `SETTLEMENT_EXPOSURE` A. The exposure clears when cash arrives. A pack limit caps the exposure per fund and per tenant. Breach blocks new exposure.

**Kernel checks.** FICA status allows dealing. Price exists for the pricing point. Dealing date is not closed. Amount matches the cash fact or exposure rule.

Events: `CashMatched`, `DealPriced`, `UnitsIssued`, `ConfirmationDue`.

### Redemption

**Purpose.** Cancel units at a published price and pay the investor.

Steps for **U** units at price **P**, amount **M = U × P**, tax withheld **T**:

| Step | Money | Units |
|------|-------|-------|
| Validated | | Dr `HOLDING` U · Cr `HOLDING_LOCKED` U |
| Priced | Dr `REDEMPTIONS_DUE_FROM_FUND` M · Cr `REDEMPTIONS_PAYABLE` (M − T) · Cr `TAX_WITHHELD_PAYABLE` T | Dr `HOLDING_LOCKED` U · Cr `UNITS_IN_ISSUE` U |
| Fund settles | Dr `BANK` M · Cr `REDEMPTIONS_DUE_FROM_FUND` M | |
| Payment instructed | Dr `REDEMPTIONS_PAYABLE` (M − T) · Cr `PAYMENTS_IN_TRANSIT` (M − T) | |
| Bank confirms | Dr `PAYMENTS_IN_TRANSIT` (M − T) · Cr `BANK` (M − T) | |

**Available units** = holding − locked − pledged. An amount-based redemption is converted at the pricing point. It is capped at available units.

**Kernel checks.** Beneficiary bank account verified. Bank detail cooling-off honoured if the pack sets one. Approvals present per tier. FICA current. Ring-fencing decision recorded when the pack threshold is hit.

**Ring-fencing.** The kernel supports partial fill and deferral. The pack sets the threshold and approver. Deferred units stay locked at the deferred dealing date.

Events: `UnitsLocked`, `DealPriced`, `UnitsCancelled`, `PayableCreated`, `PaymentInstructed`, `PaymentConfirmed`, `PaymentReturned`.

### Switch

**Purpose.** Redeem one class and invest in another, atomically.

- Out leg posts like a redemption but credits `SWITCH_CLEARING` instead of `REDEMPTIONS_PAYABLE`.
- In leg posts like an investment drawn from `SWITCH_CLEARING`.
- Both legs commit together or neither does.
- Different pricing points (15:00 local, 17:00 foreign, T+1 feeder) are supported. Cash rests in switch clearing until the in-leg price exists.
- Net cash between funds settles through the custodian sweep.

### Transfer and re-registration

**Purpose.** Move units between accounts without a price.

- Units only: Dr `HOLDING:A` U · Cr `HOLDING:B` U.
- No money moves. No price is used.
- Tax lots and base cost travel with the units.
- Typical cases: estates, nominee to direct, section 14 transfers on the LISP side, product conversions.

### Distribution

**Purpose.** Allocate declared income to holders at the record date.

- Declaration per class: cents per unit **D**, tax components, record date, pay date.
- Holdings at record date are **derived** as at that effective date. Nothing is snapshotted in advance.
- Entitlement per account **E = units × D**, rounded per pack. Σ rounding differences post to `ROUNDING`.
- Money: Dr `DISTRIBUTIONS_DUE_FROM_FUND` ΣE · Cr `DISTRIBUTIONS_PAYABLE` ΣE − ΣT · Cr `TAX_WITHHELD_PAYABLE` ΣT.
- **Reinvest:** Dr `DISTRIBUTIONS_PAYABLE` E · Cr `SUBS_PAYABLE_TO_FUND` E, and units issued at the reinvestment price.
- **Pay out:** through the payment pipeline.
- **Money market classes:** the price is constant. Daily declared rates accrue as derived entitlements and capitalise monthly. Nothing is stored between runs.

### Fees

**Purpose.** Collect investor-level fees safely.

- Fund-level fees (management, performance) accrue inside the NAV. The register sees them only through the price.
- Investor-level fees (initial, adviser ongoing, platform) are **fee claims** calculated by the pack.
- The kernel executes a claim as a unit cancellation at a pricing point, or a cash deduction before units.
- Money: Dr `FEES_DUE_FROM_FUND` F · Cr `FEES_PAYABLE:<beneficiary>` F. VAT is a separate posting line.
- The fee run reconciles: claims = cancellations = payments.

### Regular instructions

**Purpose.** Debit orders, phased investments, scheduled withdrawals.

- The kernel schedules and creates **child instructions** with lineage to the parent mandate.
- Collections leave through the pack's bank format. Expected receipts are created.
- **Units on collection day** uses `SETTLEMENT_EXPOSURE` under a limit.
- An unpaid collection after units were issued triggers a **reversal with a loss owner**. Doc 07.

### Pricing and price corrections

**Purpose.** Accept prices as facts and handle corrections without rewriting.

- `PublishPrice` needs class, pricing point, cents per unit, kind, version, source reference.
- **Official** prices need two distinct signers. Indicative prices need one.
- Tolerance check against the previous official price and the latest indicative. A breach needs an explicit override with a reason.
- A new version for an already-used pricing point starts the **correction block**. Doc 07.

### Backdating and reversals

Covered fully in doc 07. In short: the fund always deals at the current price. The historical price is honoured by a named owner. The delta is posted. Two approvals. A daily register.

### Corporate actions

- **Conversion at ratio:** cancel old units, issue new units at the ratio, rounding to `ROUNDING`.
- **Fund merger:** conversion across funds on the effective date, no cash.
- **Termination:** compulsory redemption at the final price through the redemption block.
- **Class close or rename:** static data event with an effective date.

### Day close

Per tenant and dealing date. Gates:

1. Every instruction for the date is priced, deferred, or in a documented exception.
2. Official prices exist for every class that dealt.
3. Register reconciles to fund accounting units in issue.
4. Bank reconciliation done. Unmatched items are aged breaks, not silence.
5. Control accounts are within tolerance or have an owned break.
6. Every backdating and reversal for the day is approved and posted.

Passing the gates **locks** the effective date. The pack may add gates. It cannot remove one.

### Reporting and communications

- Confirmations, statements, tax certificates and regulatory files are **as-at queries** rendered by the pack's templates.
- A rendered document records the knowledge time and every price version it used.
- Re-running the same query later may differ. Both renderings are kept.
