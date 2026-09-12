import unittest
from decimal import Decimal

from _fixtures import CLASS, D, SIGNERS, at, invest, kernel, on, price
from digi_kernel import Price, PriceError, value_holding


class CalculateDontStore(unittest.TestCase):
    def setUp(self):
        self.k = kernel()
        price(self.k, 1, "1000.00")
        self.deal = invest(self.k, ins_id="I1", account="ACC-1", amount="100000", day=1)

    def test_units_and_value_from_facts(self):
        self.assertEqual(self.deal.units, D("10000.0000"))
        v = value_holding(self.k.register, self.k.prices, "ACC-1", CLASS, effective_as_at=on(1))
        self.assertEqual(v.amount, D("100000.00"))
        self.assertEqual(v.price.version, 1)
        self.assertEqual(v.price_age_days, 0)
        self.assertFalse(v.stale)

    def test_new_price_changes_value_with_no_rerun(self):
        price(self.k, 2, "1050.00")
        v = value_holding(self.k.register, self.k.prices, "ACC-1", CLASS, effective_as_at=on(2))
        self.assertEqual(v.amount, D("105000.00"))
        self.assertEqual(v.price.pricing_date, on(2))

    def test_knowledge_time_view_uses_the_price_known_then(self):
        price(self.k, 2, "1050.00")  # published 2 Sep 17:00
        v = value_holding(self.k.register, self.k.prices, "ACC-1", CLASS, effective_as_at=on(2), knowledge_as_at=at(2, 9))
        self.assertEqual(v.price.pricing_date, on(1))
        self.assertEqual(v.amount, D("100000.00"))
        self.assertEqual(v.price_age_days, 1)

    def test_stale_price_is_shown_and_flagged(self):
        v = value_holding(self.k.register, self.k.prices, "ACC-1", CLASS, effective_as_at=on(10))
        self.assertTrue(v.stale)
        self.assertEqual(v.amount, D("100000.00"))
        self.assertEqual(v.price_age_days, 9)

    def test_no_price_means_no_amount_never_a_guess(self):
        v = value_holding(self.k.register, self.k.prices, "ACC-1", "OTHER", effective_as_at=on(1))
        self.assertIsNone(v.amount)
        self.assertEqual(v.basis, "no price")

    def test_indicative_policy_is_opt_in(self):
        self.k.prices.publish(Price(CLASS, on(2), 1, D("1100.00"), "indicative", at(2, 12), ("pricing_1",)))
        official = value_holding(self.k.register, self.k.prices, "ACC-1", CLASS, effective_as_at=on(2))
        indicative = value_holding(self.k.register, self.k.prices, "ACC-1", CLASS, effective_as_at=on(2), policy="indicative-latest")
        self.assertEqual(official.amount, D("100000.00"))
        self.assertEqual(indicative.amount, D("110000.00"))
        self.assertEqual(indicative.price.kind, "indicative")

    def test_account_view_carries_oldest_price_and_coverage(self):
        # A second class priced a day earlier than the first.
        self.k.publish_price(class_id="EXB-B", pricing_date=on(1), cpu=D("200.00"), at=at(1, 17), signed_by=SIGNERS)
        price(self.k, 2, "1000.00")
        line = self.k.receive_cash(bank_account="TRUST-1", fund="EXB", amount=D("10000"), reference="I2", at=at(1, 9), actor="bank_feed")
        ins = self.k.receive_instruction(id="I2", account="ACC-1", class_id="EXB-B", fund="EXB", kind="invest",
                                         received_at=at(1, 10), dealing_date=on(1), amount=D("10000"))
        self.k.match_cash(instruction_id="I2", bank_line_id=line.id, at=at(1, 10), actor="cash_clerk")
        self.k.price_investment(instruction_id="I2", at=at(1, 18), actor="dealing_clerk")
        s = self.k.statement("ACC-1", [CLASS, "EXB-B"], effective_as_at=on(3))
        self.assertEqual(s.total, D("110000.00"))
        self.assertEqual(s.oldest_price_date, on(1))
        # EXB-A priced 2 Sep (age 1) counts as fresh; EXB-B priced 1 Sep (age 2) does not.
        self.assertEqual(s.coverage, D("0.9091"))


class PriceFacts(unittest.TestCase):
    def test_official_price_needs_two_signers(self):
        k = kernel()
        with self.assertRaises(PriceError):
            k.publish_price(class_id=CLASS, pricing_date=on(1), cpu=D("1000"), at=at(1, 17), signed_by=("pricing_1", "pricing_1"))

    def test_prices_are_versioned_never_overwritten(self):
        k = kernel()
        price(k, 1, "1000.00")
        with self.assertRaises(PriceError):
            k.prices.publish(Price(CLASS, on(1), 1, D("1001.00"), "official", at(1, 18), SIGNERS))
        k.publish_price(class_id=CLASS, pricing_date=on(1), cpu=D("1001.00"), at=at(1, 18), signed_by=SIGNERS)
        self.assertEqual([p.version for p in k.prices.versions(CLASS, on(1))], [1, 2])
        self.assertEqual(k.prices.official_at(CLASS, on(1), knowledge_as_at=at(1, 17, 30)).cpu, D("1000.00"))
        self.assertEqual(k.prices.official_at(CLASS, on(1)).cpu, D("1001.00"))

    def test_movement_tolerance_needs_an_override(self):
        k = kernel()
        price(k, 1, "1000.00")
        with self.assertRaises(PriceError):
            price(k, 2, "1100.00")
        k.publish_price(class_id=CLASS, pricing_date=on(2), cpu=D("1100.00"), at=at(2, 17), signed_by=SIGNERS,
                        override_reason="corporate action confirmed by fund accounting")


if __name__ == "__main__":
    unittest.main()
