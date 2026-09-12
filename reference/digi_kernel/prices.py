"""Prices are facts. They are versioned and never overwritten (I10)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Optional


class PriceError(Exception):
    """Raised when a price cannot be accepted."""


@dataclass(frozen=True)
class Price:
    class_id: str
    pricing_date: date
    version: int
    cpu: Decimal  # cents per unit
    kind: str = "official"  # "official" or "indicative"
    published_at: Optional[datetime] = None
    signed_by: tuple[str, ...] = ()
    source: str = ""

    @property
    def ref(self) -> str:
        return f"price:{self.class_id}:{self.pricing_date.isoformat()}:{self.kind}:v{self.version}"


class PriceBook:
    """Series of prices per class. Official prices need four eyes and pass a movement check."""

    def __init__(self, movement_tolerance: Decimal = Decimal("0.05")) -> None:
        self._prices: list[Price] = []
        self.movement_tolerance = movement_tolerance

    def publish(self, price: Price, *, override_reason: Optional[str] = None) -> Price:
        if price.kind not in ("official", "indicative"):
            raise PriceError(f"unknown price kind {price.kind!r}")
        if not isinstance(price.cpu, Decimal) or price.cpu <= 0:
            raise PriceError("price must be a positive Decimal")
        if price.published_at is None:
            raise PriceError("published_at is required")
        if price.kind == "official" and len(set(price.signed_by)) < 2:
            raise PriceError("an official price needs two distinct signers (four eyes)")
        existing = self.versions(price.class_id, price.pricing_date, price.kind)
        expected = existing[-1].version + 1 if existing else 1
        if price.version != expected:
            raise PriceError(
                f"expected version {expected} for {price.class_id} {price.pricing_date} {price.kind}; "
                "prices are never overwritten (I10)"
            )
        previous = self._previous_official(price.class_id, price.pricing_date)
        if price.kind == "official" and previous is not None:
            movement = abs(price.cpu - previous.cpu) / previous.cpu
            if movement > self.movement_tolerance and not override_reason:
                raise PriceError(
                    f"movement of {movement:.4%} breaches the tolerance; an override reason is required"
                )
        self._prices.append(price)
        return price

    def versions(self, class_id: str, pricing_date: date, kind: str = "official") -> list[Price]:
        found = [
            p for p in self._prices
            if p.class_id == class_id and p.pricing_date == pricing_date and p.kind == kind
        ]
        return sorted(found, key=lambda p: p.version)

    def _previous_official(self, class_id: str, before: date) -> Optional[Price]:
        pool = [p for p in self._prices if p.class_id == class_id and p.kind == "official" and p.pricing_date < before]
        if not pool:
            return None
        latest = max(p.pricing_date for p in pool)
        return max((p for p in pool if p.pricing_date == latest), key=lambda p: p.version)

    def official_at(
        self, class_id: str, pricing_date: date, *, knowledge_as_at: Optional[datetime] = None
    ) -> Optional[Price]:
        """The official price for a pricing point as known at a time. Highest visible version."""
        visible = [
            p for p in self.versions(class_id, pricing_date, "official")
            if knowledge_as_at is None or p.published_at <= knowledge_as_at
        ]
        return visible[-1] if visible else None

    def select(
        self,
        class_id: str,
        *,
        effective_as_at: date,
        knowledge_as_at: Optional[datetime] = None,
        policy: str = "official-latest",
    ) -> Optional[Price]:
        """Price selection with a policy. Returns the price and therefore its provenance."""

        def visible(p: Price) -> bool:
            return (
                p.class_id == class_id
                and p.pricing_date <= effective_as_at
                and (knowledge_as_at is None or p.published_at <= knowledge_as_at)
            )

        if policy == "official-latest":
            pool = [p for p in self._prices if visible(p) and p.kind == "official"]
        elif policy == "indicative-latest":
            pool = [p for p in self._prices if visible(p)]
        else:
            raise PriceError(f"unknown price policy {policy!r}")
        if not pool:
            return None
        latest = max(p.pricing_date for p in pool)
        same_day = sorted((p for p in pool if p.pricing_date == latest), key=lambda p: (p.kind == "official", p.version))
        return same_day[-1]
