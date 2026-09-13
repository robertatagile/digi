import unittest
from datetime import date

from _fixtures import CLASS, D, FUND, approvals, at, invest, kernel, on, price
from digi_kernel import ControlError, LegislationLibrary, Obligation, ObligationRegister


def fica_cdd():
    return Obligation("FICA-CDD", "FICA", "s21", "Customer due diligence before a business relationship or transaction", "gate", ("manco", "lisp"), "FICA s21")


def fica_records():
    return Obligation("FICA-RECORDS", "FICA", "s22", "Keep records for five years", "record", ("manco", "lisp"), "FICA s22")


def fais_licence():
    return Obligation("FAIS-ADVISER-LICENCE", "FAIS", "s7, s13", "Only licensed FSPs and representatives", "gate", ("manco", "lisp"), "FAIS s7")


def reg28():
    return Obligation("PFA-REGULATION-28", "PFA", "Reg 28", "Asset allocation limits for retirement funds", "limit", ("lisp",), "PFA Regulation 28")


def cofi_tcf():
    return Obligation("COFI-TCF-OUTCOMES", "COFI", "Bill", "Treating customers fairly outcomes", "attestation", ("manco", "lisp"), "COFI Bill")


def library():
    lib = LegislationLibrary()
    lib.publish(legislation="FICA", effective_from=date(2003, 6, 30), status="in_force", obligations=[fica_cdd(), fica_records()],
                source="Act 38 of 2001", maker="reg_analyst", approvals=approvals("reg_lead", "reg_counsel"))
    lib.publish(legislation="FAIS", effective_from=date(2004, 9, 30), status="in_force", obligations=[fais_licence()],
                source="Act 37 of 2002", maker="reg_analyst", approvals=approvals("reg_lead", "reg_counsel"))
    lib.publish(legislation="PFA", effective_from=date(2011, 7, 1), status="in_force", obligations=[reg28()],
                source="Regulation 28", maker="reg_analyst", approvals=approvals("reg_lead", "reg_counsel"))
    lib.publish(legislation="COFI", effective_from=date(2027, 7, 1), status="pending", obligations=[cofi_tcf()],
                source="COFI Bill", maker="reg_analyst", approvals=approvals("reg_lead", "reg_counsel"))
    return lib


class LibraryIsControlled(unittest.TestCase):
    def test_a_version_needs_two_approvers_and_a_source(self):
        lib = LegislationLibrary()
        with self.assertRaises(ControlError):
            lib.publish(legislation="FICA", effective_from=date(2003, 6, 30), status="in_force", obligations=[fica_cdd()],
                        source="Act 38 of 2001", maker="reg_analyst", approvals=approvals("reg_lead"))
        with self.assertRaises(ControlError):
            lib.publish(legislation="FICA", effective_from=date(2003, 6, 30), status="in_force", obligations=[fica_cdd()],
                        source="Act 38 of 2001", maker="reg_analyst", approvals=approvals("reg_analyst", "reg_lead"))
        with self.assertRaises(ControlError):
            lib.publish(legislation="FICA", effective_from=date(2003, 6, 30), status="in_force", obligations=[fica_cdd()],
                        source="", maker="reg_analyst", approvals=approvals("reg_lead", "reg_counsel"))

    def test_versions_append_and_are_effective_dated(self):
        lib = library()
        # An amendment adds an obligation from a future date. The old version still answers for earlier dates.
        edd = Obligation("FICA-EDD", "FICA", "s21C", "Enhanced due diligence for prominent persons", "gate", ("manco", "lisp"), "FIC Amendment Act")
        lib.publish(legislation="FICA", effective_from=date(2027, 4, 1), status="in_force", obligations=[fica_cdd(), fica_records(), edd],
                    source="Amendment Gazette", maker="reg_analyst", approvals=approvals("reg_lead", "reg_counsel"))
        self.assertEqual([v.version for v in lib.versions("FICA")], [1, 2])
        self.assertEqual(lib.current("FICA", as_at=date(2026, 10, 1)).version, 1)
        self.assertEqual(lib.current("FICA", as_at=date(2027, 4, 1)).version, 2)
        ids_now = {o.id for o in lib.applicable(tenant_type="manco", as_at=date(2026, 10, 1))}
        self.assertNotIn("FICA-EDD", ids_now)
        pending = {o.id for o, _ in lib.pending(tenant_type="manco", as_at=date(2026, 10, 1))}
        self.assertIn("FICA-EDD", pending)

    def test_obligation_needs_a_source_and_a_known_type(self):
        with self.assertRaises(ControlError):
            Obligation("X", "FICA", "s1", "…", "gate", ("manco",), "")
        with self.assertRaises(ControlError):
            Obligation("X", "FICA", "s1", "…", "wish", ("manco",), "FICA")


class TenantRegister(unittest.TestCase):
    def setUp(self):
        self.lib = library()
        self.reg = ObligationRegister("example-manco", "manco")

    def test_applicability_follows_tenant_type(self):
        ids = {o.id for o in self.lib.applicable(tenant_type="manco", as_at=date(2026, 10, 1))}
        self.assertEqual(ids, {"FICA-CDD", "FICA-RECORDS", "FAIS-ADVISER-LICENCE"})
        lisp_ids = {o.id for o in self.lib.applicable(tenant_type="lisp", as_at=date(2026, 10, 1))}
        self.assertIn("PFA-REGULATION-28", lisp_ids)

    def test_cofi_is_visible_as_pending_not_required(self):
        report = self.reg.coverage(self.lib, as_at=date(2026, 10, 1))
        self.assertIn(("COFI-TCF-OUTCOMES", date(2027, 7, 1)), report.pending)
        self.assertNotIn("COFI-TCF-OUTCOMES", report.gaps)

    def test_unbound_obligation_blocks_release(self):
        self.reg.bind(obligation_id="FICA-CDD", owner_role="mlro", implementations=["kernel:gates.kyc_current_on_payment"])
        with self.assertRaises(ControlError) as ctx:
            self.reg.release_gate(self.lib, as_at=date(2026, 10, 1))
        self.assertIn("FICA-RECORDS", str(ctx.exception))
        self.assertIn("FAIS-ADVISER-LICENCE", str(ctx.exception))

    def test_bindings_and_justified_exclusions_complete_coverage(self):
        self.reg.bind(obligation_id="FICA-CDD", owner_role="mlro", implementations=["kernel:gates.kyc_current_on_payment", "pack:workflows/redemption.yaml"])
        self.reg.bind(obligation_id="FICA-RECORDS", owner_role="mlro", implementations=["kernel:ledger.immutable_events"])
        self.reg.bind(obligation_id="FAIS-ADVISER-LICENCE", owner_role="key_individual", implementations=["kernel:gates.adviser_licence_on_fee_release"])
        report = self.reg.release_gate(self.lib, as_at=date(2026, 10, 1))
        self.assertTrue(report.complete)
        self.assertEqual(set(report.covered), {"FICA-CDD", "FICA-RECORDS", "FAIS-ADVISER-LICENCE"})

    def test_not_applicable_needs_a_reason_and_two_approvers(self):
        lisp = ObligationRegister("example-lisp", "lisp")
        with self.assertRaises(ControlError):
            lisp.exclude(obligation_id="PFA-REGULATION-28", reason="  ", maker="compliance_officer", approvals=approvals("head_of_compliance", "key_individual"))
        with self.assertRaises(ControlError):
            lisp.exclude(obligation_id="PFA-REGULATION-28", reason="No retirement products", maker="compliance_officer", approvals=approvals("head_of_compliance"))
        b = lisp.exclude(obligation_id="PFA-REGULATION-28", reason="No retirement products", maker="compliance_officer", approvals=approvals("head_of_compliance", "key_individual"))
        self.assertTrue(b.is_exclusion)
        report = lisp.coverage(self.lib, as_at=date(2026, 10, 1))
        self.assertIn("PFA-REGULATION-28", report.excluded)
        self.assertNotIn("PFA-REGULATION-28", report.gaps)

    def test_a_binding_needs_a_real_implementation(self):
        with self.assertRaises(ControlError):
            self.reg.bind(obligation_id="FICA-CDD", owner_role="mlro", implementations=[])
        with self.assertRaises(ControlError):
            self.reg.bind(obligation_id="FICA-CDD", owner_role="mlro", implementations=["hope:someone checks"])


class KernelGatesNameTheLaw(unittest.TestCase):
    def setUp(self):
        self.k = kernel()
        price(self.k, 1, "1000.00")
        invest(self.k, ins_id="I1", account="ACC-1", amount="100000", day=1)
        price(self.k, 2, "1010.00")
        self.k.receive_instruction(id="R1", account="ACC-1", class_id=CLASS, fund=FUND, kind="redeem",
                                   received_at=at(2, 10), dealing_date=on(2), units=D("1000"))
        self.k.lock_units(instruction_id="R1", at=at(2, 10), actor="dealing_clerk")
        _, self.payable = self.k.price_redemption(instruction_id="R1", at=at(2, 18), actor="dealing_clerk")

    def test_expired_fica_blocks_the_payment_and_names_the_obligation(self):
        self.k.set_kyc_status(account="ACC-1", status="expired", actor="fica_officer", at=at(3, 8))
        with self.assertRaises(ControlError) as ctx:
            self.k.instruct_payment(payable_id=self.payable.id, maker="payments_clerk", approvals=approvals("checker"), at=at(3, 9))
        self.assertIn("Blocked by FICA-CDD", str(ctx.exception))
        self.assertEqual(self.payable.status, "open")

    def test_unverified_account_cannot_deal(self):
        self.k.receive_instruction(id="I-new", account="ACC-UNKNOWN", class_id=CLASS, fund=FUND, kind="invest",
                                   received_at=at(2, 10), dealing_date=on(2), amount=D("5000"))
        line = self.k.receive_cash(bank_account="TRUST-1", fund=FUND, amount=D("5000"), reference="I-new", at=at(2, 9), actor="bank_feed")
        self.k.match_cash(instruction_id="I-new", bank_line_id=line.id, at=at(2, 10), actor="cash_clerk")
        with self.assertRaises(ControlError) as ctx:
            self.k.price_investment(instruction_id="I-new", at=at(2, 18), actor="dealing_clerk")
        self.assertIn("FICA-CDD", str(ctx.exception))
        self.assertEqual(self.k.register.units("ACC-UNKNOWN", CLASS), D("0"))

    def test_regulatory_trail_reads_the_tags_back(self):
        self.k.instruct_payment(payable_id=self.payable.id, maker="payments_clerk", approvals=approvals("checker"), at=at(3, 9))
        trail = self.k.regulatory_trail("FICA-CDD")
        self.assertEqual({j.command for j in trail}, {"PriceInvestment", "InstructPayment"})
        march_only = self.k.regulatory_trail("FICA-CDD", since=at(3, 0), until=at(3, 23))
        self.assertEqual([j.command for j in march_only], ["InstructPayment"])
        forward_pricing = self.k.regulatory_trail("CISCA-FORWARD-PRICING")
        self.assertEqual([j.command for j in forward_pricing], ["PriceInvestment"])


if __name__ == "__main__":
    unittest.main()
