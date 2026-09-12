"""The unit register. Positions are derived from unit postings, never stored (I2, I6)."""

from __future__ import annotations

from decimal import Decimal

from .ledger import Ledger

ZERO = Decimal("0")
HOLDER_PREFIXES = ("HOLDING:", "HOLDING_LOCKED:", "BOX:")


class RegisterError(Exception):
    """Raised when the register does not reconcile."""


def holding_account(account: str, class_id: str) -> str:
    return f"HOLDING:{account}:{class_id}"


def locked_account(account: str, class_id: str) -> str:
    return f"HOLDING_LOCKED:{account}:{class_id}"


def box_account(class_id: str) -> str:
    return f"BOX:{class_id}"


def in_issue_account(class_id: str) -> str:
    return f"UNITS_IN_ISSUE:{class_id}"


class Register:
    def __init__(self, ledger: Ledger) -> None:
        self.ledger = ledger

    def units(self, account: str, class_id: str, **as_at) -> Decimal:
        """Total units held, including units locked for a pending redemption or fee."""
        return self.ledger.credit_balance(holding_account(account, class_id), **as_at) + self.ledger.credit_balance(
            locked_account(account, class_id), **as_at
        )

    def available_units(self, account: str, class_id: str, **as_at) -> Decimal:
        """Units free to deal: held minus locked."""
        return self.ledger.credit_balance(holding_account(account, class_id), **as_at)

    def units_in_issue(self, class_id: str, **as_at) -> Decimal:
        return self.ledger.balance(in_issue_account(class_id), **as_at)

    def holders_total(self, class_id: str, **as_at) -> Decimal:
        total = ZERO
        for _, p in self.ledger.postings(**as_at):
            if p.dimension == "units" and p.unit == class_id and p.account.startswith(HOLDER_PREFIXES):
                total -= p.amount
        return total

    def check(self, class_id: str, **as_at) -> None:
        """Invariant I2: holders plus box equal units in issue. Unit postings hit known accounts only."""
        for j, p in self.ledger.postings(**as_at):
            if p.dimension != "units" or p.unit != class_id:
                continue
            if not (p.account.startswith(HOLDER_PREFIXES) or p.account == in_issue_account(class_id)):
                raise RegisterError(f"journal {j.id} posts units to an unknown account {p.account}")
        holders = self.holders_total(class_id, **as_at)
        in_issue = self.units_in_issue(class_id, **as_at)
        if holders != in_issue:
            raise RegisterError(f"register break for {class_id}: holders {holders} vs units in issue {in_issue} (I2)")
