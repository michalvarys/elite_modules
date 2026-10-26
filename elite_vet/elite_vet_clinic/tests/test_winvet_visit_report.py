"""Task 28: "Zpráva z vyšetření" for a visit imported from WinVet (elite.vet.visit)."""
from datetime import date

from odoo.tests import tagged

from .common import BASE, ClinicCase

REPORT = "elite_vet_clinic.report_winvet_visit_document"


@tagged("post_install", "-at_install")
class TestWinvetVisitReport(ClinicCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.doctor.kvl_number = "KVL-4711"
        cls.pet.write({"winvet_note": "WINVETPOZNAMKAINTERNI", "important_note": "DULEZITEINTERNI",
                       "next_vaccination": date(2027, 3, 14)})
        cls.env["elite.vet.pet.alert"].create({"pet_id": cls.pet.id, "kind": "allergy", "note": "ALERTPENICILIN"})
        cls.wv_doctor = cls.env["elite.vet.winvet.user"].create({
            "winvet_ref": BASE + 801, "name": "Ordinační-Testová Zdeňka", "doctor_id": cls.doctor.id})
        cls.wv_nurse = cls.env["elite.vet.winvet.user"].create({"winvet_ref": BASE + 802, "name": "Sestra Bez Vazby"})
        Visit = cls.env["elite.vet.visit"]
        cls.visit = Visit.create({
            "winvet_ref": BASE + 810, "pet_id": cls.pet.id, "date": date(2026, 9, 21), "time": "16:52:53",
            "case_name": "Kulhání", "diagnosis_name": "Distorze karpu", "entered_by_id": cls.wv_doctor.id,
            "notes": "Anamnéza:\nKulhá od včerejška.\n\nKlinické vyšetření:\nBolestivost karpu vlevo.",
        })
        cls.env["elite.vet.visit.vital"].create([
            {"winvet_ref": BASE + 820, "visit_id": cls.visit.id, "time": "16:55:00", "temperature": 38.6, "weight": 15.4},
            {"winvet_ref": BASE + 821, "visit_id": cls.visit.id, "time": "17:20:00", "heart_rate": 96,
             "bp_systolic": 120, "bp_diastolic": 80},
        ])
        document = cls.env["elite.vet.sale.document"].create({
            "winvet_ref": BASE + 830, "doc_type": "UM", "number": "UM-T34", "partner_id": cls.owner.id,
            "date": date(2026, 9, 21), "total": 12345.0})
        Line = cls.env["elite.vet.sale.line"]
        for n, (name, qty, unit, price) in enumerate((
                ("Klinické vyšetření WinVet T34", 1, "ks", 4567.0),
                ("Meloxicam WinVet T34", 1.5, "ml", 89.5),
                ("Převod nedoplatku z 2026000999", 1, "měna", 7654.0))):
            Line.create({"winvet_ref": BASE + 840 + n, "document_id": document.id, "visit_id": cls.visit.id,
                         "item_name": name, "quantity": qty, "unit": unit, "unit_price": price,
                         "amount": price * qty, "date": date(2026, 9, 21)})
        cls.bare = Visit.create({"winvet_ref": BASE + 811, "pet_id": cls.pet.id, "date": date(2026, 9, 2),
                                 "entered_by_id": cls.wv_nurse.id})
        cls.text_only = Visit.create({"winvet_ref": BASE + 812, "pet_id": cls.pet.id, "date": date(2026, 9, 5),
                                      "time": "09:01:00", "entered_by_id": cls.wv_nurse.id,
                                      "notes": "Kontrola po operaci, hojí se dobře."})

    def render(self, records, user=None):
        Report = self.env["ir.actions.report"]
        if user:
            Report = Report.with_user(user)
        html, _kind = Report._render_qweb_html(REPORT, records.ids)
        return html.decode() if isinstance(html, bytes) else html

    def test_report_contains_the_visit(self):
        html = self.render(self.visit)
        for text in ("Zpráva z vyšetření", "Azor Klinický", "bígl", "Majitelka Klinická-Testová", "777 654 321",
                     "21. 9. 2026", "16:52", "Ošetřující lékař/ka:", "MVDr. Zdeňka Ordinační-Testová",
                     "č. KVL KVL-4711", "Podpis a razítko lékaře/ky", "Záznam z vyšetření", "Kulhá od včerejška.",
                     "Bolestivost karpu vlevo.", "16:55 · teplota 38,6 °C · hmotnost 15,4 kg",
                     "17:20 · tep 96/min · TK 120/80", "Diagnóza", "Distorze karpu", "Případ: Kulhání",
                     "Provedené výkony a podané léky", "Klinické vyšetření WinVet T34", "Meloxicam WinVet T34",
                     "1,5 ml", "Příští vakcinace", "14. 3. 2027", "Místo a datum"):
            self.assertIn(text, html)
        self.assertRegex(html, r"Anamnéza:<br\s*/?>\s*Kulhá od včerejška\.")   # line breaks kept

    def test_no_prices_money_lines_or_internal_notes(self):
        html = self.render(self.visit)
        for text in ("4567", "4 567", "89,5", "7654", "12345", "Kč", "Cena", "Celkem", "Převod nedoplatku",
                     "WINVETPOZNAMKAINTERNI", "DULEZITEINTERNI", "ALERTPENICILIN", "Zapsal",
                     "majitelka.clinic@example.invalid", "Šarže", "Ordinační-Testová Zdeňka"):
            self.assertNotIn(text, html, text)

    def test_minimal_visits(self):
        """Without a linked doctor nobody is named as the treating doctor (the WinVet user who
        entered it may be a nurse); empty sections are left out."""
        html = self.render(self.text_only)
        self.assertIn("Kontrola po operaci, hojí se dobře.", html)
        for text in ("Ošetřující lékař", "Sestra Bez Vazby", "Diagnóza", "Provedené výkony", "teplota"):
            self.assertNotIn(text, html, text)
        self.assertFalse(self.bare._visit_report_has_content())
        self.assertTrue(self.text_only._visit_report_has_content())
        self.assertTrue(self.visit._visit_report_has_content())

    def test_rights_binding_and_file_name(self):
        report = self.env.ref("elite_vet_clinic.report_winvet_visit")
        self.assertEqual((report.model, report.report_name), ("elite.vet.visit", REPORT))
        for user in (self.reception, self.nurse, self.doctor_user, self.manager):
            html = self.render(self.visit, user=user)
            self.assertIn("Meloxicam WinVet T34", html, user.login)
            self.assertNotIn("4567", html, user.login)
            bindings = self.env["ir.actions.actions"].with_user(user).get_bindings("elite.vet.visit")
            self.assertIn(report.id, [a["id"] for a in bindings.get("report", [])], user.login)
        self.assertEqual(self.visit._visit_report_filename(), "Zprava_Azor_Klinicky_2026-09-21")
        pdf_html = self.render(self.visit | self.text_only)
        self.assertIn("Kulhá od včerejška.", pdf_html)
        self.assertIn("Kontrola po operaci", pdf_html)

    def test_card_timeline_marks_printable_visits(self):
        data = self.Record.with_user(self.doctor_user).card_data(self.pet.id)
        visits = {e["id"]: e for e in data["timeline"] if e["type"] == "visit"}
        self.assertTrue(visits[self.visit.id]["printable"])
        self.assertTrue(visits[self.text_only.id]["printable"])
        self.assertFalse(visits[self.bare.id]["printable"])
        from odoo.tools import file_open
        with file_open("elite_vet_clinic/static/src/patient_card/patient_card.js") as f:
            js = f.read()
        self.assertIn("report_winvet_visit_document", js)
