import unittest
from decimal import Decimal

from _fixtures import CLASS, D, FUND, at, invest, kernel, on, price
from digi_kernel import BlockError, ControlError

EXT = "OTH-A"      # a class issued by another manco
EXT_FUND = "OTH"


def external_investment(k, *, ins_id, account, amount, day):
    line = k.receive_cash(bank_account="TRUST-1", fund=EXT_FUND, amount=D(amount), reference=ins_id, at=at(day, 9), actor="bank_feed")
    k.receive_instruction(id=ins_id, account=account, class_id=EXT, fund=EXT_FUND, kind="invest",
                          received_at=at(day, 10), dealing_date=on(day), amount=D(amount))
    k.match_cash(instruction_id=ins_id, bank_line_id=line.id, at=at(day, 10, 5), actor="cash_clerk")


class OneAccountManyInstruments(unittest.TestCase):
    def setUp(self):
        self.k = kernel()
        self.k.register_instrument(class_id=CLASS, issuer="own")
        self.k.register_instrument(class_id=EXT, issuer="external")
        price(self.k, 1, "1000.00")
        invest(self.k, ins_id="I1", account="ACC-1", amount="100000", day=1)           # own fund, priced directly
        for i, account in enumerate(("ACC-1", "ACC-2", "ACC-3"), start=1):             # external fund, dealt in bulk
            external_investment(self.k, ins_id=f"E{i}", account=account, amount="10000", day=1)

    def test_external_instrument_cannot_be_priced_one_by_one(self):
        with self.assertRaises(BlockError) as ctx:
            self.k.price_investment(instruction_id="E1", at=at(1, 18), actor="dealing_clerk")
        self.assertIn("bulk", str(ctx.exception))

    def test_bulk_allocation_at_the_confirmed_price(self):
        bulk = self.k.submit_bulk(class_id=EXT, dealing_date=on(1), at=at(1, 13), actor="dealing_clerk")
        self.assertEqual(bulk.amount, D("30000"))
        self.assertEqual(self.k.ledger.credit_balance("SUBS_AWAITING_PRICING:OTH"), D("30000"))
        # The manco confirms 10 000.0000 units at 300.00 cpu for R30 000. Each investor gets 3 333.3333.
        p, deals = self.k.confirm_bulk(bulk_id=bulk.id, cpu=D("300.00"), units_confirmed=D("10000.0000"),
                                       confirmation_ref="FSW-2026-09-02-0001", at=at(2, 9), actor="dealing_clerk")
        self.assertEqual(p.cpu, D("300.00"))
        self.assertEqual(p.signed_by, ("dealing_clerk", "confirmation:FSW-2026-09-02-0001"))
        self.assertEqual([d.units for d in deals], [D("3333.3333")] * 3)
        self.assertEqual(self.k.register.units("ACC-2", EXT), D("3333.3333"))
        self.assertEqual(self.k.register.nominee_bulk(EXT), D("10000.0000"))
        self.assertEqual(self.k.ledger.credit_balance("ROUNDING_UNITS:OTH-A"), D("0.0001"))
        self.assertEqual(self.k.ledger.balance("SUBS_AWAITING_PRICING:OTH"), D("0"))
        self.assertEqual(self.k.ledger.credit_balance("SUBS_PAYABLE_TO_FUND:OTH"), D("30000"))
        self.k.register.check(EXT)
        self.k.register.check(CLASS)

    def test_same_statement_for_one_fund_or_many(self):
        bulk = self.k.submit_bulk(class_id=EXT, dealing_date=on(1), at=at(1, 13), actor="dealing_clerk")
        self.k.confirm_bulk(bulk_id=bulk.id, cpu=D("300.00"), units_confirmed=D("10000.0000"),
                            confirmation_ref="FSW-1", at=at(2, 9), actor="dealing_clerk")
        many = self.k.statement("ACC-1", [CLASS, EXT], effective_as_at=on(2))
        one = self.k.statement("ACC-2", [EXT], effective_as_at=on(2))
        self.assertEqual([line.amount for line in many.lines], [D("100000.00"), D("10000.00")])
        self.assertEqual(many.total, D("110000.00"))
        self.assertEqual(one.total, D("10000.00"))
        self.assertEqual({line.price.pricing_date for line in many.lines}, {on(1)})
        self.assertEqual(many.lines[1].price.signed_by[1], "confirmation:FSW-1")

    def test_allocation_break_posts_nothing(self):
        bulk = self.k.submit_bulk(class_id=EXT, dealing_date=on(1), at=at(1, 13), actor="dealing_clerk")
        before = len(self.k.ledger.journals())
        with self.assertRaises(ControlError) as ctx:
            self.k.confirm_bulk(bulk_id=bulk.id, cpu=D("300.00"), units_confirmed=D("10001.0000"),
                                confirmation_ref="FSW-2", at=at(2, 9), actor="dealing_clerk")
        self.assertIn("allocation break", str(ctx.exception))
        self.assertEqual(len(self.k.ledger.journals()), before)
        self.assertEqual(self.k.register.units("ACC-1", EXT), D("0"))
        self.assertEqual(bulk.status, "submitted")

    def test_a_confirmation_never_overwrites_a_published_price(self):
        bulk = self.k.submit_bulk(class_id=EXT, dealing_date=on(1), at=at(1, 13), actor="dealing_clerk")
        self.k.confirm_bulk(bulk_id=bulk.id, cpu=D("300.00"), units_confirmed=D("10000.0000"),
                            confirmation_ref="FSW-1", at=at(2, 9), actor="dealing_clerk")
        external_investment(self.k, ins_id="E4", account="ACC-4", amount="3000", day=1)
        late = self.k.submit_bulk(class_id=EXT, dealing_date=on(1), at=at(2, 10), actor="dealing_clerk")
        with self.assertRaises(BlockError) as ctx:
            self.k.confirm_bulk(bulk_id=late.id, cpu=D("301.00"), units_confirmed=D("996.6777"),
                                confirmation_ref="FSW-3", at=at(2, 11), actor="dealing_clerk")
        self.assertIn("never overwritten", str(ctx.exception))

    def test_unverified_account_stays_out_of_the_bulk_and_blocks_day_close(self):
        external_investment(self.k, ins_id="E9", account="ACC-NEW", amount="5000", day=1)
        bulk = self.k.submit_bulk(class_id=EXT, dealing_date=on(1), at=at(1, 13), actor="dealing_clerk")
        self.assertNotIn("E9", bulk.instruction_ids)
        self.assertEqual(bulk.excluded[0][0], "E9")
        self.assertIn("FICA-CDD", bulk.excluded[0][1])
        self.k.confirm_bulk(bulk_id=bulk.id, cpu=D("300.00"), units_confirmed=D("10000.0000"),
                            confirmation_ref="FSW-1", at=at(2, 9), actor="dealing_clerk")
        with self.assertRaises(ControlError) as ctx:
            self.k.close_day(on(1), actor="ops_manager", at=at(2, 19))
        self.assertIn("E9", str(ctx.exception))

    def test_own_instrument_cannot_be_submitted_in_bulk(self):
        with self.assertRaises(BlockError):
            self.k.submit_bulk(class_id=CLASS, dealing_date=on(1), at=at(1, 13), actor="dealing_clerk")


if __name__ == "__main__":
    unittest.main()
