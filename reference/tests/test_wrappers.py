"""Product wrappers are guards on the same blocks.

The guards below stand in for what a generated pack would express in products/tfsa.yaml and
products/retirement-annuity.yaml. The kernel only offers add_guard, holds and derived counters.
"""

import unittest
from datetime import date
from decimal import Decimal

from _fixtures import CLASS, D, FUND, approvals, at, kernel, on, price
from digi_kernel import BlockError, ControlError, account_root


def tax_year(d: date) -> tuple[date, date]:
    """South African tax year: 1 March to end of February."""
    start = date(d.year if d.month >= 3 else d.year - 1, 3, 1)
    return start, date(start.year + 1, 2, 28)


def tfsa_contribution_limit(annual=D("36000"), lifetime=D("500000")):
    """ITA s12T. Limits are pack parameters with a source and an effective date."""
    def guard(k, ins):
        if not ins.account.startswith("TFSA-"):
            return None
        start, end = tax_year(ins.dealing_date)
        if k.contributions(ins.account, start=start, end=end) + ins.amount > annual:
            return f"annual tax-free contribution limit R{annual} would be exceeded (ITA s12T)"
        if k.contributions(ins.account, start=date.min, end=date.max) + ins.amount > lifetime:
            return f"lifetime tax-free contribution limit R{lifetime} would be exceeded (ITA s12T)"
        return None
    return guard


def ra_withdrawal_rules(birthdates: dict, retirement_age=55, savings_minimum=D("2000")):
    """Pension Funds Act, fund rules and the two-pot regime. Components are sub-accounts ACCOUNT:component."""
    def guard(k, ins):
        root, _, component = ins.account.partition(":")
        if not root.startswith("RA-"):
            return None
        if component == "savings":
            start, end = tax_year(ins.dealing_date)
            prior = [
                i for i in k.instructions.values()
                if i.account == ins.account and i.kind == "redeem" and i.id != ins.id
                and i.status != "rejected" and start <= i.dealing_date <= end
            ]
            if prior:
                return "one savings component withdrawal per tax year (two-pot)"
            last = k.prices.select(ins.class_id, effective_as_at=ins.dealing_date)
            if last is not None and ins.units * last.cpu / 100 < savings_minimum:
                return f"savings withdrawal below the minimum R{savings_minimum} (two-pot)"
            return None
        born = birthdates[root]
        age = ins.dealing_date.year - born.year - ((ins.dealing_date.month, ins.dealing_date.day) < (born.month, born.day))
        if age < retirement_age:
            return f"{component or 'retirement'} component is locked before age {retirement_age} (Pension Funds Act, fund rules)"
        return None
    return guard


def contribute(k, *, ins_id, account, amount, day, month=9, year=2026):
    from datetime import datetime
    when = datetime(year, month, day, 10)
    line = k.receive_cash(bank_account="TRUST-1", fund=FUND, amount=D(amount), reference=ins_id, at=when, actor="bank_feed")
    k.receive_instruction(id=ins_id, account=account, class_id=CLASS, fund=FUND, kind="invest",
                          received_at=when, dealing_date=when.date(), amount=D(amount))
    return k.match_cash(instruction_id=ins_id, bank_line_id=line.id, at=when, actor="cash_clerk")


class TaxFreeSavings(unittest.TestCase):
    def setUp(self):
        self.k = kernel()
        self.k.set_kyc_status(account="TFSA-1", status="verified", actor="fica_officer", at=at(1, 8))
        self.k.add_guard(command="MatchCash", rule="tfsa-contribution-limit", guard=tfsa_contribution_limit())

    def test_contributions_within_the_limit_are_ordinary_investments(self):
        j = contribute(self.k, ins_id="T1", account="TFSA-1", amount="20000", day=1)
        contribute(self.k, ins_id="T2", account="TFSA-1", amount="16000", day=2)
        self.assertIn("rule:tfsa-contribution-limit", j.evidence)
        self.assertEqual(self.k.contributions("TFSA-1", start=date(2026, 3, 1), end=date(2027, 2, 28)), D("36000"))

    def test_the_excess_is_refused_and_the_cash_stays_refundable(self):
        contribute(self.k, ins_id="T1", account="TFSA-1", amount="36000", day=1)
        with self.assertRaises(ControlError) as ctx:
            contribute(self.k, ins_id="T3", account="TFSA-1", amount="1000", day=3)
        self.assertIn("s12T", str(ctx.exception))
        self.assertEqual(self.k.instructions["T3"].status, "received")
        self.assertEqual(self.k.ledger.credit_balance("UNALLOCATED_CASH:EXB"), D("1000"))

    def test_the_counter_resets_with_the_tax_year_but_the_lifetime_limit_does_not(self):
        k = kernel()
        k.set_kyc_status(account="TFSA-2", status="verified", actor="fica_officer", at=at(1, 8))
        k.add_guard(command="MatchCash", rule="tfsa-contribution-limit", guard=tfsa_contribution_limit(lifetime=D("50000")))
        contribute(k, ins_id="A", account="TFSA-2", amount="36000", day=2, month=3, year=2026)   # tax year 2026/27
        contribute(k, ins_id="B", account="TFSA-2", amount="14000", day=2, month=3, year=2027)   # tax year 2027/28
        with self.assertRaises(ControlError) as ctx:
            contribute(k, ins_id="C", account="TFSA-2", amount="1", day=3, month=3, year=2027)
        self.assertIn("lifetime", str(ctx.exception))

    def test_other_accounts_are_untouched_by_the_guard(self):
        contribute(self.k, ins_id="D1", account="ACC-1", amount="250000", day=1)
        self.assertEqual(self.k.instructions["D1"].status, "matched")


class RetirementAnnuity(unittest.TestCase):
    def setUp(self):
        self.k = kernel()
        self.k.set_kyc_status(account="RA-7", status="verified", actor="fica_officer", at=at(1, 8))  # FICA on the root
        self.k.add_guard(command="LockUnits", rule="ra-withdrawal", guard=ra_withdrawal_rules({"RA-7": date(1986, 5, 20)}))
        price(self.k, 1, "1000.00")
        for ins_id, component, amount in (("C1", "savings", "10000"), ("C2", "retirement", "20000")):
            contribute(self.k, ins_id=ins_id, account=f"RA-7:{component}", amount=amount, day=1)
            self.k.price_investment(instruction_id=ins_id, at=at(1, 18), actor="dealing_clerk")
        price(self.k, 2, "1000.00")

    def redeem(self, component, units, ins_id="W1", day=2):
        self.k.receive_instruction(id=ins_id, account=f"RA-7:{component}", class_id=CLASS, fund=FUND, kind="redeem",
                                   received_at=at(day, 10), dealing_date=on(day), units=D(units))
        return self.k.lock_units(instruction_id=ins_id, at=at(day, 10), actor="dealing_clerk")

    def test_components_are_ordinary_holdings_on_the_same_register(self):
        self.assertEqual(self.k.register.units("RA-7:savings", CLASS), D("1000.0000"))
        self.assertEqual(self.k.register.units("RA-7:retirement", CLASS), D("2000.0000"))
        self.assertEqual(account_root("RA-7:savings"), "RA-7")
        self.k.register.check(CLASS)

    def test_the_retirement_component_is_locked_before_retirement_age(self):
        with self.assertRaises(ControlError) as ctx:
            self.redeem("retirement", "100")
        self.assertIn("age 55", str(ctx.exception))
        self.assertEqual(self.k.register.available_units("RA-7:retirement", CLASS), D("2000.0000"))

    def test_one_savings_withdrawal_per_tax_year(self):
        j = self.redeem("savings", "500", ins_id="W1", day=2)
        self.assertIn("rule:ra-withdrawal", j.evidence)
        with self.assertRaises(ControlError) as ctx:
            self.redeem("savings", "100", ins_id="W2", day=3)
        self.assertIn("one savings component withdrawal", str(ctx.exception))

    def test_savings_withdrawal_below_the_minimum_is_refused(self):
        with self.assertRaises(ControlError) as ctx:
            self.redeem("savings", "100")  # 100 units at R10.00 = R1 000
        self.assertIn("minimum", str(ctx.exception))

    def test_payment_waits_for_the_tax_directive_and_the_release_withholds(self):
        self.redeem("savings", "500")
        deal, payable = self.k.price_redemption(instruction_id="W1", at=at(2, 18), actor="dealing_clerk", holds=("tax_directive",))
        self.assertEqual(payable.amount, D("5000.00"))
        with self.assertRaises(ControlError) as ctx:
            self.k.instruct_payment(payable_id=payable.id, maker="payments_clerk", approvals=approvals("checker"), at=at(3, 9))
        self.assertIn("held", str(ctx.exception))
        with self.assertRaises(ControlError):
            self.k.release_hold(payable_id=payable.id, hold="tax_directive", reference="", at=at(4, 9), actor="tax_clerk")
        j = self.k.release_hold(payable_id=payable.id, hold="tax_directive", reference="SARS-DIR-2026-001234",
                                at=at(4, 9), actor="tax_clerk", tax_withheld=D("900"), obligation="ITA-TAX-DIRECTIVE")
        self.assertEqual(payable.amount, D("4100.00"))
        self.assertEqual(self.k.ledger.credit_balance("TAX_WITHHELD_PAYABLE"), D("900"))
        self.assertIn("tax_directive:SARS-DIR-2026-001234", j.evidence)
        self.k.instruct_payment(payable_id=payable.id, maker="payments_clerk", approvals=approvals("checker"), at=at(4, 10))
        self.k.confirm_payment(payable_id=payable.id, bank_account="TRUST-1", at=at(4, 15), actor="bank_feed")
        self.assertEqual(self.k.ledger.balance("REDEMPTIONS_PAYABLE:EXB"), D("0"))
        self.assertEqual([x.command for x in self.k.regulatory_trail("ITA-TAX-DIRECTIVE")], ["ReleaseHold"])

    def test_a_hold_cannot_be_released_twice(self):
        self.redeem("savings", "500")
        _, payable = self.k.price_redemption(instruction_id="W1", at=at(2, 18), actor="dealing_clerk", holds=("tax_directive",))
        self.k.release_hold(payable_id=payable.id, hold="tax_directive", reference="SARS-1", at=at(4, 9), actor="tax_clerk")
        with self.assertRaises(BlockError):
            self.k.release_hold(payable_id=payable.id, hold="tax_directive", reference="SARS-1", at=at(4, 9), actor="tax_clerk")


if __name__ == "__main__":
    unittest.main()
