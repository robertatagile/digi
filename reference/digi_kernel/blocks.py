"""Building blocks on top of the ledger, prices, register and controls.

Covers: investment, redemption, payment (I8), settlement exposure (I4), backdating with a delta
and a loss owner (I7), reversal of unpaid collections, price corrections (I10), day close (I11).

The fund always deals at the current price. The historical price is honoured by a named owner.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Callable, Iterable, Optional

from .controls import Approval, ControlError, DayClose, LossPolicy, require_approvals
from .ledger import Journal, Ledger, Posting, cr, dr
from .prices import Price, PriceBook
from .register import Register, holding_account, in_issue_account, locked_account, nominee_bulk_account, rounding_units_account
from .valuation import AccountValuation, cpu_to_amount, value_account

ZERO = Decimal("0")
UNIT_STEP = Decimal("0.0001")
ZAR = "ZAR"

# Control accounts. Names match docs/04-building-blocks.md.
TAX_WITHHELD = "TAX_WITHHELD_PAYABLE"
MANCO_ERROR = "MANCO_ERROR_ACCOUNT"

# Obligations the kernel's own gates serve. Tags land in journal evidence as "obligation:<id>".
FICA_CDD = "FICA-CDD"
CISCA_FORWARD_PRICING = "CISCA-FORWARD-PRICING"
FAIS_LICENCE = "FAIS-ADVISER-LICENCE"
SWITCH_CLEARING = "SWITCH_CLEARING"
ROUNDING = "ROUNDING"


def bank(bank_account: str) -> str:
    return f"BANK:{bank_account}"


def unallocated(fund: str) -> str:
    return f"UNALLOCATED_CASH:{fund}"


def awaiting_pricing(fund: str) -> str:
    return f"SUBS_AWAITING_PRICING:{fund}"


def payable_to_fund(fund: str) -> str:
    """Cash owed to the fund's custodian, from any source."""
    return f"SUBS_PAYABLE_TO_FUND:{fund}"


def exposure(fund: str) -> str:
    return f"SETTLEMENT_EXPOSURE:{fund}"


def due_from_fund(fund: str) -> str:
    return f"REDEMPTIONS_DUE_FROM_FUND:{fund}"


def redemptions_payable(fund: str) -> str:
    return f"REDEMPTIONS_PAYABLE:{fund}"


def in_transit(fund: str) -> str:
    return f"PAYMENTS_IN_TRANSIT:{fund}"


def fees_payable(beneficiary: str) -> str:
    return f"FEES_PAYABLE:{beneficiary}"


def fees_due_from_fund(fund: str) -> str:
    return f"FEES_DUE_FROM_FUND:{fund}"


def distributions_payable(fund: str) -> str:
    return f"DISTRIBUTIONS_PAYABLE:{fund}"


def distributions_due_from_fund(fund: str) -> str:
    return f"DISTRIBUTIONS_DUE_FROM_FUND:{fund}"


def to_units(amount: Decimal, cpu: Decimal) -> Decimal:
    """Units bought with an amount at a cents-per-unit price. Rounded half-up to 4 decimals."""
    return (amount * Decimal(100) / cpu).quantize(UNIT_STEP, rounding=ROUND_HALF_UP)


class BlockError(Exception):
    """Raised when a block's preconditions are not met."""


# A pack guard looks at the kernel and the subject of a command and returns a refusal message, or None.
# Guards run after the kernel's own checks. They can refuse. They cannot post or change anything (C10).
Guard = Callable[["Kernel", object], Optional[str]]


def account_root(account: str) -> str:
    """Components are sub-accounts written ACCOUNT:component. FICA and party data live on the root."""
    return account.split(":", 1)[0]


@dataclass
class BankLine:
    id: str
    bank_account: str
    fund: str
    amount: Decimal
    reference: str
    at: datetime
    matched: bool = False


@dataclass
class Instruction:
    id: str
    account: str
    class_id: str
    fund: str
    kind: str  # "invest" or "redeem"
    received_at: datetime
    dealing_date: date
    amount: Optional[Decimal] = None
    units: Optional[Decimal] = None
    in_good_order: bool = True
    status: str = "received"
    funded_amount: Decimal = ZERO
    on_exposure: bool = False


@dataclass
class Deal:
    id: str
    instruction_id: str
    account: str
    class_id: str
    fund: str
    kind: str
    units: Decimal
    investor_amount: Decimal  # what the investor paid or is paid
    fund_amount: Decimal  # what the fund received or paid, always at the price the fund dealt at
    fee: Decimal
    price: Price  # the price the investor was dealt at
    effective_date: date
    journal_id: str
    on_exposure: bool = False
    reversed: bool = False


@dataclass
class BulkInstruction:
    """Instructions for an external instrument, aggregated per class and dealing day."""

    id: str
    class_id: str
    fund: str
    dealing_date: date
    instruction_ids: tuple[str, ...]
    amount: Decimal
    excluded: tuple[tuple[str, str], ...] = ()  # (instruction id, reason)
    status: str = "submitted"  # submitted, allocated
    confirmation_ref: Optional[str] = None
    journal_id: Optional[str] = None


@dataclass
class Payable:
    id: str
    fund: str
    account: str  # the beneficiary: an investor account, or an adviser for a fee
    amount: Decimal
    deal_id: str
    ledger_account: str  # the payable control account this payment draws from
    kind: str = "redemption"  # redemption, distribution, fee
    status: str = "open"  # open, in_transit, paid
    holds: set = field(default_factory=set)  # a held payable cannot be paid, e.g. "tax_directive"


@dataclass
class SwitchInstruction:
    id: str
    account: str
    from_class: str
    to_class: str
    from_fund: str
    to_fund: str
    units: Decimal
    received_at: datetime
    dealing_date: date
    status: str = "received"


@dataclass(frozen=True)
class TransferRequest:
    from_account: str
    to_account: str
    class_id: str
    units: Decimal
    reason: str


@dataclass
class Entitlement:
    account: str
    units: Decimal
    gross: Decimal
    tax: Decimal
    net: Decimal
    option: str = "reinvest"  # reinvest or payout


@dataclass
class Distribution:
    id: str
    class_id: str
    fund: str
    cpu: Decimal
    record_date: date
    pay_date: date
    tax_rate: Decimal
    signed_by: tuple[str, ...]
    status: str = "declared"  # declared, allocated, settled
    declared_total: Decimal = ZERO
    rounding: Decimal = ZERO
    entitlements: dict = field(default_factory=dict)
    journal_id: Optional[str] = None


@dataclass(frozen=True)
class BackdatingRecord:
    deal_id: str
    kind: str
    reason: str
    owner: str
    delta: Decimal  # positive: the owner paid. negative: the owner received.
    historical_price: Optional[Price]
    current_price: Price
    approvers: tuple[str, ...]
    evidence: tuple[str, ...]


@dataclass(frozen=True)
class CorrectionRecord:
    class_id: str
    pricing_date: date
    old_cpu: Decimal
    new_cpu: Decimal
    error_ratio: Decimal
    material: bool
    adjustments: tuple[tuple[str, str, Decimal], ...]  # (deal id, "units" or "money", difference)


class Kernel:
    """One tenant's kernel instance. Every command goes through here."""

    def __init__(
        self,
        *,
        tenant: str,
        pack_version: str,
        loss_policy: Optional[LossPolicy] = None,
        exposure_limit: Optional[Decimal] = None,
        price_tolerance: Decimal = Decimal("0.05"),
    ) -> None:
        self.tenant = tenant
        self.pack_version = pack_version
        self.ledger = Ledger()
        self.prices = PriceBook(movement_tolerance=price_tolerance)
        self.register = Register(self.ledger)
        self.day_close = DayClose()
        self.loss_policy = loss_policy or LossPolicy()
        self.exposure_limit = exposure_limit
        self.bank_lines: dict[str, BankLine] = {}
        self.instructions: dict[str, Instruction] = {}
        self.deals: dict[str, Deal] = {}
        self.payables: dict[str, Payable] = {}
        self.backdating_register: list[BackdatingRecord] = []
        self.corrections: list[CorrectionRecord] = []
        self.kyc_status: dict[str, str] = {}  # account -> "verified" | "expired" | "pending"
        self.instruments: dict[str, str] = {}  # class id -> "own" | "external"
        self.bulks: dict[str, BulkInstruction] = {}
        self.guards: dict[str, list[tuple[str, Guard]]] = {}  # command -> [(rule name, guard)]
        self.switches: dict[str, SwitchInstruction] = {}
        self.distributions: dict[str, Distribution] = {}
        self.adviser_status: dict[str, str] = {}  # adviser -> licensed | lapsed | debarred
        self._seq = 0

    # ------------------------------------------------------------------ helpers

    def _next_id(self, prefix: str) -> str:
        self._seq += 1
        return f"{prefix}{self._seq:06d}"

    def _journal(
        self,
        *,
        effective_date: date,
        at: datetime,
        postings: Iterable[Posting],
        actor: str,
        command: str,
        reason: str = "",
        evidence: Iterable[str] = (),
    ) -> Journal:
        return self.ledger.post(
            Journal(
                id=self._next_id("J"),
                effective_date=effective_date,
                posted_at=at,
                postings=tuple(postings),
                actor=actor,
                command=command,
                pack_version=self.pack_version,
                reason=reason,
                evidence=tuple(evidence),
            )
        )

    def _instruction(self, instruction_id: str, *, kind: str) -> Instruction:
        try:
            ins = self.instructions[instruction_id]
        except KeyError:
            raise BlockError(f"unknown instruction {instruction_id}") from None
        if ins.kind != kind:
            raise BlockError(f"instruction {instruction_id} is a {ins.kind}, not a {kind}")
        return ins

    def _current_price(self, class_id: str, at: datetime) -> Price:
        price = self.prices.select(class_id, effective_as_at=at.date(), knowledge_as_at=at)
        if price is None:
            raise BlockError(f"no official price known for {class_id} at {at}")
        return price

    def register_instrument(self, *, class_id: str, issuer: str) -> None:
        """Who issues the instrument. An attribute, not a system boundary."""
        if issuer not in ("own", "external"):
            raise BlockError(f"issuer must be own or external, not {issuer!r}")
        self.instruments[class_id] = issuer

    def issuer_of(self, class_id: str) -> str:
        return self.instruments.get(class_id, "own")

    def add_guard(self, *, command: str, rule: str, guard: Guard) -> None:
        """A pack adds a named guard to a block. Product wrappers such as TFSA and RA are built from these."""
        self.guards.setdefault(command, []).append((rule, guard))

    def _pack_guards(self, command: str, subject: object) -> list[str]:
        """Run the pack's guards for a command. Kernel checks always run first. Returns evidence tags."""
        tags: list[str] = []
        for rule, guard in self.guards.get(command, []):
            message = guard(self, subject)
            if message:
                raise ControlError(f"Blocked by pack rule {rule}: {message}")
            tags.append(f"rule:{rule}")
        return tags

    def contributions(self, account: str, *, start: date, end: date) -> Decimal:
        """Money accepted into an account in a period. Derived from instructions with a cash fact. Never stored."""
        total = ZERO
        for ins in self.instructions.values():
            if (
                ins.account == account and ins.kind == "invest"
                and ins.status in ("matched", "in_bulk", "priced")
                and start <= ins.dealing_date <= end
            ):
                total += ins.funded_amount
        return total

    def set_kyc_status(self, *, account: str, status: str, actor: str, at: datetime) -> None:
        """FICA customer due diligence status. A kernel flag with controlled transitions."""
        if status not in ("verified", "expired", "pending"):
            raise BlockError(f"unknown KYC status {status!r}")
        self.kyc_status[account] = status

    def set_adviser_status(self, *, adviser: str, status: str, actor: str, at: datetime) -> None:
        """FSP licence status from the FSCA register. A kernel flag with controlled transitions."""
        if status not in ("licensed", "lapsed", "debarred"):
            raise BlockError(f"unknown adviser status {status!r}")
        self.adviser_status[adviser] = status

    def _require_adviser_licensed(self, adviser: str) -> str:
        """The FAIS gate. No adviser fee is released to a lapsed or debarred FSP."""
        status = self.adviser_status.get(adviser, "unknown")
        if status != "licensed":
            raise ControlError(f"Blocked by {FAIS_LICENCE}: adviser {adviser} is {status}; fee release refused")
        return f"obligation:{FAIS_LICENCE}"

    def _require_kyc(self, account: str, action: str) -> str:
        """The FICA-CDD gate. Blocks dealing and payment for an account that is not verified."""
        status = self.kyc_status.get(account_root(account), "pending")
        if status != "verified":
            raise ControlError(f"Blocked by {FICA_CDD}: account {account} is {status}; {action} refused")
        return f"obligation:{FICA_CDD}"

    def regulatory_trail(self, obligation_id: str, *, since: Optional[datetime] = None, until: Optional[datetime] = None) -> list[Journal]:
        """Every journal that evaluated an obligation. Answers an FSCA or FIC information request."""
        tag = f"obligation:{obligation_id}"
        return [
            j for j in self.ledger.journals()
            if tag in j.evidence
            and (since is None or j.posted_at >= since)
            and (until is None or j.posted_at <= until)
        ]

    def _new_deal(self, **kwargs) -> Deal:
        deal = Deal(id=self._next_id("D"), **kwargs)
        self.deals[deal.id] = deal
        return deal

    # ------------------------------------------------------------------- prices

    def publish_price(
        self,
        *,
        class_id: str,
        pricing_date: date,
        cpu: Decimal,
        at: datetime,
        signed_by: Iterable[str],
        kind: str = "official",
        override_reason: Optional[str] = None,
    ) -> Price:
        version = len(self.prices.versions(class_id, pricing_date, kind)) + 1
        price = Price(class_id, pricing_date, version, Decimal(cpu), kind, at, tuple(signed_by))
        return self.prices.publish(price, override_reason=override_reason)

    # ----------------------------------------------------------------- money in

    def receive_cash(self, *, bank_account: str, fund: str, amount: Decimal, reference: str, at: datetime, actor: str) -> BankLine:
        amount = Decimal(amount)
        if amount <= 0:
            raise BlockError("a bank receipt must be positive")
        line = BankLine(id=self._next_id("BL"), bank_account=bank_account, fund=fund, amount=amount, reference=reference, at=at)
        self.bank_lines[line.id] = line
        self._journal(
            effective_date=at.date(), at=at, actor=actor, command="ReceiveCash",
            postings=[dr(bank(bank_account), "money", ZAR, amount), cr(unallocated(fund), "money", ZAR, amount)],
            evidence=[f"bankline:{line.id}"],
        )
        return line

    def receive_instruction(
        self,
        *,
        id: str,
        account: str,
        class_id: str,
        fund: str,
        kind: str,
        received_at: datetime,
        dealing_date: date,
        amount: Optional[Decimal] = None,
        units: Optional[Decimal] = None,
        in_good_order: bool = True,
    ) -> Instruction:
        if kind not in ("invest", "redeem"):
            raise BlockError(f"unknown instruction kind {kind!r}")
        if id in self.instructions:
            raise BlockError(f"duplicate instruction {id}")
        if dealing_date < received_at.date():
            raise BlockError("a dealing date cannot precede receipt; forward pricing. Backdating needs a reason and an owner")
        if kind == "invest":
            if amount is None or Decimal(amount) <= 0:
                raise BlockError("an investment needs a positive amount")
            amount = Decimal(amount)
        else:
            if units is None or Decimal(units) <= 0:
                raise BlockError("a redemption needs positive units")
            units = Decimal(units)
        ins = Instruction(
            id=id, account=account, class_id=class_id, fund=fund, kind=kind, received_at=received_at,
            dealing_date=dealing_date, amount=amount, units=units, in_good_order=in_good_order,
        )
        self.instructions[id] = ins
        return ins

    def match_cash(self, *, instruction_id: str, bank_line_id: str, at: datetime, actor: str) -> Journal:
        ins = self._instruction(instruction_id, kind="invest")
        line = self.bank_lines[bank_line_id]
        if ins.status != "received":
            raise BlockError(f"instruction {ins.id} is already {ins.status}")
        if line.matched:
            raise BlockError(f"bank line {line.id} is already matched")
        if line.fund != ins.fund or line.amount != ins.amount:
            raise BlockError("no exact match; the receipt stays in unallocated cash for a human")
        rule_tags = self._pack_guards("MatchCash", ins)  # e.g. a TFSA contribution limit; refused cash stays unallocated
        line.matched = True
        ins.funded_amount = line.amount
        ins.status = "matched"
        return self._journal(
            effective_date=at.date(), at=at, actor=actor, command="MatchCash",
            postings=[dr(unallocated(ins.fund), "money", ZAR, line.amount), cr(awaiting_pricing(ins.fund), "money", ZAR, line.amount)],
            evidence=[f"bankline:{line.id}", f"instruction:{ins.id}"] + rule_tags,
        )

    def fund_on_exposure(self, *, instruction_id: str, at: datetime, actor: str) -> Journal:
        """Units before cleared funds. Allowed only under a pack limit (I4)."""
        ins = self._instruction(instruction_id, kind="invest")
        if ins.status != "received":
            raise BlockError(f"instruction {ins.id} is already {ins.status}")
        if self.exposure_limit is None:
            raise ControlError("the pack sets no settlement exposure limit; units before cleared funds are not allowed (I4)")
        current = self.ledger.balance(exposure(ins.fund))
        if current + ins.amount > self.exposure_limit:
            raise ControlError(f"settlement exposure limit {self.exposure_limit} would be breached (I4)")
        rule_tags = self._pack_guards("FundOnExposure", ins)
        ins.funded_amount = ins.amount
        ins.on_exposure = True
        ins.status = "matched"
        return self._journal(
            effective_date=at.date(), at=at, actor=actor, command="FundOnExposure",
            postings=[dr(exposure(ins.fund), "money", ZAR, ins.amount), cr(awaiting_pricing(ins.fund), "money", ZAR, ins.amount)],
            evidence=[f"instruction:{ins.id}"] + rule_tags,
        )

    def clear_exposure(self, *, instruction_id: str, bank_line_id: str, at: datetime, actor: str) -> Journal:
        """The cash arrived for an exposure-funded instruction."""
        ins = self._instruction(instruction_id, kind="invest")
        line = self.bank_lines[bank_line_id]
        if not ins.on_exposure:
            raise BlockError(f"instruction {ins.id} was not funded on exposure")
        if line.matched or line.fund != ins.fund or line.amount != ins.funded_amount:
            raise BlockError("no exact match; the receipt stays in unallocated cash for a human")
        line.matched = True
        ins.on_exposure = False
        return self._journal(
            effective_date=at.date(), at=at, actor=actor, command="ClearExposure",
            postings=[dr(unallocated(ins.fund), "money", ZAR, line.amount), cr(exposure(ins.fund), "money", ZAR, line.amount)],
            evidence=[f"bankline:{line.id}", f"instruction:{ins.id}"],
        )

    # --------------------------------------------------------------- investment

    def price_investment(
        self, *, instruction_id: str, at: datetime, actor: str, initial_fee: Decimal = ZERO, fee_beneficiary: str = "adviser"
    ) -> Deal:
        ins = self._instruction(instruction_id, kind="invest")
        if ins.status != "matched":
            raise BlockError(f"instruction {ins.id} has no cash fact or exposure (I4)")
        if self.day_close.is_closed(ins.dealing_date):
            raise ControlError(
                f"{ins.dealing_date} is closed; use backdate_investment with a reason and a loss owner (I11)"
            )
        if self.issuer_of(ins.class_id) == "external":
            raise BlockError(f"{ins.class_id} is issued by another manco; deal in bulk with submit_bulk and confirm_bulk")
        kyc_tag = self._require_kyc(ins.account, "dealing")
        price = self.prices.official_at(ins.class_id, ins.dealing_date, knowledge_as_at=at)
        if price is None:
            raise BlockError(f"no official price for {ins.class_id} on {ins.dealing_date} yet (I3)")
        fee = Decimal(initial_fee)
        net = ins.funded_amount - fee
        units = to_units(net, price.cpu)
        postings = [
            dr(awaiting_pricing(ins.fund), "money", ZAR, ins.funded_amount),
            cr(payable_to_fund(ins.fund), "money", ZAR, net),
            dr(in_issue_account(ins.class_id), "units", ins.class_id, units),
            cr(holding_account(ins.account, ins.class_id), "units", ins.class_id, units),
        ]
        if fee > 0:
            postings.append(cr(fees_payable(fee_beneficiary), "money", ZAR, fee))
        journal = self._journal(
            effective_date=ins.dealing_date, at=at, actor=actor, command="PriceInvestment",
            postings=postings,
            evidence=[f"instruction:{ins.id}", price.ref, kyc_tag, f"obligation:{CISCA_FORWARD_PRICING}"],
        )
        self.register.check(ins.class_id)
        ins.status = "priced"
        return self._new_deal(
            instruction_id=ins.id, account=ins.account, class_id=ins.class_id, fund=ins.fund, kind="invest",
            units=units, investor_amount=ins.funded_amount, fund_amount=net, fee=fee, price=price,
            effective_date=ins.dealing_date, journal_id=journal.id, on_exposure=ins.on_exposure,
        )

    # ------------------------------------------------ bulk dealing and allocation

    def submit_bulk(self, *, class_id: str, dealing_date: date, at: datetime, actor: str) -> BulkInstruction:
        """Aggregate matched investments in an external instrument for one dealing day."""
        if self.issuer_of(class_id) != "external":
            raise BlockError(f"{class_id} is issued by this tenant; it deals at its own pricing point")
        if self.day_close.is_closed(dealing_date):
            raise ControlError(f"{dealing_date} is closed (I11)")
        included: list[Instruction] = []
        excluded: list[tuple[str, str]] = []
        for ins in self.instructions.values():
            if ins.class_id != class_id or ins.dealing_date != dealing_date or ins.kind != "invest" or ins.status != "matched":
                continue
            try:
                self._require_kyc(ins.account, "dealing")
            except ControlError as exc:  # the account stays out of the bulk and stays unpriced; day close sees it
                excluded.append((ins.id, str(exc)))
                continue
            included.append(ins)
        if not included:
            raise BlockError(f"nothing to submit for {class_id} on {dealing_date}")
        bulk = BulkInstruction(
            id=self._next_id("B"), class_id=class_id, fund=included[0].fund, dealing_date=dealing_date,
            instruction_ids=tuple(i.id for i in included), amount=sum((i.funded_amount for i in included), ZERO),
            excluded=tuple(excluded),
        )
        for ins in included:
            ins.status = "in_bulk"
        self.bulks[bulk.id] = bulk
        return bulk

    def confirm_bulk(
        self, *, bulk_id: str, cpu: Decimal, units_confirmed: Decimal, confirmation_ref: str, at: datetime, actor: str
    ) -> tuple[Price, list[Deal]]:
        """The issuing manco confirms price and units. The price becomes a fact. Investors are allocated."""
        bulk = self.bulks[bulk_id]
        if bulk.status != "submitted":
            raise BlockError(f"bulk {bulk.id} is already {bulk.status}")
        if not confirmation_ref:
            raise ControlError("a confirmation reference is the second pair of eyes on an external price")
        cpu = Decimal(cpu)
        units_confirmed = Decimal(units_confirmed)
        existing = self.prices.official_at(bulk.class_id, bulk.dealing_date, knowledge_as_at=at)
        if existing is None:
            price = self.publish_price(
                class_id=bulk.class_id, pricing_date=bulk.dealing_date, cpu=cpu, at=at,
                signed_by=(actor, f"confirmation:{confirmation_ref}"),
            )
        elif existing.cpu != cpu:
            raise BlockError(
                f"confirmation price {cpu} differs from the published {existing.cpu} for {bulk.class_id} on "
                f"{bulk.dealing_date}; prices are never overwritten, raise a correction (I10)"
            )
        else:
            price = existing
        instructions = [self.instructions[i] for i in bulk.instruction_ids]
        allocations = [(ins, to_units(ins.funded_amount, price.cpu)) for ins in instructions]
        allocated = sum((u for _, u in allocations), ZERO)
        diff = units_confirmed - allocated
        if abs(diff) >= Decimal("1"):
            raise ControlError(
                f"allocation break on {bulk.class_id}: the manco confirmed {units_confirmed} units, allocation gives "
                f"{allocated}; nothing posts until a human resolves it (C6)"
            )
        postings = [
            dr(awaiting_pricing(bulk.fund), "money", ZAR, bulk.amount),
            cr(payable_to_fund(bulk.fund), "money", ZAR, bulk.amount),
            dr(nominee_bulk_account(bulk.class_id), "units", bulk.class_id, units_confirmed),
        ]
        for ins, units in allocations:
            postings.append(cr(holding_account(ins.account, bulk.class_id), "units", bulk.class_id, units))
        if diff > 0:
            postings.append(cr(rounding_units_account(bulk.class_id), "units", bulk.class_id, diff))
        elif diff < 0:
            postings.append(dr(rounding_units_account(bulk.class_id), "units", bulk.class_id, -diff))
        journal = self._journal(
            effective_date=bulk.dealing_date, at=at, actor=actor, command="ConfirmBulk",
            postings=postings,
            evidence=[f"bulk:{bulk.id}", f"confirmation:{confirmation_ref}", price.ref, f"obligation:{FICA_CDD}",
                      f"obligation:{CISCA_FORWARD_PRICING}"],
        )
        self.register.check(bulk.class_id)
        bulk.status = "allocated"
        bulk.confirmation_ref = confirmation_ref
        bulk.journal_id = journal.id
        deals: list[Deal] = []
        for ins, units in allocations:
            ins.status = "priced"
            deals.append(self._new_deal(
                instruction_id=ins.id, account=ins.account, class_id=ins.class_id, fund=ins.fund, kind="invest",
                units=units, investor_amount=ins.funded_amount, fund_amount=ins.funded_amount, fee=ZERO, price=price,
                effective_date=bulk.dealing_date, journal_id=journal.id,
            ))
        return price, deals

    # --------------------------------------------------------------- redemption

    def lock_units(self, *, instruction_id: str, at: datetime, actor: str) -> Journal:
        ins = self._instruction(instruction_id, kind="redeem")
        if ins.status != "received":
            raise BlockError(f"instruction {ins.id} is already {ins.status}")
        available = self.register.available_units(ins.account, ins.class_id)
        if ins.units > available:
            raise BlockError(f"only {available} units available, {ins.units} requested")
        rule_tags = self._pack_guards("LockUnits", ins)  # e.g. retirement restrictions, two-pot rules
        ins.status = "locked"
        return self._journal(
            effective_date=at.date(), at=at, actor=actor, command="LockUnits",
            postings=[
                dr(holding_account(ins.account, ins.class_id), "units", ins.class_id, ins.units),
                cr(locked_account(ins.account, ins.class_id), "units", ins.class_id, ins.units),
            ],
            evidence=[f"instruction:{ins.id}"] + rule_tags,
        )

    def price_redemption(
        self, *, instruction_id: str, at: datetime, actor: str, tax_withheld: Decimal = ZERO, holds: Iterable[str] = ()
    ) -> tuple[Deal, Payable]:
        """Cancel units at the pricing point and create the payable. `holds` name what must clear before payment."""
        ins = self._instruction(instruction_id, kind="redeem")
        if ins.status != "locked":
            raise BlockError(f"instruction {ins.id} must be locked first")
        if self.day_close.is_closed(ins.dealing_date):
            raise ControlError(
                f"{ins.dealing_date} is closed; use backdate_redemption with a reason and a loss owner (I11)"
            )
        price = self.prices.official_at(ins.class_id, ins.dealing_date, knowledge_as_at=at)
        if price is None:
            raise BlockError(f"no official price for {ins.class_id} on {ins.dealing_date} yet (I3)")
        gross = cpu_to_amount(ins.units, price.cpu)
        tax = Decimal(tax_withheld)
        net = gross - tax
        postings = [
            dr(due_from_fund(ins.fund), "money", ZAR, gross),
            cr(redemptions_payable(ins.fund), "money", ZAR, net),
            dr(locked_account(ins.account, ins.class_id), "units", ins.class_id, ins.units),
            cr(in_issue_account(ins.class_id), "units", ins.class_id, ins.units),
        ]
        if tax > 0:
            postings.append(cr(TAX_WITHHELD, "money", ZAR, tax))
        journal = self._journal(
            effective_date=ins.dealing_date, at=at, actor=actor, command="PriceRedemption",
            postings=postings, evidence=[f"instruction:{ins.id}", price.ref],
        )
        self.register.check(ins.class_id)
        ins.status = "priced"
        deal = self._new_deal(
            instruction_id=ins.id, account=ins.account, class_id=ins.class_id, fund=ins.fund, kind="redeem",
            units=ins.units, investor_amount=gross, fund_amount=gross, fee=ZERO, price=price,
            effective_date=ins.dealing_date, journal_id=journal.id,
        )
        payable = Payable(id=self._next_id("P"), fund=ins.fund, account=ins.account, amount=net, deal_id=deal.id,
                          ledger_account=redemptions_payable(ins.fund), holds=set(holds))
        self.payables[payable.id] = payable
        return deal, payable

    def release_hold(
        self, *, payable_id: str, hold: str, reference: str, at: datetime, actor: str,
        tax_withheld: Decimal = ZERO, obligation: Optional[str] = None,
    ) -> Optional[Journal]:
        """Clear a hold on a payable. A tax directive release posts the withholding it prescribes."""
        payable = self.payables[payable_id]
        if hold not in payable.holds:
            raise BlockError(f"payable {payable.id} has no hold {hold!r}")
        if not reference:
            raise ControlError(f"releasing the {hold} hold needs a reference, for example the SARS directive number")
        tax = Decimal(tax_withheld)
        if tax < 0 or tax > payable.amount:
            raise BlockError("withholding must be between zero and the payable amount")
        journal = None
        if tax > 0:
            payable.amount -= tax
            journal = self._journal(
                effective_date=at.date(), at=at, actor=actor, command="ReleaseHold", reason=f"{hold}:{reference}",
                postings=[dr(payable.ledger_account, "money", ZAR, tax), cr(TAX_WITHHELD, "money", ZAR, tax)],
                evidence=[f"payable:{payable.id}", f"{hold}:{reference}"] + ([f"obligation:{obligation}"] if obligation else []),
            )
        payable.holds.discard(hold)
        return journal

    def fund_settles_redemption(self, *, deal_id: str, bank_account: str, at: datetime, actor: str) -> Journal:
        deal = self.deals[deal_id]
        if deal.kind != "redeem":
            raise BlockError("only redemptions are settled by the fund")
        return self._journal(
            effective_date=at.date(), at=at, actor=actor, command="FundSettlesRedemption",
            postings=[dr(bank(bank_account), "money", ZAR, deal.fund_amount), cr(due_from_fund(deal.fund), "money", ZAR, deal.fund_amount)],
            evidence=[f"deal:{deal.id}"],
        )

    # ----------------------------------------------------------------- payments

    def instruct_payment(self, *, payable_id: str, maker: str, approvals: Iterable[Approval], at: datetime) -> Journal:
        """No payment without an open payable (I8). Maker is never the checker (I9)."""
        try:
            payable = self.payables[payable_id]
        except KeyError:
            raise BlockError(f"no payable {payable_id} (I8)") from None
        if payable.status != "open":
            raise BlockError(f"payable {payable.id} is {payable.status}, not open (I8)")
        if payable.holds:
            raise ControlError(f"payable {payable.id} is held: {sorted(payable.holds)}; release the hold first")
        approvals = require_approvals(maker, approvals, minimum=1)
        if payable.kind == "fee":
            gate_tag = self._require_adviser_licensed(payable.account)
        else:
            gate_tag = self._require_kyc(payable.account, "payment")
        rule_tags = self._pack_guards("InstructPayment", payable)
        payable.status = "in_transit"
        return self._journal(
            effective_date=at.date(), at=at, actor=maker, command="InstructPayment",
            postings=[dr(payable.ledger_account, "money", ZAR, payable.amount), cr(in_transit(payable.fund), "money", ZAR, payable.amount)],
            evidence=[f"payable:{payable.id}", gate_tag] + rule_tags + [f"approval:{a.role}:{a.actor}" for a in approvals],
        )

    def confirm_payment(self, *, payable_id: str, bank_account: str, at: datetime, actor: str) -> Journal:
        payable = self.payables[payable_id]
        if payable.status != "in_transit":
            raise BlockError(f"payable {payable.id} is {payable.status}, not in transit")
        payable.status = "paid"
        return self._journal(
            effective_date=at.date(), at=at, actor=actor, command="ConfirmPayment",
            postings=[dr(in_transit(payable.fund), "money", ZAR, payable.amount), cr(bank(bank_account), "money", ZAR, payable.amount)],
            evidence=[f"payable:{payable.id}"],
        )

    def return_payment(self, *, payable_id: str, at: datetime, actor: str, reason: str) -> Journal:
        """A returned payment goes back to the payable. It never vanishes."""
        payable = self.payables[payable_id]
        if payable.status != "in_transit":
            raise BlockError(f"payable {payable.id} is {payable.status}, not in transit")
        payable.status = "open"
        return self._journal(
            effective_date=at.date(), at=at, actor=actor, command="ReturnPayment", reason=reason,
            postings=[dr(in_transit(payable.fund), "money", ZAR, payable.amount), cr(payable.ledger_account, "money", ZAR, payable.amount)],
            evidence=[f"payable:{payable.id}"],
        )

    # ------------------------------------------------------------------- switch

    def receive_switch(
        self, *, id: str, account: str, from_class: str, to_class: str, from_fund: str, to_fund: str,
        units: Decimal, received_at: datetime, dealing_date: date,
    ) -> SwitchInstruction:
        if id in self.switches:
            raise BlockError(f"duplicate switch {id}")
        if dealing_date < received_at.date():
            raise BlockError("a dealing date cannot precede receipt; forward pricing")
        if from_class == to_class:
            raise BlockError("a switch needs two different classes")
        sw = SwitchInstruction(id, account, from_class, to_class, from_fund, to_fund, Decimal(units), received_at, dealing_date)
        self.switches[id] = sw
        return sw

    def price_switch(self, *, instruction_id: str, at: datetime, actor: str) -> tuple[Deal, Deal]:
        """A redemption leg and an investment leg in one journal. Both legs or neither."""
        sw = self.switches[instruction_id]
        if sw.status != "received":
            raise BlockError(f"switch {sw.id} is already {sw.status}")
        if self.issuer_of(sw.from_class) == "external" or self.issuer_of(sw.to_class) == "external":
            raise BlockError("a leg on an external instrument goes through bulk dealing")
        if self.day_close.is_closed(sw.dealing_date):
            raise ControlError(f"{sw.dealing_date} is closed (I11)")
        available = self.register.available_units(sw.account, sw.from_class)
        if sw.units > available:
            raise BlockError(f"only {available} units available, {sw.units} requested")
        kyc_tag = self._require_kyc(sw.account, "dealing")
        rule_tags = self._pack_guards("Switch", sw)
        price_out = self.prices.official_at(sw.from_class, sw.dealing_date, knowledge_as_at=at)
        price_in = self.prices.official_at(sw.to_class, sw.dealing_date, knowledge_as_at=at)
        if price_out is None or price_in is None:
            raise BlockError("both legs need an official price for the dealing date; nothing posts until they exist (I3)")
        amount = cpu_to_amount(sw.units, price_out.cpu)
        units_in = to_units(amount, price_in.cpu)
        journal = self._journal(
            effective_date=sw.dealing_date, at=at, actor=actor, command="PriceSwitch",
            postings=[
                dr(holding_account(sw.account, sw.from_class), "units", sw.from_class, sw.units),
                cr(in_issue_account(sw.from_class), "units", sw.from_class, sw.units),
                dr(in_issue_account(sw.to_class), "units", sw.to_class, units_in),
                cr(holding_account(sw.account, sw.to_class), "units", sw.to_class, units_in),
                dr(due_from_fund(sw.from_fund), "money", ZAR, amount),
                cr(SWITCH_CLEARING, "money", ZAR, amount),
                dr(SWITCH_CLEARING, "money", ZAR, amount),
                cr(payable_to_fund(sw.to_fund), "money", ZAR, amount),
            ],
            evidence=[f"switch:{sw.id}", price_out.ref, price_in.ref, kyc_tag, f"obligation:{CISCA_FORWARD_PRICING}"] + rule_tags,
        )
        self.register.check(sw.from_class)
        self.register.check(sw.to_class)
        sw.status = "priced"
        out = self._new_deal(
            instruction_id=sw.id, account=sw.account, class_id=sw.from_class, fund=sw.from_fund, kind="switch_out",
            units=sw.units, investor_amount=amount, fund_amount=amount, fee=ZERO, price=price_out,
            effective_date=sw.dealing_date, journal_id=journal.id,
        )
        into = self._new_deal(
            instruction_id=sw.id, account=sw.account, class_id=sw.to_class, fund=sw.to_fund, kind="switch_in",
            units=units_in, investor_amount=amount, fund_amount=amount, fee=ZERO, price=price_in,
            effective_date=sw.dealing_date, journal_id=journal.id,
        )
        return out, into

    # ----------------------------------------------------------------- transfer

    def transfer_units(
        self, *, from_account: str, to_account: str, class_id: str, units: Decimal, at: datetime, actor: str,
        reason: str, evidence: Iterable[str] = (),
    ) -> Journal:
        """Units move between accounts without a price and without money. Tax lots travel with them."""
        units = Decimal(units)
        if units <= 0:
            raise BlockError("a transfer needs positive units")
        if not reason:
            raise BlockError("a transfer needs a reason: estate, re-registration, section 14, retirement")
        available = self.register.available_units(from_account, class_id)
        if units > available:
            raise BlockError(f"only {available} units available, {units} requested")
        kyc_tag = self._require_kyc(to_account, "receiving a transfer")
        request = TransferRequest(from_account, to_account, class_id, units, reason)
        rule_tags = self._pack_guards("Transfer", request)
        journal = self._journal(
            effective_date=at.date(), at=at, actor=actor, command="TransferUnits", reason=reason,
            postings=[
                dr(holding_account(from_account, class_id), "units", class_id, units),
                cr(holding_account(to_account, class_id), "units", class_id, units),
            ],
            evidence=list(evidence) + [kyc_tag] + rule_tags,
        )
        self.register.check(class_id)
        return journal

    # ------------------------------------------------------------- distribution

    def declare_distribution(
        self, *, class_id: str, fund: str, cpu: Decimal, record_date: date, pay_date: date, at: datetime,
        signed_by: Iterable[str], tax_rate: Decimal = ZERO,
    ) -> Distribution:
        """Cents per unit for a class. Two signers, like a price."""
        signed_by = tuple(signed_by)
        if len(set(signed_by)) < 2:
            raise ControlError("a distribution declaration needs two distinct signers")
        cpu = Decimal(cpu)
        if cpu <= 0:
            raise BlockError("cents per unit must be positive")
        if pay_date < record_date:
            raise BlockError("the pay date cannot precede the record date")
        dist = Distribution(self._next_id("DIST"), class_id, fund, cpu, record_date, pay_date, Decimal(tax_rate), signed_by)
        self.distributions[dist.id] = dist
        return dist

    def allocate_distribution(
        self, *, distribution_id: str, at: datetime, actor: str,
        option_for: Callable[[str], str] = lambda account: "reinvest",
        exempt: Callable[[str], bool] = lambda account: False,
    ) -> Journal:
        """Entitlements from record-date holdings, derived as at that date. Rounding to its own account."""
        dist = self.distributions[distribution_id]
        if dist.status != "declared":
            raise BlockError(f"distribution {dist.id} is already {dist.status}")
        holders = self.register.holders(dist.class_id, effective_as_at=dist.record_date, knowledge_as_at=at)
        if not holders:
            raise BlockError(f"no holders of {dist.class_id} at {dist.record_date}")
        in_issue = self.register.control_total(dist.class_id, effective_as_at=dist.record_date, knowledge_as_at=at)
        dist.declared_total = cpu_to_amount(in_issue, dist.cpu)
        total_gross = total_tax = total_net = ZERO
        for account, units in sorted(holders.items()):
            gross = cpu_to_amount(units, dist.cpu)
            tax = ZERO if exempt(account) else (gross * dist.tax_rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            net = gross - tax
            option = option_for(account)
            if option not in ("reinvest", "payout"):
                raise BlockError(f"unknown distribution option {option!r} for {account}")
            dist.entitlements[account] = Entitlement(account, units, gross, tax, net, option)
            total_gross += gross
            total_tax += tax
            total_net += net
        dist.rounding = dist.declared_total - total_gross
        postings = [
            dr(distributions_due_from_fund(dist.fund), "money", ZAR, dist.declared_total),
            cr(distributions_payable(dist.fund), "money", ZAR, total_net),
        ]
        if total_tax > 0:
            postings.append(cr(TAX_WITHHELD, "money", ZAR, total_tax))
        if dist.rounding > 0:
            postings.append(cr(ROUNDING, "money", ZAR, dist.rounding))
        elif dist.rounding < 0:
            postings.append(dr(ROUNDING, "money", ZAR, -dist.rounding))
        journal = self._journal(
            effective_date=dist.record_date, at=at, actor=actor, command="AllocateDistribution",
            postings=postings, evidence=[f"distribution:{dist.id}"] + [f"signer:{s}" for s in dist.signed_by],
        )
        dist.status = "allocated"
        dist.journal_id = journal.id
        return journal

    def settle_distribution(self, *, distribution_id: str, at: datetime, actor: str) -> tuple[list[Deal], list[Payable]]:
        """Reinvest at the pay-date price, or create payables. One journal for every reinvestment."""
        dist = self.distributions[distribution_id]
        if dist.status != "allocated":
            raise BlockError(f"distribution {dist.id} must be allocated first")
        reinvesting = [e for e in dist.entitlements.values() if e.option == "reinvest" and e.net > 0]
        paying = [e for e in dist.entitlements.values() if e.option == "payout" and e.net > 0]
        deals: list[Deal] = []
        payables: list[Payable] = []
        if reinvesting:
            price = self.prices.official_at(dist.class_id, dist.pay_date, knowledge_as_at=at)
            if price is None:
                raise BlockError(f"no official price for {dist.class_id} on the pay date {dist.pay_date} (I3)")
            postings = []
            allocations = []
            for e in reinvesting:
                units = to_units(e.net, price.cpu)
                allocations.append((e, units))
                postings += [
                    dr(distributions_payable(dist.fund), "money", ZAR, e.net),
                    cr(payable_to_fund(dist.fund), "money", ZAR, e.net),
                    dr(in_issue_account(dist.class_id), "units", dist.class_id, units),
                    cr(holding_account(e.account, dist.class_id), "units", dist.class_id, units),
                ]
            journal = self._journal(
                effective_date=dist.pay_date, at=at, actor=actor, command="ReinvestDistribution",
                postings=postings, evidence=[f"distribution:{dist.id}", price.ref],
            )
            self.register.check(dist.class_id)
            for e, units in allocations:
                deals.append(self._new_deal(
                    instruction_id=dist.id, account=e.account, class_id=dist.class_id, fund=dist.fund, kind="reinvest",
                    units=units, investor_amount=e.net, fund_amount=e.net, fee=ZERO, price=price,
                    effective_date=dist.pay_date, journal_id=journal.id,
                ))
        for e in paying:
            payable = Payable(id=self._next_id("P"), fund=dist.fund, account=e.account, amount=e.net, deal_id=dist.id,
                              ledger_account=distributions_payable(dist.fund), kind="distribution")
            self.payables[payable.id] = payable
            payables.append(payable)
        dist.status = "settled"
        return deals, payables

    # --------------------------------------------------------------------- fees

    def accrue_fee(
        self, *, account: str, class_id: str, rate_pa: Decimal, start: date, end: date, knowledge_as_at: Optional[datetime] = None,
    ) -> Decimal:
        """A fee to date, computed from daily units and the last known price. Never stored until collected."""
        total = ZERO
        day = start
        while day <= end:
            units = self.register.units(account, class_id, effective_as_at=day, knowledge_as_at=knowledge_as_at)
            price = self.prices.select(class_id, effective_as_at=day, knowledge_as_at=knowledge_as_at)
            if price is not None and units > 0:
                total += units * price.cpu / Decimal(100) * Decimal(rate_pa) / Decimal(365)
            day += timedelta(days=1)
        return total.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    def collect_fee(
        self, *, account: str, class_id: str, fund: str, amount: Decimal, beneficiary: str, dealing_date: date,
        at: datetime, actor: str, period: str,
    ) -> tuple[Deal, Payable]:
        """Execute a fee claim as a unit cancellation. The beneficiary gets a payable, paid through the FAIS gate."""
        amount = Decimal(amount)
        if amount <= 0:
            raise BlockError("a fee claim must be positive")
        if self.day_close.is_closed(dealing_date):
            raise ControlError(f"{dealing_date} is closed (I11)")
        price = self.prices.official_at(class_id, dealing_date, knowledge_as_at=at)
        if price is None:
            raise BlockError(f"no official price for {class_id} on {dealing_date} (I3)")
        units = to_units(amount, price.cpu)
        available = self.register.available_units(account, class_id)
        if units > available:
            raise BlockError(f"only {available} units available for a fee of {units}")
        rule_tags = self._pack_guards("CollectFee", (account, class_id, amount, beneficiary))
        journal = self._journal(
            effective_date=dealing_date, at=at, actor=actor, command="CollectFee", reason=period,
            postings=[
                dr(holding_account(account, class_id), "units", class_id, units),
                cr(in_issue_account(class_id), "units", class_id, units),
                dr(fees_due_from_fund(fund), "money", ZAR, amount),
                cr(fees_payable(beneficiary), "money", ZAR, amount),
            ],
            evidence=[f"fee:{beneficiary}:{period}", price.ref] + rule_tags,
        )
        self.register.check(class_id)
        deal = self._new_deal(
            instruction_id=f"fee:{beneficiary}:{period}", account=account, class_id=class_id, fund=fund, kind="fee",
            units=units, investor_amount=amount, fund_amount=amount, fee=amount, price=price,
            effective_date=dealing_date, journal_id=journal.id,
        )
        payable = Payable(id=self._next_id("P"), fund=fund, account=beneficiary, amount=amount, deal_id=deal.id,
                          ledger_account=fees_payable(beneficiary), kind="fee")
        self.payables[payable.id] = payable
        return deal, payable

    # --------------------------------------------------------------- backdating

    def _backdating_checks(
        self, ins: Instruction, historical_date: date, reason: str, evidence: tuple[str, ...], maker: str,
        approvals: Iterable[Approval], at: datetime,
    ) -> tuple[str, tuple[Approval, ...], Price, Price]:
        if historical_date >= ins.dealing_date:
            raise BlockError("not a backdating: the historical date must precede the instruction's dealing date")
        if (at.date() - historical_date).days > self.loss_policy.max_age_days:
            raise ControlError(f"backdating older than {self.loss_policy.max_age_days} days is refused")
        if not evidence:
            raise ControlError("backdating needs evidence of the original receipt")
        owner = self.loss_policy.owner_for(reason)
        minimum = max(2, self.loss_policy.approvals_required)  # kernel minimum is 2; a pack may only raise it
        approvals = require_approvals(maker, approvals, minimum=minimum)
        historical = self.prices.official_at(ins.class_id, historical_date, knowledge_as_at=at)
        if historical is None:
            raise BlockError(f"no official price for {ins.class_id} on {historical_date}")
        current = self._current_price(ins.class_id, at)
        return owner, approvals, historical, current

    def backdate_investment(
        self,
        *,
        instruction_id: str,
        historical_date: date,
        reason: str,
        evidence: Iterable[str],
        maker: str,
        approvals: Iterable[Approval],
        at: datetime,
        initial_fee: Decimal = ZERO,
        fee_beneficiary: str = "adviser",
    ) -> tuple[Deal, BackdatingRecord]:
        """Investor dealt at the historical price. Fund receives value at the current price. Owner pays the delta."""
        ins = self._instruction(instruction_id, kind="invest")
        if ins.status != "matched":
            raise BlockError(f"instruction {ins.id} has no cash fact or exposure (I4)")
        evidence = tuple(evidence)
        owner, approvals, historical, current = self._backdating_checks(ins, historical_date, reason, evidence, maker, approvals, at)
        fee = Decimal(initial_fee)
        net = ins.funded_amount - fee
        units = to_units(net, historical.cpu)
        fund_amount = cpu_to_amount(units, current.cpu)
        delta = fund_amount - net
        postings = [
            dr(awaiting_pricing(ins.fund), "money", ZAR, ins.funded_amount),
            cr(payable_to_fund(ins.fund), "money", ZAR, fund_amount),
            dr(in_issue_account(ins.class_id), "units", ins.class_id, units),
            cr(holding_account(ins.account, ins.class_id), "units", ins.class_id, units),
        ]
        if fee > 0:
            postings.append(cr(fees_payable(fee_beneficiary), "money", ZAR, fee))
        if delta > 0:
            postings.append(dr(owner, "money", ZAR, delta))
        elif delta < 0:
            postings.append(cr(owner, "money", ZAR, -delta))
        journal = self._journal(
            effective_date=historical_date, at=at, actor=maker, command="BackdateInvestment", reason=reason,
            postings=postings, evidence=list(evidence) + [f"instruction:{ins.id}", historical.ref, current.ref],
        )
        self.register.check(ins.class_id)
        ins.status = "priced"
        deal = self._new_deal(
            instruction_id=ins.id, account=ins.account, class_id=ins.class_id, fund=ins.fund, kind="invest",
            units=units, investor_amount=ins.funded_amount, fund_amount=fund_amount, fee=fee, price=historical,
            effective_date=historical_date, journal_id=journal.id, on_exposure=ins.on_exposure,
        )
        record = BackdatingRecord(deal.id, "invest", reason, owner, delta, historical, current, tuple(a.actor for a in approvals), evidence)
        self.backdating_register.append(record)
        return deal, record

    def backdate_redemption(
        self,
        *,
        instruction_id: str,
        historical_date: date,
        reason: str,
        evidence: Iterable[str],
        maker: str,
        approvals: Iterable[Approval],
        at: datetime,
        tax_withheld: Decimal = ZERO,
    ) -> tuple[Deal, Payable, BackdatingRecord]:
        """Investor paid at the historical price. Fund pays at the current price. Owner takes the delta."""
        ins = self._instruction(instruction_id, kind="redeem")
        if ins.status != "locked":
            raise BlockError(f"instruction {ins.id} must be locked first")
        evidence = tuple(evidence)
        owner, approvals, historical, current = self._backdating_checks(ins, historical_date, reason, evidence, maker, approvals, at)
        investor_gross = cpu_to_amount(ins.units, historical.cpu)
        fund_amount = cpu_to_amount(ins.units, current.cpu)
        delta = investor_gross - fund_amount
        tax = Decimal(tax_withheld)
        net = investor_gross - tax
        postings = [
            dr(due_from_fund(ins.fund), "money", ZAR, fund_amount),
            cr(redemptions_payable(ins.fund), "money", ZAR, net),
            dr(locked_account(ins.account, ins.class_id), "units", ins.class_id, ins.units),
            cr(in_issue_account(ins.class_id), "units", ins.class_id, ins.units),
        ]
        if tax > 0:
            postings.append(cr(TAX_WITHHELD, "money", ZAR, tax))
        if delta > 0:
            postings.append(dr(owner, "money", ZAR, delta))
        elif delta < 0:
            postings.append(cr(owner, "money", ZAR, -delta))
        journal = self._journal(
            effective_date=historical_date, at=at, actor=maker, command="BackdateRedemption", reason=reason,
            postings=postings, evidence=list(evidence) + [f"instruction:{ins.id}", historical.ref, current.ref],
        )
        self.register.check(ins.class_id)
        ins.status = "priced"
        deal = self._new_deal(
            instruction_id=ins.id, account=ins.account, class_id=ins.class_id, fund=ins.fund, kind="redeem",
            units=ins.units, investor_amount=investor_gross, fund_amount=fund_amount, fee=ZERO, price=historical,
            effective_date=historical_date, journal_id=journal.id,
        )
        payable = Payable(id=self._next_id("P"), fund=ins.fund, account=ins.account, amount=net, deal_id=deal.id,
                          ledger_account=redemptions_payable(ins.fund))
        self.payables[payable.id] = payable
        record = BackdatingRecord(deal.id, "redeem", reason, owner, delta, historical, current, tuple(a.actor for a in approvals), evidence)
        self.backdating_register.append(record)
        return deal, payable, record

    def reverse_unpaid_collection(self, *, deal_id: str, reason: str, at: datetime, actor: str) -> BackdatingRecord:
        """Units were issued on exposure and the money never came. Cancel at the current price. Owner takes the delta."""
        deal = self.deals[deal_id]
        if deal.kind != "invest" or not deal.on_exposure or deal.reversed:
            raise BlockError("only an open exposure-funded investment can be reversed this way")
        ins = self.instructions[deal.instruction_id]
        if not ins.on_exposure:
            raise BlockError("the exposure was already cleared by a receipt; this is not an unpaid collection")
        available = self.register.available_units(deal.account, deal.class_id)
        if available < deal.units:
            raise BlockError("the investor no longer holds the units; a human must decide")
        owner = self.loss_policy.owner_for(reason)
        current = self._current_price(deal.class_id, at)
        returned = cpu_to_amount(deal.units, current.cpu)
        delta = returned - deal.fund_amount  # negative: the fund got less back than it was owed; the owner pays
        postings = [
            dr(payable_to_fund(deal.fund), "money", ZAR, returned),
            cr(exposure(deal.fund), "money", ZAR, deal.investor_amount),
            dr(holding_account(deal.account, deal.class_id), "units", deal.class_id, deal.units),
            cr(in_issue_account(deal.class_id), "units", deal.class_id, deal.units),
        ]
        if deal.fee > 0:
            postings.append(dr(fees_payable("adviser"), "money", ZAR, deal.fee))
        if delta > 0:
            postings.append(cr(owner, "money", ZAR, delta))
        elif delta < 0:
            postings.append(dr(owner, "money", ZAR, -delta))
        self._journal(
            effective_date=at.date(), at=at, actor=actor, command="ReverseUnpaidCollection", reason=reason,
            postings=postings, evidence=[f"deal:{deal.id}", current.ref],
        )
        self.register.check(deal.class_id)
        deal.reversed = True
        ins.on_exposure = False
        record = BackdatingRecord(deal.id, "reversal", reason, owner, -delta, deal.price, current, (), (f"deal:{deal.id}",))
        self.backdating_register.append(record)
        return record

    # --------------------------------------------------------- price correction

    def correct_price(
        self,
        *,
        class_id: str,
        pricing_date: date,
        new_cpu: Decimal,
        signed_by: Iterable[str],
        at: datetime,
        actor: str,
        materiality: Decimal = Decimal("0.005"),
    ) -> CorrectionRecord:
        """A new price version. Affected deals are repriced from the manco's error account when material."""
        old = self.prices.official_at(class_id, pricing_date, knowledge_as_at=at)
        if old is None:
            raise BlockError(f"no official price to correct for {class_id} on {pricing_date}")
        new = self.publish_price(
            class_id=class_id, pricing_date=pricing_date, cpu=Decimal(new_cpu), at=at, signed_by=signed_by,
            override_reason="price correction",
        )
        error_ratio = abs(new.cpu - old.cpu) / new.cpu
        material = error_ratio >= materiality
        adjustments: list[tuple[str, str, Decimal]] = []
        if material:
            affected = [
                d for d in self.deals.values()
                if d.class_id == class_id and d.effective_date == pricing_date and d.price.version == old.version and not d.reversed
            ]
            for deal in affected:
                if deal.kind == "invest":
                    correct_units = to_units(deal.investor_amount - deal.fee, new.cpu)
                    diff = deal.units - correct_units  # positive: too many units were issued
                    if diff > 0:
                        postings = [
                            dr(holding_account(deal.account, class_id), "units", class_id, diff),
                            cr(in_issue_account(class_id), "units", class_id, diff),
                        ]
                    elif diff < 0:
                        postings = [
                            dr(in_issue_account(class_id), "units", class_id, -diff),
                            cr(holding_account(deal.account, class_id), "units", class_id, -diff),
                        ]
                    else:
                        continue
                    adjustments.append((deal.id, "units", diff))
                else:
                    correct_amount = cpu_to_amount(deal.units, new.cpu)
                    diff = correct_amount - deal.investor_amount  # positive: the investor was underpaid
                    if diff > 0:
                        postings = [dr(MANCO_ERROR, "money", ZAR, diff), cr(redemptions_payable(deal.fund), "money", ZAR, diff)]
                        payable = Payable(id=self._next_id("P"), fund=deal.fund, account=deal.account, amount=diff, deal_id=deal.id,
                                          ledger_account=redemptions_payable(deal.fund))
                        self.payables[payable.id] = payable
                    elif diff < 0:
                        postings = [dr(MANCO_ERROR, "money", ZAR, -diff), cr(payable_to_fund(deal.fund), "money", ZAR, -diff)]
                    else:
                        continue
                    adjustments.append((deal.id, "money", diff))
                self._journal(
                    effective_date=at.date(), at=at, actor=actor, command="CorrectDeal",
                    reason=f"price correction {old.ref} -> {new.ref}", postings=postings, evidence=[f"deal:{deal.id}", new.ref],
                )
            self.register.check(class_id)
        record = CorrectionRecord(class_id, pricing_date, old.cpu, new.cpu, error_ratio, material, tuple(adjustments))
        self.corrections.append(record)
        return record

    # ---------------------------------------------------------------- day close

    def close_day(self, dealing_date: date, *, actor: str, at: datetime) -> dict:
        """Gates from docs/04. Passing them locks the date. There is no reopen."""
        problems: list[str] = []
        for ins in self.instructions.values():
            if ins.dealing_date == dealing_date and ins.status in ("matched", "locked", "in_bulk"):
                problems.append(f"instruction {ins.id} is unpriced")
        for sw in self.switches.values():
            if sw.dealing_date == dealing_date and sw.status == "received":
                problems.append(f"switch {sw.id} is unpriced")
        for line in self.bank_lines.values():
            if not line.matched and line.at.date() <= dealing_date:
                problems.append(f"bank line {line.id} is unallocated cash")
        for class_id in {ins.class_id for ins in self.instructions.values()}:
            try:
                self.register.check(class_id)
            except Exception as exc:  # noqa: BLE001 - reported as a gate failure
                problems.append(str(exc))
        if problems:
            raise ControlError(f"day close for {dealing_date} blocked: " + "; ".join(problems))
        self.day_close.close(dealing_date)
        return {"dealing_date": dealing_date, "closed_by": actor, "closed_at": at}

    # ------------------------------------------------------------------ queries

    def statement(
        self, account: str, class_ids: Iterable[str], *, effective_as_at: date, knowledge_as_at: Optional[datetime] = None,
        policy: str = "official-latest",
    ) -> AccountValuation:
        return value_account(
            self.register, self.prices, account, class_ids,
            effective_as_at=effective_as_at, knowledge_as_at=knowledge_as_at, policy=policy,
        )
