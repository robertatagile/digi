import unittest
from datetime import date, datetime
from decimal import Decimal

from _fixtures import D  # noqa: F401  (sets up sys.path)
from digi_kernel import Journal, Ledger, LedgerError, Posting, cr, dr


def journal(id, postings, *, effective=date(2026, 9, 1), posted=datetime(2026, 9, 1, 12), actor="clerk", pack="2026.10.0"):
    return Journal(id=id, effective_date=effective, posted_at=posted, postings=tuple(postings), actor=actor, command="Test", pack_version=pack)


class LedgerInvariants(unittest.TestCase):
    def test_balanced_money_journal_posts(self):
        ledger = Ledger()
        ledger.post(journal("J1", [dr("BANK:T", "money", "ZAR", D("100")), cr("UNALLOCATED_CASH:F", "money", "ZAR", D("100"))]))
        self.assertEqual(ledger.balance("BANK:T"), D("100"))
        self.assertEqual(ledger.credit_balance("UNALLOCATED_CASH:F"), D("100"))

    def test_unbalanced_money_is_rejected(self):
        ledger = Ledger()
        with self.assertRaises(LedgerError):
            ledger.post(journal("J1", [dr("BANK:T", "money", "ZAR", D("100")), cr("UNALLOCATED_CASH:F", "money", "ZAR", D("99"))]))

    def test_units_balance_separately_from_money(self):
        ledger = Ledger()
        with self.assertRaises(LedgerError):
            ledger.post(journal("J1", [
                dr("BANK:T", "money", "ZAR", D("100")), cr("SUBS_PAYABLE_TO_FUND:F", "money", "ZAR", D("100")),
                dr("UNITS_IN_ISSUE:C", "units", "C", D("10")), cr("HOLDING:A:C", "units", "C", D("9")),
            ]))

    def test_currencies_balance_separately(self):
        ledger = Ledger()
        with self.assertRaises(LedgerError):
            ledger.post(journal("J1", [dr("BANK:T", "money", "ZAR", D("100")), cr("BANK:U", "money", "USD", D("100"))]))

    def test_floats_are_refused(self):
        with self.assertRaises(LedgerError):
            Posting("BANK:T", "money", "ZAR", 100.0)  # type: ignore[arg-type]

    def test_zero_postings_are_refused(self):
        with self.assertRaises(LedgerError):
            Posting("BANK:T", "money", "ZAR", D("0"))

    def test_duplicate_journal_id_is_refused(self):
        ledger = Ledger()
        p = [dr("BANK:T", "money", "ZAR", D("1")), cr("X", "money", "ZAR", D("1"))]
        ledger.post(journal("J1", p))
        with self.assertRaises(LedgerError):
            ledger.post(journal("J1", p))

    def test_actor_and_pack_version_are_required(self):
        ledger = Ledger()
        p = [dr("BANK:T", "money", "ZAR", D("1")), cr("X", "money", "ZAR", D("1"))]
        with self.assertRaises(LedgerError):
            ledger.post(journal("J1", p, actor=""))
        with self.assertRaises(LedgerError):
            ledger.post(journal("J2", p, pack=""))

    def test_no_update_or_delete_exists(self):
        for name in ("update", "delete", "remove", "amend", "edit"):
            self.assertFalse(hasattr(Ledger, name), f"Ledger must not expose {name} (I5)")

    def test_reversal_negates_and_references_the_original(self):
        ledger = Ledger()
        ledger.post(journal("J1", [dr("BANK:T", "money", "ZAR", D("100")), cr("X", "money", "ZAR", D("100"))]))
        rev = ledger.reverse("J1", new_id="J2", posted_at=datetime(2026, 9, 2, 9), actor="supervisor", reason="duplicate receipt")
        self.assertEqual(rev.reverses, "J1")
        self.assertEqual(ledger.balance("BANK:T"), D("0"))
        self.assertEqual(len(ledger.journals()), 2)

    def test_reversal_needs_a_reason(self):
        ledger = Ledger()
        ledger.post(journal("J1", [dr("BANK:T", "money", "ZAR", D("100")), cr("X", "money", "ZAR", D("100"))]))
        with self.assertRaises(LedgerError):
            ledger.reverse("J1", new_id="J2", posted_at=datetime(2026, 9, 2), actor="supervisor", reason="")


class Bitemporal(unittest.TestCase):
    def test_balance_as_at_both_time_axes(self):
        ledger = Ledger()
        ledger.post(journal("J1", [dr("BANK:T", "money", "ZAR", D("100")), cr("X", "money", "ZAR", D("100"))],
                            effective=date(2026, 9, 1), posted=datetime(2026, 9, 1, 12)))
        # A backdated posting: effective 1 Sep, only known on 5 Sep.
        ledger.post(journal("J2", [dr("BANK:T", "money", "ZAR", D("50")), cr("X", "money", "ZAR", D("50"))],
                            effective=date(2026, 9, 1), posted=datetime(2026, 9, 5, 9)))
        as_reported = ledger.balance("BANK:T", effective_as_at=date(2026, 9, 1), knowledge_as_at=datetime(2026, 9, 2))
        as_corrected = ledger.balance("BANK:T", effective_as_at=date(2026, 9, 1))
        self.assertEqual(as_reported, D("100"))
        self.assertEqual(as_corrected, D("150"))
        self.assertEqual(ledger.balance("BANK:T", effective_as_at=date(2026, 8, 31)), D("0"))


if __name__ == "__main__":
    unittest.main()
