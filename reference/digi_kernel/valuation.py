"""Valuation: calculate, don't store (I6). Every value carries its price basis."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Iterable, Optional

from .prices import Price, PriceBook
from .register import Register

ZERO = Decimal("0")
CENTS = Decimal("0.01")


def cpu_to_amount(units: Decimal, cpu: Decimal) -> Decimal:
    """Rand amount for units at a cents-per-unit price. Rounded once, at the end."""
    return (units * cpu / Decimal(100)).quantize(CENTS, rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class Valuation:
    account: str
    class_id: str
    units: Decimal
    price: Optional[Price]
    amount: Optional[Decimal]
    price_age_days: Optional[int]
    stale: bool

    @property
    def basis(self) -> str:
        if self.price is None:
            return "no price"
        return f"{self.price.kind} {self.price.pricing_date.isoformat()} v{self.price.version}, age {self.price_age_days}d"


def value_holding(
    register: Register,
    prices: PriceBook,
    account: str,
    class_id: str,
    *,
    effective_as_at: date,
    knowledge_as_at: Optional[datetime] = None,
    policy: str = "official-latest",
    stale_after_days: int = 3,
) -> Valuation:
    units = register.units(account, class_id, effective_as_at=effective_as_at, knowledge_as_at=knowledge_as_at)
    price = prices.select(class_id, effective_as_at=effective_as_at, knowledge_as_at=knowledge_as_at, policy=policy)
    if price is None:
        return Valuation(account, class_id, units, None, None, None, True)
    age = (effective_as_at - price.pricing_date).days
    return Valuation(account, class_id, units, price, cpu_to_amount(units, price.cpu), age, age > stale_after_days)


@dataclass(frozen=True)
class AccountValuation:
    account: str
    lines: tuple[Valuation, ...]
    total: Decimal
    oldest_price_date: Optional[date]
    coverage: Decimal  # share of value priced within one day of the effective date


def value_account(
    register: Register,
    prices: PriceBook,
    account: str,
    class_ids: Iterable[str],
    *,
    effective_as_at: date,
    knowledge_as_at: Optional[datetime] = None,
    policy: str = "official-latest",
    stale_after_days: int = 3,
) -> AccountValuation:
    lines = tuple(
        value_holding(
            register, prices, account, c,
            effective_as_at=effective_as_at, knowledge_as_at=knowledge_as_at,
            policy=policy, stale_after_days=stale_after_days,
        )
        for c in class_ids
    )
    priced = [line for line in lines if line.amount is not None]
    total = sum((line.amount for line in priced), ZERO)
    oldest = min((line.price.pricing_date for line in priced), default=None)
    fresh = sum((line.amount for line in priced if line.price_age_days is not None and line.price_age_days <= 1), ZERO)
    coverage = (fresh / total).quantize(Decimal("0.0001")) if total else Decimal("1")
    return AccountValuation(account, lines, total, oldest, coverage)
