"""Task 27: the visit report for the owner ("Zpráva z vyšetření"). Rendered as HTML
(_render_qweb_html); the PDF binary itself is not needed in the tests."""
from datetime import date

from odoo.exceptions import AccessError
from odoo.tests import tagged

from odoo.addons.elite_vet_clinic.models.visit_report import age_long, file_part

from .common import ClinicCase

REPORT = "elite_vet_clinic.report_visit_document"


@tagged("post_install", "-at_install")
class TestVisitReport(ClinicCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.doctor.kvl_number = "KVL-4711"
        cls.owner.write({"street": "Lázeňská 12", "zip": "360 01", "city": "Karlovy Vary"})
        cls.pet.write({"color": "trikolóra", "tattoo": "TT-55", "passport": "CZ-PAS-0099",
                       "next_vaccination": date(2027, 3, 14), "next_deworming": date(2027, 1, 9)})
        cls.env["elite.vet.pet.alert"].create({"pet_id": cls.pet.id, "kind": "allergy", "note": "ALERTPENICILIN"})
        cls.full = cls.Record.create({
            "pet_id": cls.pet.id, "doctor_id": cls.doctor.id, "start": cls.today_utc(cls, 9, 30),
            "temperature": 38.6, "weight": 15.4, "heart_rate": 96, "respiratory_rate": 24,
            "anamnesis": "Kulhá na levou hrudní.\nOd včerejška.",
            "examination": "Bolestivost karpu vlevo.",
            "diagnosis": "Distorze karpu.\nKlidový režim 10 dní.",
            "reception_note": "RECEPCEINTERNI platí převodem",
            "room_note": "ORDINACEINTERNI objednat na kontrolu",
            "line_ids": [(0, 0, {"item_id": cls.exam.id, "quantity": 1, "price_unit": 777.0}),
                         (0, 0, {"item_id": cls.vaccine.id, "quantity": 0.5, "price_unit": 9876.0})],
        })

    def render(self, records, user=None):
        Report = self.env["ir.actions.report"]
        if user:
            Report = Report.with_user(user)
        html, _kind = Report._render_qweb_html(REPORT, records.ids)
        return html.decode() if isinstance(html, bytes) else html

    def report_bindings(self, user):
        """Ids of the Print menu entries of the record for the user."""
        bindings = self.env["ir.actions.actions"].with_user(user).get_bindings("elite.vet.clinical.record")
        return [action["id"] for action in bindings.get("report", [])]

    def test_full_report_contains_the_medical_texts(self):
        html = self.render(self.full)
        for text in ("Zpráva z vyšetření", "Azor Klinický", "Pes", "bígl", "trikolóra", "203 098 100 555 777",
                     "TT-55", "CZ-PAS-0099", "Majitelka Klinická-Testová", "Lázeňská 12, 360 01 Karlovy Vary",
                     "777 654 321", "Anamnéza", "Kulhá na levou hrudní.", "Od včerejška.",
                     "Klinické vyšetření", "teplota 38,6 °C", "hmotnost 15,4 kg", "tep 96/min", "dech 24/min",
                     "Bolestivost karpu vlevo.", "Diagnóza a doporučení", "Distorze karpu.", "Klidový režim 10 dní.",
                     "Provedené výkony a podané léky", "Klinické vyšetření testovací", "Vakcína testovací DHPPi",
                     "0,5 dávka", "Příští vakcinace", "14. 3. 2027", "Příští odčervení", "9. 1. 2027",
                     "MVDr. Zdeňka Ordinační-Testová", "č. KVL KVL-4711", "Ošetřující lékař/ka:", "Podpis a razítko lékaře/ky",
                     "Místo a datum", "09:30"):
            self.assertIn(text, html)
        self.assertRegex(html, r"Kulhá na levou hrudní\.<br\s*/?>\s*Od včerejška\.")   # line breaks kept
        self.assertIn('class="page"', html)     # page numbers in the footer
        self.assertIn('class="topage"', html)

    def test_never_internal_notes_alerts_or_prices(self):
        self.pet.write({"winvet_note": "WINVETINTERNI", "important_note": "DULEZITEINTERNI", "note": "POZNAMKAINTERNI"})
        html = self.render(self.full)
        for text in ("RECEPCEINTERNI", "ORDINACEINTERNI", "ALERTPENICILIN", "Alergie", "WINVETINTERNI",
                     "DULEZITEINTERNI", "POZNAMKAINTERNI", "777", "9876", "Kč", "Cena", "Celkem",
                     "majitelka.clinic@example.invalid", "Zapsal", "Rozepsaný"):
            if text == "777":
                # the owner's mobile "777 654 321" is printed, the price 777.0 is not
                self.assertNotIn("777,00", html)
                self.assertNotIn("777.0", html)
                continue
            self.assertNotIn(text, html, text)

    def test_minimal_report_omits_empty_sections(self):
        bare_pet = self.env["elite.vet.pet"].create({"name": "Mourek Holý", "partner_id": self.owner.id,
                                                     "species": "cat"})
        record = self.Record.create({"pet_id": bare_pet.id, "diagnosis": "Zdráv."})
        html = self.render(record)
        self.assertIn("Zdráv.", html)
        self.assertIn("Kočka", html)
        for text in ("Anamnéza", "Klinické vyšetření", "Provedené výkony", "Příští vakcinace", "Příští odčervení",
                     "Plemeno", "Čip", "Tetování", "Číslo pasu", "Barva", "Narozen", "Ošetřující lékař", "KVL",
                     "Exspirace", "Šarže"):
            self.assertNotIn(text, html, text)

    def test_vitals_only_show_examination_and_no_kvl_without_number(self):
        self.doctor.kvl_number = False
        record = self.Record.create({"pet_id": self.pet.id, "doctor_id": self.doctor.id, "weight": 4.25})
        html = self.render(record)
        self.assertIn("Klinické vyšetření", html)
        self.assertIn("hmotnost 4,25 kg", html)
        self.assertNotIn("teplota", html)
        self.assertIn("MVDr. Zdeňka Ordinační-Testová", html)
        self.assertNotIn("KVL", html)

    def test_doctor_title_from_the_team_card(self):
        section = self.env["elite.vet.team.section"].search([], limit=1) or self.env["elite.vet.team.section"].create(
            {"name": "Lékaři test"})
        member = self.env["elite.vet.team.member"].create({"name": "MVDr. Zdeňka Ordinační-Testová, Ph.D.",
                                                            "section_id": section.id})
        self.doctor.member_id = member
        self.assertIn("MVDr. Zdeňka Ordinační-Testová, Ph.D.", self.render(self.full))

    def test_clinic_header_from_company(self):
        self.env.company.write({"name": "Klinika Testovací s.r.o.", "street": "Hybešova 1", "zip": "360 05",
                                "city": "Karlovy Vary", "company_registry": "12345678", "vat": "CZ12345679",
                                "phone": "+420 700 000 001", "email": "klinika@example.invalid",
                                "website": "https://www.klinika.example"})
        html = self.render(self.full)
        for text in ("Klinika Testovací s.r.o.", "Hybešova 1", "360 05 Karlovy Vary", "IČO: 12345678",
                     "DIČ: CZ12345679", "+420 700 000 001", "klinika@example.invalid", "www.klinika.example",
                     "Místo a datum: Karlovy Vary"):
            self.assertIn(text, html)

    def test_several_records_and_filename(self):
        other = self.Record.create({"pet_id": self.pet.id, "anamnesis": "Druhá návštěva"})
        html = self.render(self.full | other)
        self.assertEqual(html.count("evr-title"), 2)
        self.assertEqual(self.full._visit_report_filename(), "Zprava_Azor_Klinicky_%s" % self.full.date.isoformat())
        self.assertEqual(file_part("Ťapka  Malá!"), "Tapka_Mala")

    def test_age_text(self):
        self.assertEqual(age_long(date(2023, 8, 1), 0, date(2026, 10, 26)), "3 roky 2 měsíce")
        self.assertEqual(age_long(date(2025, 10, 26), 0, date(2026, 10, 26)), "1 rok")
        self.assertEqual(age_long(date(2026, 5, 2), 0, date(2026, 10, 26)), "5 měsíců")
        self.assertEqual(age_long(date(2026, 10, 10), 0, date(2026, 10, 26)), "2 týdny")
        self.assertEqual(age_long(False, 2019, date(2026, 10, 26)), "cca 7 let")
        self.assertEqual(age_long(False, 0, date(2026, 10, 26)), "")

    def test_has_content(self):
        self.assertTrue(self.full._visit_report_has_content())
        self.assertFalse(self.Record.create({"pet_id": self.pet.id, "reception_note": "jen recepce"})
                         ._visit_report_has_content())

    def test_rights(self):
        report = self.env.ref("elite_vet_clinic.report_visit")
        self.assertEqual(report.binding_model_id.model, "elite.vet.clinical.record")
        self.assertEqual(report.report_name, REPORT)
        for user in (self.reception, self.nurse, self.doctor_user, self.manager):
            self.assertIn("Kulhá na levou hrudní.", self.render(self.full, user=user), user.login)
            self.assertIn(report.id, self.report_bindings(user), user.login)
        outsider = self.env["res.users"].with_context(no_reset_password=True).create({
            "name": "Mimo kliniku", "login": "clinic_outsider_test",
            "groups_id": [(6, 0, [self.env.ref("base.group_user").id])]})
        with self.assertRaises(Exception) as caught:
            self.render(self.full, user=outsider)
        error = caught.exception
        self.assertTrue(isinstance(error, AccessError) or isinstance(error.__cause__, AccessError), repr(error))
        self.assertNotIn(report.id, self.report_bindings(outsider))

    def test_card_button_and_assets(self):
        bundle = self.env["ir.qweb"]._get_asset_bundle("web.assets_backend", css=False, js=True)
        templates = bundle.generate_xml_bundle()
        self.assertIn("printReport", templates)
        self.assertIn("evpc-tl-print", templates)
        self.assertIn("Nejdřív vyplňte záznam", templates)
        self.assertNotIn("Bude ve fázi 5", templates)
        css = self.env["ir.qweb"]._get_asset_bundle("web.report_assets_common", css=True, js=False)
        self.assertTrue(any(a.url.endswith("elite_vet_clinic/static/src/report/visit_report.scss")
                            for a in css.stylesheets))
