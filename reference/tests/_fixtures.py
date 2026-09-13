"""Shared helpers for the reference model tests."""

from __future__ import annotations

import os
import sys
from datetime import date, datetime
from decimal import Decimal

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from digi_kernel import Approval, Kernel, LossPolicy  # noqa: E402

D = Decimal
FUND = "EXB"
CLASS = "EXB-A"
SIGNERS = ("pricing_1", "pricing_2")

POLICY = LossPolicy(
    owners={
        "manco_error": "MANCO_ERROR_ACCOUNT",
        "system_outage": "MANCO_ERROR_ACCOUNT",
        "sla_intermediary": "INTERMEDIARY_ACCOUNT:LISP-1",
        "unpaid_collection": "MANCO_ERROR_ACCOUNT",
    },
    approvals_required=2,
    max_age_days=30,
)


def at(day: int, hour: int = 10, minute: int = 0, month: int = 9) -> datetime:
    return datetime(2026, month, day, hour, minute)


def on(day: int, month: int = 9) -> date:
    return date(2026, month, day)


VERIFIED_ACCOUNTS = ("ACC-1", "ACC-2", "ACC-3", "ACC-4", "ACC-9", "BUYER", "SELLER")


def kernel(**kwargs) -> Kernel:
    defaults = dict(tenant="example-manco", pack_version="2026.10.0", loss_policy=POLICY)
    defaults.update(kwargs)
    k = Kernel(**defaults)
    for account in VERIFIED_ACCOUNTS:
        k.set_kyc_status(account=account, status="verified", actor="fica_officer", at=at(1, 8))
    return k


def price(k: Kernel, day: int, cpu: str, *, month: int = 9, hour: int = 17, override: str | None = None) -> None:
    """Publish an official price for `day`, visible from `hour` on that day."""
    k.publish_price(class_id=CLASS, pricing_date=on(day, month), cpu=D(cpu), at=at(day, hour, month=month),
                    signed_by=SIGNERS, override_reason=override)


def invest(k: Kernel, *, ins_id: str, account: str, amount: str, day: int, hour: int = 10, price_it: bool = True):
    """Cash in, instruction, match, price. Returns the deal (or the instruction if not priced)."""
    line = k.receive_cash(bank_account="TRUST-1", fund=FUND, amount=D(amount), reference=ins_id, at=at(day, hour - 1), actor="bank_feed")
    ins = k.receive_instruction(
        id=ins_id, account=account, class_id=CLASS, fund=FUND, kind="invest",
        received_at=at(day, hour), dealing_date=on(day), amount=D(amount),
    )
    k.match_cash(instruction_id=ins.id, bank_line_id=line.id, at=at(day, hour, 5), actor="cash_clerk")
    if not price_it:
        return ins
    return k.price_investment(instruction_id=ins.id, at=at(day, 18), actor="dealing_clerk")


def approvals(*actors: str, day: int = 6) -> list[Approval]:
    return [Approval(role=f"role_{i}", actor=a, at=at(day, 11)) for i, a in enumerate(actors)]
