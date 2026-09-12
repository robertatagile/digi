import unittest
from decimal import Decimal

from _fixtures import CLASS, D, FUND, POLICY, approvals, at, invest, kernel, on, price
from digi_kernel import BlockError, ControlError, LossPolicy


def matched_investment(k, *, ins_id="I-late", account="ACC-1", amount="100000", day=5):
    """Captured on `day`, so its dealing date is `day`. Evidence will say it arrived earlier."""
    return invest(k, ins_id=ins_id, account=account, amount=amount, day=day, price_it=False)


class BackdatedInvestment(unittest.TestCase):
    def setUp(self):
        self.k = kernel()
        price(self.k, 1, "1000.00")
        self.k.close_day(on(1), actor="ops_manager", at=at(1, 19))
        price(self.k, 5, "1050.00")

    def backdate(self, k, ins, **kw):
        args = dict(instruction_id=ins.id, historical_date=on(1), reason="manco_error", evidence=["email:2026-09-01T09:12"],
                    maker="ops_clerk", approvals=approvals("ops_manager", "finance_manager"), at=at(6, 11))
        args.update(kw)
        return k.backdate_investment(**args)

    def test_closed_day_refuses_ordinary_pricing(self):
        ins = self.k.receive_instruction(id="I-q", account="ACC-1", class_id=CLASS, fund=FUND, kind="invest",
                                         received_at=at(1, 10), dealing_date=on(1), amount=D("1000"))
        line = self.k.receive_cash(bank_account="TRUST-1", fund=FUND, amount=D("1000"), reference="q", at=at(5, 9), actor="bank_feed")
        self.k.match_cash(instruction_id=ins.id, bank_line_id=line.id, at=at(5, 9), actor="cash_clerk")
        with self.assertRaises(ControlError) as ctx:
            self.k.price_investment(instruction_id=ins.id, at=at(5, 18), actor="dealing_clerk")
        self.assertIn("backdate_investment", str(ctx.exception))

    def test_price_rose_owner_pays_the_fund(self):
        ins = matched_investment(self.k)
        deal, record = self.backdate(self.k, ins)
        self.assertEqual(deal.units, D("10000.0000"))
        self.assertEqual(deal.fund_amount, D("105000.00"))
        self.assertEqual(record.delta, D("5000.00"))
        self.assertEqual(record.owner, "MANCO_ERROR_ACCOUNT")
        self.assertEqual(self.k.ledger.balance("MANCO_ERROR_ACCOUNT"), D("5000.00"))
        self.assertEqual(self.k.ledger.credit_balance("SUBS_PAYABLE_TO_FUND:EXB"), D("105000.00"))
        self.assertEqual(self.k.ledger.balance("SUBS_AWAITING_PRICING:EXB"), D("0"))
        self.assertEqual(self.k.ledger.get(deal.journal_id).effective_date, on(1))
        self.k.register.check(CLASS)

    def test_price_fell_owner_receives_the_surplus(self):
        price(self.k, 6, "950.00", override="market fall confirmed by fund accounting")
        ins = matched_investment(self.k, day=6)
        deal, record = self.backdate(self.k, ins, at=at(7, 11))
        self.assertEqual(deal.fund_amount, D("95000.00"))
        self.assertEqual(record.delta, D("-5000.00"))
        self.assertEqual(self.k.ledger.credit_balance("MANCO_ERROR_ACCOUNT"), D("5000.00"))
        self.assertEqual(self.k.ledger.credit_balance("SUBS_PAYABLE_TO_FUND:EXB"), D("95000.00"))

    def test_bitemporal_statement_before_and_after(self):
        ins = matched_investment(self.k)
        self.backdate(self.k, ins)
        as_sent = self.k.statement("ACC-1", [CLASS], effective_as_at=on(1), knowledge_as_at=at(2, 8))
        as_corrected = self.k.statement("ACC-1", [CLASS], effective_as_at=on(1))
        self.assertEqual(as_sent.total, D("0.00"))
        self.assertEqual(as_corrected.total, D("100000.00"))
        self.assertEqual(self.k.register.units_in_issue(CLASS, effective_as_at=on(1), knowledge_as_at=at(1, 19)), D("0"))
        self.assertEqual(self.k.register.units_in_issue(CLASS, effective_as_at=on(1)), D("10000.0000"))

    def test_reason_without_an_owner_is_refused(self):
        ins = matched_investment(self.k)
        with self.assertRaises(ControlError) as ctx:
            self.backdate(self.k, ins, reason="investor_late")
        self.assertIn("I7", str(ctx.exception))
        self.assertEqual(self.k.register.units("ACC-1", CLASS), D("0"))

    def test_maker_cannot_approve(self):
        ins = matched_investment(self.k)
        with self.assertRaises(ControlError):
            self.backdate(self.k, ins, approvals=approvals("ops_clerk", "finance_manager"))

    def test_two_distinct_approvers_are_the_minimum(self):
        ins = matched_investment(self.k)
        with self.assertRaises(ControlError):
            self.backdate(self.k, ins, approvals=approvals("ops_manager"))
        with self.assertRaises(ControlError):
            self.backdate(self.k, ins, approvals=approvals("ops_manager", "ops_manager"))

    def test_pack_can_only_raise_the_approval_count(self):
        k = kernel(loss_policy=LossPolicy(owners=POLICY.owners, approvals_required=1))
        price(k, 1, "1000.00")
        price(k, 5, "1050.00")
        ins = matched_investment(k)
        with self.assertRaises(ControlError):
            self.backdate(k, ins, approvals=approvals("ops_manager"))
        k3 = kernel(loss_policy=LossPolicy(owners=POLICY.owners, approvals_required=3))
        price(k3, 1, "1000.00")
        price(k3, 5, "1050.00")
        ins3 = matched_investment(k3)
        with self.assertRaises(ControlError):
            self.backdate(k3, ins3)
        self.backdate(k3, ins3, approvals=approvals("ops_manager", "finance_manager", "head_of_ops"))

    def test_evidence_and_age_limits(self):
        ins = matched_investment(self.k)
        with self.assertRaises(ControlError):
            self.backdate(self.k, ins, evidence=[])
        with self.assertRaises(ControlError):
            self.backdate(self.k, ins, at=at(15, 11, month=10))

    def test_register_lists_the_decision(self):
        ins = matched_investment(self.k)
        deal, _ = self.backdate(self.k, ins)
        self.assertEqual(len(self.k.backdating_register), 1)
        rec = self.k.backdating_register[0]
        self.assertEqual(rec.deal_id, deal.id)
        self.assertEqual(rec.approvers, ("ops_manager", "finance_manager"))
        self.assertIn("email:2026-09-01T09:12", rec.evidence)


class BackdatedRedemption(unittest.TestCase):
    def setUp(self):
        self.k = kernel()
        price(self.k, 1, "1000.00")
        invest(self.k, ins_id="I0", account="ACC-1", amount="100000", day=1)
        self.k.close_day(on(1), actor="ops_manager", at=at(1, 19))
        price(self.k, 5, "1050.00")
        self.ins = self.k.receive_instruction(id="R1", account="ACC-1", class_id=CLASS, fund=FUND, kind="redeem",
                                              received_at=at(5, 10), dealing_date=on(5), units=D("10000"))
        self.k.lock_units(instruction_id="R1", at=at(5, 10), actor="dealing_clerk")

    def test_price_rose_fund_pays_more_owner_keeps_surplus(self):
        deal, payable, record = self.k.backdate_redemption(
            instruction_id="R1", historical_date=on(1), reason="manco_error", evidence=["fax:2026-09-01T11:00"],
            maker="ops_clerk", approvals=approvals("ops_manager", "finance_manager"), at=at(6, 11),
        )
        self.assertEqual(deal.investor_amount, D("100000.00"))
        self.assertEqual(deal.fund_amount, D("105000.00"))
        self.assertEqual(payable.amount, D("100000.00"))
        self.assertEqual(record.delta, D("-5000.00"))
        self.assertEqual(self.k.ledger.credit_balance("MANCO_ERROR_ACCOUNT"), D("5000.00"))
        self.assertEqual(self.k.ledger.balance("REDEMPTIONS_DUE_FROM_FUND:EXB"), D("105000.00"))
        self.assertEqual(self.k.register.units("ACC-1", CLASS), D("0"))
        self.k.register.check(CLASS)

    def test_price_fell_owner_tops_up_the_investor(self):
        price(self.k, 6, "950.00", override="market fall confirmed by fund accounting")
        deal, payable, record = self.k.backdate_redemption(
            instruction_id="R1", historical_date=on(1), reason="manco_error", evidence=["fax:2026-09-01T11:00"],
            maker="ops_clerk", approvals=approvals("ops_manager", "finance_manager"), at=at(7, 11),
        )
        self.assertEqual(deal.fund_amount, D("95000.00"))
        self.assertEqual(payable.amount, D("100000.00"))
        self.assertEqual(record.delta, D("5000.00"))
        self.assertEqual(self.k.ledger.balance("MANCO_ERROR_ACCOUNT"), D("5000.00"))


class UnpaidCollection(unittest.TestCase):
    def setUp(self):
        self.k = kernel(exposure_limit=D("50000"))
        price(self.k, 1, "1000.00")
        self.ins = self.k.receive_instruction(id="DO-1", account="ACC-9", class_id=CLASS, fund=FUND, kind="invest",
                                              received_at=at(1, 8), dealing_date=on(1), amount=D("1000"))
        self.k.fund_on_exposure(instruction_id="DO-1", at=at(1, 8), actor="collections")
        self.deal = self.k.price_investment(instruction_id="DO-1", at=at(1, 18), actor="dealing_clerk")

    def test_units_exist_against_exposure(self):
        self.assertEqual(self.deal.units, D("100.0000"))
        self.assertEqual(self.k.ledger.balance("SETTLEMENT_EXPOSURE:EXB"), D("1000"))

    def test_price_fell_manco_bears_the_loss(self):
        price(self.k, 6, "980.00")
        record = self.k.reverse_unpaid_collection(deal_id=self.deal.id, reason="unpaid_collection", at=at(6, 18), actor="collections")
        self.assertEqual(record.delta, D("20.00"))
        self.assertEqual(self.k.ledger.balance("MANCO_ERROR_ACCOUNT"), D("20.00"))
        self.assertEqual(self.k.ledger.balance("SETTLEMENT_EXPOSURE:EXB"), D("0"))
        self.assertEqual(self.k.register.units("ACC-9", CLASS), D("0"))
        self.assertEqual(self.k.register.units_in_issue(CLASS), D("0"))
        # The fund keeps the R20 it was owed: it gets R1 000 for units now worth R980. Neutral NAV.
        self.assertEqual(self.k.ledger.credit_balance("SUBS_PAYABLE_TO_FUND:EXB"), D("20.00"))
        self.k.register.check(CLASS)

    def test_price_rose_manco_keeps_the_gain(self):
        price(self.k, 6, "1020.00")
        record = self.k.reverse_unpaid_collection(deal_id=self.deal.id, reason="unpaid_collection", at=at(6, 18), actor="collections")
        self.assertEqual(record.delta, D("-20.00"))
        self.assertEqual(self.k.ledger.credit_balance("MANCO_ERROR_ACCOUNT"), D("20.00"))
        self.assertEqual(self.k.ledger.balance("SUBS_PAYABLE_TO_FUND:EXB"), D("20.00"))

    def test_cleared_exposure_cannot_be_reversed_as_unpaid(self):
        line = self.k.receive_cash(bank_account="TRUST-1", fund=FUND, amount=D("1000"), reference="DO-1", at=at(3, 9), actor="bank_feed")
        self.k.clear_exposure(instruction_id="DO-1", bank_line_id=line.id, at=at(3, 9), actor="cash_clerk")
        self.assertEqual(self.k.ledger.balance("SETTLEMENT_EXPOSURE:EXB"), D("0"))
        with self.assertRaises(BlockError):
            self.k.reverse_unpaid_collection(deal_id=self.deal.id, reason="unpaid_collection", at=at(6, 12), actor="collections")


if __name__ == "__main__":
    unittest.main()
