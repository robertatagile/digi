"""The unit register. Positions are derived from unit postings, never stored (I2, I6).

One account holds any number of instruments. The control side per class is UNITS_IN_ISSUE for an
instrument this tenant issues and NOMINEE_BULK for one another manco issues. The invariant is the same.
"""

from __future__ import annotations

from decimal import Decimal

from .ledger import Ledger

ZERO = Decimal("0")
HOLDER_PREFIXES = ("HOLDING:", "HOLDING_LOCKED:", "BOX:", "ROUNDING_UNITS:")


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


def nominee_bulk_account(class_id: str) -> str:
    return f"NOMINEE_BULK:{class_id}"


def rounding_units_account(class_id: str) -> str:
    return f"ROUNDING_UNITS:{class_id}"


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

    def nominee_bulk(self, class_id: str, **as_at) -> Decimal:
        return self.ledger.balance(nominee_bulk_account(class_id), **as_at)

    def control_total(self, class_id: str, **as_at) -> Decimal:
        """Issuer-side quantity: units in issue for an own class, nominee bulk for an external one."""
        return self.units_in_issue(class_id, **as_at) + self.nominee_bulk(class_id, **as_at)

    def holders_total(self, class_id: str, **as_at) -> Decimal:
        total = ZERO
        for _, p in self.ledger.postings(**as_at):
            if p.dimension == "units" and p.unit == class_id and p.account.startswith(HOLDER_PREFIXES):
                total -= p.amount
        return total

    def check(self, class_id: str, **as_at) -> None:
        """Invariant I2: the holder side equals the control side. Unit postings hit known accounts only."""
        controls = (in_issue_account(class_id), nominee_bulk_account(class_id))
        for j, p in self.ledger.postings(**as_at):
            if p.dimension != "units" or p.unit != class_id:
                continue
            if not (p.account.startswith(HOLDER_PREFIXES) or p.account in controls):
                raise RegisterError(f"journal {j.id} posts units to an unknown account {p.account}")
        holders = self.holders_total(class_id, **as_at)
        control = self.control_total(class_id, **as_at)
        if holders != control:
            raise RegisterError(f"register break for {class_id}: holders {holders} vs control total {control} (I2)")
