import unittest
from decimal import Decimal

from _fixtures import CLASS, D, FUND, approvals, at, invest, kernel, on, price
from digi_kernel import BlockError, ControlError, DayClose


class Investment(unittest.TestCase):
    def test_full_chain_clears_every_control_account(self):
        k = kernel()
        price(k, 1, "1000.00")
        deal = invest(k, ins_id="I1", account="ACC-1", amount="100000", day=1)
        self.assertEqual(deal.units, D("10000.0000"))
        self.assertEqual(k.ledger.balance("UNALLOCATED_CASH:EXB"), D("0"))
        self.assertEqual(k.ledger.balance("SUBS_AWAITING_PRICING:EXB"), D("0"))
        self.assertEqual(k.ledger.credit_balance("SUBS_PAYABLE_TO_FUND:EXB"), D("100000"))
        self.assertEqual(k.ledger.balance("BANK:TRUST-1"), D("100000"))
        self.assertEqual(k.register.units_in_issue(CLASS), D("10000.0000"))

    def test_initial_fee_reduces_units_and_creates_a_payable(self):
        k = kernel()
        price(k, 1, "1000.00")
        ins = invest(k, ins_id="I1", account="ACC-1", amount="100000", day=1, price_it=False)
        deal = k.price_investment(instruction_id=ins.id, at=at(1, 18), actor="dealing_clerk", initial_fee=D("2000"))
        self.assertEqual(deal.units, D("9800.0000"))
        self.assertEqual(k.ledger.credit_balance("FEES_PAYABLE:adviser"), D("2000"))
        self.assertEqual(k.ledger.credit_balance("SUBS_PAYABLE_TO_FUND:EXB"), D("98000"))

    def test_no_units_without_cash_or_exposure(self):
        k = kernel()
        price(k, 1, "1000.00")
        ins = k.receive_instruction(id="I1", account="ACC-1", class_id=CLASS, fund=FUND, kind="invest",
                                    received_at=at(1, 10), dealing_date=on(1), amount=D("1000"))
        with self.assertRaises(BlockError):
            k.price_investment(instruction_id=ins.id, at=at(1, 18), actor="dealing_clerk")

    def test_no_units_without_a_published_price(self):
        k = kernel()
        with self.assertRaises(BlockError):
            invest(k, ins_id="I1", account="ACC-1", amount="1000", day=1)

    def test_forward_pricing_dealing_date_never_precedes_receipt(self):
        k = kernel()
        with self.assertRaises(BlockError):
            k.receive_instruction(id="I1", account="ACC-1", class_id=CLASS, fund=FUND, kind="invest",
                                  received_at=at(5, 10), dealing_date=on(4), amount=D("1000"))

    def test_mismatched_cash_stays_unallocated(self):
        k = kernel()
        line = k.receive_cash(bank_account="TRUST-1", fund=FUND, amount=D("999"), reference="I1", at=at(1, 9), actor="bank_feed")
        ins = k.receive_instruction(id="I1", account="ACC-1", class_id=CLASS, fund=FUND, kind="invest",
                                    received_at=at(1, 10), dealing_date=on(1), amount=D("1000"))
        with self.assertRaises(BlockError):
            k.match_cash(instruction_id=ins.id, bank_line_id=line.id, at=at(1, 10), actor="cash_clerk")
        self.assertEqual(k.ledger.credit_balance("UNALLOCATED_CASH:EXB"), D("999"))


class Exposure(unittest.TestCase):
    def test_no_limit_means_no_exposure(self):
        k = kernel()
        k.receive_instruction(id="DO-1", account="ACC-1", class_id=CLASS, fund=FUND, kind="invest",
                              received_at=at(1, 8), dealing_date=on(1), amount=D("1000"))
        with self.assertRaises(ControlError):
            k.fund_on_exposure(instruction_id="DO-1", at=at(1, 8), actor="collections")

    def test_limit_is_enforced_cumulatively(self):
        k = kernel(exposure_limit=D("1500"))
        for i, amount in enumerate(("1000", "600")):
            k.receive_instruction(id=f"DO-{i}", account="ACC-1", class_id=CLASS, fund=FUND, kind="invest",
                                  received_at=at(1, 8), dealing_date=on(1), amount=D(amount))
        k.fund_on_exposure(instruction_id="DO-0", at=at(1, 8), actor="collections")
        with self.assertRaises(ControlError):
            k.fund_on_exposure(instruction_id="DO-1", at=at(1, 8), actor="collections")


class RedemptionAndPayment(unittest.TestCase):
    def setUp(self):
        self.k = kernel()
        price(self.k, 1, "1000.00")
        invest(self.k, ins_id="I1", account="ACC-1", amount="100000", day=1)
        price(self.k, 2, "1010.00")

    def redeem(self, units="4000", tax="0"):
        self.k.receive_instruction(id="R1", account="ACC-1", class_id=CLASS, fund=FUND, kind="redeem",
                                   received_at=at(2, 10), dealing_date=on(2), units=D(units))
        self.k.lock_units(instruction_id="R1", at=at(2, 10), actor="dealing_clerk")
        return self.k.price_redemption(instruction_id="R1", at=at(2, 18), actor="dealing_clerk", tax_withheld=D(tax))

    def test_more_than_available_is_refused(self):
        self.k.receive_instruction(id="R1", account="ACC-1", class_id=CLASS, fund=FUND, kind="redeem",
                                   received_at=at(2, 10), dealing_date=on(2), units=D("10001"))
        with self.assertRaises(BlockError):
            self.k.lock_units(instruction_id="R1", at=at(2, 10), actor="dealing_clerk")

    def test_locked_units_are_held_but_not_available(self):
        self.k.receive_instruction(id="R1", account="ACC-1", class_id=CLASS, fund=FUND, kind="redeem",
                                   received_at=at(2, 10), dealing_date=on(2), units=D("4000"))
        self.k.lock_units(instruction_id="R1", at=at(2, 10), actor="dealing_clerk")
        self.assertEqual(self.k.register.units("ACC-1", CLASS), D("10000.0000"))
        self.assertEqual(self.k.register.available_units("ACC-1", CLASS), D("6000.0000"))
        self.k.register.check(CLASS)

    def test_pricing_cancels_units_and_creates_a_payable(self):
        deal, payable = self.redeem(tax="400")
        self.assertEqual(deal.investor_amount, D("40400.00"))
        self.assertEqual(payable.amount, D("40000.00"))
        self.assertEqual(self.k.ledger.credit_balance("TAX_WITHHELD_PAYABLE"), D("400"))
        self.assertEqual(self.k.register.units("ACC-1", CLASS), D("6000.0000"))
        self.assertEqual(self.k.register.units_in_issue(CLASS), D("6000.0000"))

    def test_payment_needs_a_payable_and_a_checker(self):
        _, payable = self.redeem()
        with self.assertRaises(BlockError):
            self.k.instruct_payment(payable_id="P-nope", maker="payments_clerk", approvals=approvals("checker"), at=at(3, 9))
        with self.assertRaises(ControlError):
            self.k.instruct_payment(payable_id=payable.id, maker="payments_clerk", approvals=[], at=at(3, 9))
        with self.assertRaises(ControlError):
            self.k.instruct_payment(payable_id=payable.id, maker="payments_clerk", approvals=approvals("payments_clerk"), at=at(3, 9))
        self.assertEqual(payable.status, "open")

    def test_payment_chain_and_no_double_payment(self):
        deal, payable = self.redeem()
        self.k.fund_settles_redemption(deal_id=deal.id, bank_account="TRUST-1", at=at(3, 9), actor="finance")
        self.k.instruct_payment(payable_id=payable.id, maker="payments_clerk", approvals=approvals("checker"), at=at(3, 10))
        self.assertEqual(self.k.ledger.credit_balance("PAYMENTS_IN_TRANSIT:EXB"), D("40400.00"))
        with self.assertRaises(BlockError):
            self.k.instruct_payment(payable_id=payable.id, maker="payments_clerk", approvals=approvals("checker"), at=at(3, 10))
        self.k.confirm_payment(payable_id=payable.id, bank_account="TRUST-1", at=at(3, 15), actor="bank_feed")
        self.assertEqual(self.k.ledger.balance("PAYMENTS_IN_TRANSIT:EXB"), D("0"))
        self.assertEqual(self.k.ledger.balance("REDEMPTIONS_PAYABLE:EXB"), D("0"))
        self.assertEqual(self.k.ledger.balance("REDEMPTIONS_DUE_FROM_FUND:EXB"), D("0"))
        self.assertEqual(self.k.ledger.balance("BANK:TRUST-1"), D("100000"))

    def test_returned_payment_goes_back_to_the_payable(self):
        _, payable = self.redeem()
        self.k.instruct_payment(payable_id=payable.id, maker="payments_clerk", approvals=approvals("checker"), at=at(3, 10))
        self.k.return_payment(payable_id=payable.id, at=at(3, 16), actor="bank_feed", reason="account closed")
        self.assertEqual(payable.status, "open")
        self.assertEqual(self.k.ledger.credit_balance("REDEMPTIONS_PAYABLE:EXB"), D("40400.00"))


class PriceCorrection(unittest.TestCase):
    def setUp(self):
        self.k = kernel()
        price(self.k, 1, "1000.00")
        invest(self.k, ins_id="I0", account="SELLER", amount="50000", day=1)
        price(self.k, 2, "1000.00")
        self.buy = invest(self.k, ins_id="I1", account="BUYER", amount="100000", day=2)
        self.k.receive_instruction(id="R1", account="SELLER", class_id=CLASS, fund=FUND, kind="redeem",
                                   received_at=at(2, 10), dealing_date=on(2), units=D("1000"))
        self.k.lock_units(instruction_id="R1", at=at(2, 10), actor="dealing_clerk")
        self.sell, self.sell_payable = self.k.price_redemption(instruction_id="R1", at=at(2, 18), actor="dealing_clerk")

    def test_material_error_reprices_deals_from_the_error_account(self):
        record = self.k.correct_price(class_id=CLASS, pricing_date=on(2), new_cpu=D("1007.00"),
                                      signed_by=("pricing_1", "pricing_2"), at=at(3, 9), actor="pricing_1")
        self.assertTrue(record.material)
        self.assertEqual([p.version for p in self.k.prices.versions(CLASS, on(2))], [1, 2])
        self.assertEqual(self.k.prices.official_at(CLASS, on(2), knowledge_as_at=at(2, 23)).cpu, D("1000.00"))
        # Buyer got too many units. The excess is cancelled. No money moves.
        self.assertEqual(self.k.register.units("BUYER", CLASS), D("9930.4866"))
        # Seller was underpaid. The manco pays the R70 shortfall.
        self.assertEqual(self.k.ledger.balance("MANCO_ERROR_ACCOUNT"), D("70.00"))
        top_up = [p for p in self.k.payables.values() if p.account == "SELLER" and p.amount == D("70.00")]
        self.assertEqual(len(top_up), 1)
        self.assertEqual({a[0] for a in record.adjustments}, {self.buy.id, self.sell.id})
        self.k.register.check(CLASS)

    def test_below_materiality_is_versioned_but_not_repriced(self):
        record = self.k.correct_price(class_id=CLASS, pricing_date=on(2), new_cpu=D("1003.00"),
                                      signed_by=("pricing_1", "pricing_2"), at=at(3, 9), actor="pricing_1")
        self.assertFalse(record.material)
        self.assertEqual(record.adjustments, ())
        self.assertEqual(self.k.prices.official_at(CLASS, on(2)).cpu, D("1003.00"))
        self.assertEqual(self.k.register.units("BUYER", CLASS), D("10000.0000"))

    def test_correction_needs_four_eyes(self):
        from digi_kernel import PriceError
        with self.assertRaises(PriceError):
            self.k.correct_price(class_id=CLASS, pricing_date=on(2), new_cpu=D("1007.00"),
                                 signed_by=("pricing_1",), at=at(3, 9), actor="pricing_1")


class DayCloseGates(unittest.TestCase):
    def test_unpriced_instruction_blocks_close(self):
        k = kernel()
        price(k, 1, "1000.00")
        invest(k, ins_id="I1", account="ACC-1", amount="1000", day=1, price_it=False)
        with self.assertRaises(ControlError) as ctx:
            k.close_day(on(1), actor="ops_manager", at=at(1, 19))
        self.assertIn("unpriced", str(ctx.exception))
        self.assertFalse(k.day_close.is_closed(on(1)))

    def test_unallocated_cash_blocks_close(self):
        k = kernel()
        k.receive_cash(bank_account="TRUST-1", fund=FUND, amount=D("500"), reference="?", at=at(1, 9), actor="bank_feed")
        with self.assertRaises(ControlError) as ctx:
            k.close_day(on(1), actor="ops_manager", at=at(1, 19))
        self.assertIn("unallocated", str(ctx.exception))

    def test_clean_day_closes_and_stays_closed(self):
        k = kernel()
        price(k, 1, "1000.00")
        invest(k, ins_id="I1", account="ACC-1", amount="1000", day=1)
        report = k.close_day(on(1), actor="ops_manager", at=at(1, 19))
        self.assertEqual(report["closed_by"], "ops_manager")
        self.assertTrue(k.day_close.is_closed(on(1)))
        for name in ("reopen", "open", "unlock"):
            self.assertFalse(hasattr(DayClose, name), f"DayClose must not expose {name} (I11)")


if __name__ == "__main__":
    unittest.main()
