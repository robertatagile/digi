"""Control plane primitives: approvals (I9), loss policy (I7), day close (I11)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Iterable, Mapping


class ControlError(Exception):
    """Raised when a control is not satisfied."""


@dataclass(frozen=True)
class Approval:
    role: str
    actor: str
    at: datetime


def require_approvals(maker: str, approvals: Iterable[Approval], minimum: int) -> tuple[Approval, ...]:
    """Maker is never a checker. Every approver is a different person. At least `minimum` of them."""
    approvals = tuple(approvals)
    actors = [a.actor for a in approvals]
    if maker in actors:
        raise ControlError(f"maker {maker!r} cannot approve their own command (I9)")
    if len(set(actors)) != len(actors):
        raise ControlError("each approver must be a different person (I9)")
    if len(approvals) < minimum:
        raise ControlError(f"{minimum} approvals required, {len(approvals)} given (I9)")
    return approvals


@dataclass(frozen=True)
class LossPolicy:
    """Pack-supplied. Maps a backdating or reversal reason to the account that owns the delta (I7)."""

    owners: Mapping[str, str] = field(default_factory=dict)
    approvals_required: int = 2
    max_age_days: int = 30

    def owner_for(self, reason: str) -> str:
        try:
            return self.owners[reason]
        except KeyError:
            raise ControlError(f"no loss owner for reason {reason!r}; the pack must name one (I7)") from None


class DayClose:
    """Locks dealing dates. There is deliberately no reopen method (I11)."""

    def __init__(self) -> None:
        self._closed: set[date] = set()

    def close(self, dealing_date: date) -> None:
        self._closed.add(dealing_date)

    def is_closed(self, dealing_date: date) -> bool:
        return dealing_date in self._closed
