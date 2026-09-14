"""Switch, transfer, distribution and fees compose from the same primitives."""

import unittest
from decimal import Decimal

from _fixtures import CLASS, D, FUND, approvals, at, invest, kernel, on, price
from digi_kernel import BlockError, ControlError

EXG = "EXG-A"
EXG_FUND = "EXG"


class Switch(unittest.TestCase):
    def setUp(self):
        self.k = kernel()
        price(self.k, 1, "1000.00")
        invest(self.k, ins_id="I1", account="ACC-1", amount="100000", day=1)
        price(self.k, 2, "1010.00")
        self.k.receive_switch(id="S1", account="ACC-1", from_class=CLASS, to_class=EXG, from_fund=FUND, to_fund=EXG_FUND,
                              units=D("4000"), received_at=at(2, 10), dealing_date=on(2))

    def test_both_legs_or_neither(self):
        before = len(self.k.ledger.journals())
        with self.assertRaises(BlockError):
            self.k.price_switch(instruction_id="S1", at=at(2, 18), actor="dealing_clerk")  # no EXG-A price yet
        self.assertEqual(len(self.k.ledger.journals()), before)
        self.assertEqual(self.k.register.units("ACC-1", CLASS), D("10000.0000"))

    def test_one_journal_two_deals_clearing_nets_to_zero(self):
        self.k.publish_price(class_id=EXG, pricing_date=on(2), cpu=D("500.00"), at=at(2, 17), signed_by=("pricing_1", "pricing_2"))
        out, into = self.k.price_switch(instruction_id="S1", at=at(2, 18), actor="dealing_clerk")
        self.assertEqual(out.journal_id, into.journal_id)
        self.assertEqual(out.investor_amount, D("40400.00"))
        self.assertEqual(into.units, D("8080.0000"))
        self.assertEqual(self.k.register.units("ACC-1", CLASS), D("6000.0000"))
        self.assertEqual(self.k.register.units("ACC-1", EXG), D("8080.0000"))
        self.assertEqual(self.k.ledger.balance("SWITCH_CLEARING"), D("0"))
        self.assertEqual(self.k.ledger.balance("REDEMPTIONS_DUE_FROM_FUND:EXB"), D("40400.00"))
        self.assertEqual(self.k.ledger.credit_balance("SUBS_PAYABLE_TO_FUND:EXG"), D("40400.00"))
        self.k.register.check(CLASS)
        self.k.register.check(EXG)

    def test_unpriced_switch_blocks_day_close(self):
        with self.assertRaises(ControlError) as ctx:
            self.k.close_day(on(2), actor="ops_manager", at=at(2, 19))
        self.assertIn("switch S1", str(ctx.exception))


class Transfer(unittest.TestCase):
    def setUp(self):
        self.k = kernel()
        price(self.k, 1, "1000.00")
        invest(self.k, ins_id="I1", account="ACC-1", amount="100000", day=1)

    def test_units_move_without_a_price_or_money(self):
        money_before = [j.id for j in self.k.ledger.journals()]
        j = self.k.transfer_units(from_account="ACC-1", to_account="ACC-2", class_id=CLASS, units=D("2000"),
                                  at=at(9, 10), actor="ops_clerk", reason="estate: letters of executorship", evidence=["doc:LOE-4411"])
        self.assertEqual(self.k.register.units("ACC-1", CLASS), D("8000.0000"))
        self.assertEqual(self.k.register.units("ACC-2", CLASS), D("2000.0000"))
        self.assertTrue(all(p.dimension == "units" for p in j.postings))
        self.assertEqual(self.k.register.units_in_issue(CLASS), D("10000.0000"))
        self.assertIn("obligation:FICA-CDD", j.evidence)
        self.assertEqual(len(self.k.ledger.journals()), len(money_before) + 1)

    def test_receiver_must_be_verified_and_a_reason_is_required(self):
        with self.assertRaises(ControlError):
            self.k.transfer_units(from_account="ACC-1", to_account="ACC-NEW", class_id=CLASS, units=D("10"),
                                  at=at(9, 10), actor="ops_clerk", reason="re-registration")
        with self.assertRaises(BlockError):
            self.k.transfer_units(from_account="ACC-1", to_account="ACC-2", class_id=CLASS, units=D("10"),
                                  at=at(9, 10), actor="ops_clerk", reason="")


class DistributionBlock(unittest.TestCase):
    def setUp(self):
        self.k = kernel()
        self.k.set_kyc_status(account="TFSA-1", status="verified", actor="fica_officer", at=at(1, 8))
        price(self.k, 1, "1000.00")
        invest(self.k, ins_id="I1", account="ACC-1", amount="100000", day=1)
        for i, account in enumerate(("ACC-2", "ACC-3", "TFSA-1"), start=2):
            invest(self.k, ins_id=f"I{i}", account=account, amount="33333.33", day=1)
        price(self.k, 2, "1000.00")
        # ACC-1 redeems 4 000 units on 2 September, after the record date. The entitlement must not shrink.
        self.k.receive_instruction(id="R1", account="ACC-1", class_id=CLASS, fund=FUND, kind="redeem",
                                   received_at=at(2, 10), dealing_date=on(2), units=D("4000"))
        self.k.lock_units(instruction_id="R1", at=at(2, 10), actor="dealing_clerk")
        self.k.price_redemption(instruction_id="R1", at=at(2, 18), actor="dealing_clerk")
        self.dist = self.k.declare_distribution(class_id=CLASS, fund=FUND, cpu=D("12.5"), record_date=on(1), pay_date=on(5),
                                                at=at(3, 9), signed_by=("fund_accountant", "financial_manager"), tax_rate=D("0.20"))

    def test_declaration_needs_two_signers(self):
        with self.assertRaises(ControlError):
            self.k.declare_distribution(class_id=CLASS, fund=FUND, cpu=D("1"), record_date=on(1), pay_date=on(5),
                                        at=at(3, 9), signed_by=("fund_accountant",))

    def test_entitlements_are_derived_at_the_record_date_and_rounding_has_its_own_account(self):
        j = self.k.allocate_distribution(distribution_id=self.dist.id, at=at(3, 10), actor="ops_clerk",
                                         option_for=lambda a: "reinvest" if a in ("ACC-1", "TFSA-1") else "payout",
                                         exempt=lambda a: a.startswith("TFSA-"))
        e = self.dist.entitlements
        self.assertEqual(e["ACC-1"].units, D("10000.0000"))      # record-date units, not today's 6 000
        self.assertEqual(e["ACC-1"].gross, D("1250.00"))
        self.assertEqual(e["ACC-1"].tax, D("250.00"))
        self.assertEqual(e["ACC-2"].gross, D("416.67"))
        self.assertEqual(e["TFSA-1"].tax, D("0"))
        self.assertEqual(self.dist.declared_total, D("2500.00"))
        self.assertEqual(self.dist.rounding, D("-0.01"))
        self.assertEqual(self.k.ledger.balance("ROUNDING"), D("0.01"))
        self.assertEqual(self.k.ledger.credit_balance("TAX_WITHHELD_PAYABLE"), D("416.66"))
        self.assertEqual(self.k.ledger.credit_balance("DISTRIBUTIONS_PAYABLE:EXB"), D("2083.35"))
        self.assertEqual(j.effective_date, on(1))

    def test_reinvest_at_the_pay_date_price_or_pay_out(self):
        self.k.allocate_distribution(distribution_id=self.dist.id, at=at(3, 10), actor="ops_clerk",
                                     option_for=lambda a: "reinvest" if a in ("ACC-1", "TFSA-1") else "payout",
                                     exempt=lambda a: a.startswith("TFSA-"))
        price(self.k, 5, "1010.00")
        deals, payables = self.k.settle_distribution(distribution_id=self.dist.id, at=at(5, 18), actor="ops_clerk")
        by_account = {d.account: d for d in deals}
        self.assertEqual(by_account["ACC-1"].units, D("99.0099"))      # R1 000 net at 1 010 cpu
        self.assertEqual(by_account["TFSA-1"].units, D("41.2545"))     # R416.67, no tax inside the wrapper
        self.assertEqual(sorted(p.account for p in payables), ["ACC-2", "ACC-3"])
        self.assertTrue(all(p.amount == D("333.34") and p.kind == "distribution" for p in payables))
        self.assertEqual(self.k.ledger.credit_balance("DISTRIBUTIONS_PAYABLE:EXB"), D("666.68"))
        self.k.register.check(CLASS)
        payable = payables[0]
        self.k.instruct_payment(payable_id=payable.id, maker="payments_clerk", approvals=approvals("checker"), at=at(6, 9))
        self.k.confirm_payment(payable_id=payable.id, bank_account="TRUST-1", at=at(6, 15), actor="bank_feed")
        self.assertEqual(self.k.ledger.credit_balance("DISTRIBUTIONS_PAYABLE:EXB"), D("333.34"))


class Fees(unittest.TestCase):
    def setUp(self):
        self.k = kernel()
        price(self.k, 1, "1000.00")
        invest(self.k, ins_id="I1", account="ACC-1", amount="100000", day=1)
        price(self.k, 2, "1010.00")

    def test_accrual_is_computed_from_daily_facts(self):
        fee = self.k.accrue_fee(account="ACC-1", class_id=CLASS, rate_pa=D("0.005"), start=on(1), end=on(30))
        expected = ((D("100000") + 29 * D("101000")) * D("0.005") / D("365")).quantize(D("0.01"))
        self.assertEqual(fee, expected)
        self.assertEqual(fee, D("41.49"))
        # Nothing was stored. A different knowledge time gives the accrual as it was known then.
        early = self.k.accrue_fee(account="ACC-1", class_id=CLASS, rate_pa=D("0.005"), start=on(1), end=on(30), knowledge_as_at=at(2, 9))
        self.assertEqual(early, (30 * D("100000") * D("0.005") / D("365")).quantize(D("0.01")))

    def test_collection_cancels_units_and_pays_through_the_fais_gate(self):
        price(self.k, 30, "1010.00")
        deal, payable = self.k.collect_fee(account="ACC-1", class_id=CLASS, fund=FUND, amount=D("41.49"), beneficiary="ADV-1",
                                           dealing_date=on(30), at=at(30, 18), actor="fee_run", period="2026-09")
        self.assertEqual(deal.units, D("4.1079"))
        self.assertEqual(self.k.register.units("ACC-1", CLASS), D("9995.8921"))
        self.assertEqual(self.k.ledger.credit_balance("FEES_PAYABLE:ADV-1"), D("41.49"))
        self.assertEqual(self.k.ledger.balance("FEES_DUE_FROM_FUND:EXB"), D("41.49"))
        self.k.set_adviser_status(adviser="ADV-1", status="lapsed", actor="compliance", at=at(30, 8))
        with self.assertRaises(ControlError) as ctx:
            self.k.instruct_payment(payable_id=payable.id, maker="payments_clerk", approvals=approvals("checker", day=30), at=at(30, 19))
        self.assertIn("Blocked by FAIS-ADVISER-LICENCE", str(ctx.exception))
        self.assertEqual(payable.status, "open")
        self.k.set_adviser_status(adviser="ADV-1", status="licensed", actor="compliance", at=at(30, 20))
        j = self.k.instruct_payment(payable_id=payable.id, maker="payments_clerk", approvals=approvals("checker", day=30), at=at(30, 21))
        self.assertIn("obligation:FAIS-ADVISER-LICENCE", j.evidence)
        self.assertEqual([x.command for x in self.k.regulatory_trail("FAIS-ADVISER-LICENCE")], ["InstructPayment"])
        self.k.register.check(CLASS)

    def test_a_fee_cannot_exceed_the_holding(self):
        with self.assertRaises(BlockError):
            self.k.collect_fee(account="ACC-1", class_id=CLASS, fund=FUND, amount=D("999999"), beneficiary="ADV-1",
                               dealing_date=on(2), at=at(2, 18), actor="fee_run", period="2026-09")


if __name__ == "__main__":
    unittest.main()
