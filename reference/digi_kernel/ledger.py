"""Bitemporal, two-dimensional, double-entry ledger.

Invariants: I1 (balanced in money and units), I5 (immutable, reversal only),
I12 (actor and pack version on every journal).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Iterator, Optional

ZERO = Decimal("0")


class LedgerError(Exception):
    """Raised when a journal would break a ledger invariant."""


@dataclass(frozen=True)
class Posting:
    """One line of a journal. Debit is positive, credit is negative."""

    account: str
    dimension: str  # "money" or "units"
    unit: str  # currency code for money, class id for units
    amount: Decimal

    def __post_init__(self) -> None:
        if self.dimension not in ("money", "units"):
            raise LedgerError(f"unknown dimension {self.dimension!r}")
        if not isinstance(self.amount, Decimal):
            raise LedgerError("amounts must be Decimal, never float")
        if self.amount == ZERO:
            raise LedgerError("zero postings are not allowed")


def dr(account: str, dimension: str, unit: str, amount: Decimal) -> Posting:
    """A debit posting."""
    return Posting(account, dimension, unit, abs(amount))


def cr(account: str, dimension: str, unit: str, amount: Decimal) -> Posting:
    """A credit posting."""
    return Posting(account, dimension, unit, -abs(amount))


@dataclass(frozen=True)
class Journal:
    """A balanced set of postings with both time axes and full provenance."""

    id: str
    effective_date: date
    posted_at: datetime
    postings: tuple[Posting, ...]
    actor: str
    command: str
    pack_version: str
    reason: str = ""
    reverses: Optional[str] = None
    evidence: tuple[str, ...] = ()

    def imbalance(self) -> dict[tuple[str, str], Decimal]:
        totals: dict[tuple[str, str], Decimal] = {}
        for p in self.postings:
            key = (p.dimension, p.unit)
            totals[key] = totals.get(key, ZERO) + p.amount
        return {k: v for k, v in totals.items() if v != ZERO}


class Ledger:
    """Append-only. There is deliberately no update or delete method (I5)."""

    def __init__(self) -> None:
        self._journals: list[Journal] = []
        self._by_id: dict[str, Journal] = {}

    def post(self, journal: Journal) -> Journal:
        if journal.id in self._by_id:
            raise LedgerError(f"duplicate journal id {journal.id} (idempotency)")
        if not journal.postings:
            raise LedgerError("a journal needs at least one posting")
        if not journal.actor or not journal.pack_version:
            raise LedgerError("actor and pack_version are required (I12)")
        bad = journal.imbalance()
        if bad:
            raise LedgerError(f"unbalanced journal {journal.id}: {bad} (I1)")
        self._journals.append(journal)
        self._by_id[journal.id] = journal
        return journal

    def get(self, journal_id: str) -> Journal:
        try:
            return self._by_id[journal_id]
        except KeyError:
            raise LedgerError(f"unknown journal {journal_id}") from None

    def journals(self) -> tuple[Journal, ...]:
        return tuple(self._journals)

    def postings(
        self,
        *,
        effective_as_at: Optional[date] = None,
        knowledge_as_at: Optional[datetime] = None,
    ) -> Iterator[tuple[Journal, Posting]]:
        """Every posting visible as at an effective date and a knowledge time."""
        for j in self._journals:
            if effective_as_at is not None and j.effective_date > effective_as_at:
                continue
            if knowledge_as_at is not None and j.posted_at > knowledge_as_at:
                continue
            for p in j.postings:
                yield j, p

    def balance(
        self,
        account: str,
        *,
        effective_as_at: Optional[date] = None,
        knowledge_as_at: Optional[datetime] = None,
    ) -> Decimal:
        """Signed balance. Debit positive."""
        total = ZERO
        for _, p in self.postings(effective_as_at=effective_as_at, knowledge_as_at=knowledge_as_at):
            if p.account == account:
                total += p.amount
        return total

    def credit_balance(self, account: str, **as_at) -> Decimal:
        """Balance shown the way a liability or holder account reads: credit positive."""
        return -self.balance(account, **as_at)

    def reverse(
        self,
        journal_id: str,
        *,
        new_id: str,
        posted_at: datetime,
        actor: str,
        reason: str,
        effective_date: Optional[date] = None,
    ) -> Journal:
        """The only way to undo a journal: a new journal that negates it (I5)."""
        original = self.get(journal_id)
        if not reason:
            raise LedgerError("a reversal needs a reason (I5)")
        postings = tuple(Posting(p.account, p.dimension, p.unit, -p.amount) for p in original.postings)
        return self.post(
            Journal(
                id=new_id,
                effective_date=effective_date or original.effective_date,
                posted_at=posted_at,
                postings=postings,
                actor=actor,
                command="Reverse",
                pack_version=original.pack_version,
                reason=reason,
                reverses=journal_id,
            )
        )
