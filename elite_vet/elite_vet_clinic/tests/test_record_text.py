"""Task 32: one record text ("Záznam z vyšetření") instead of anamnesis / examination / diagnosis:
the migration of the old texts, inserting a template, the report and the card read record_text only."""
from odoo.tests import tagged

from odoo.addons.elite_vet_clinic.models.clinical_record import (
    combine_legacy_texts, insert_template_text, migrate_legacy_texts, record_text_title)

from .common import ClinicCase

REPORT = "elite_vet_clinic.report_visit_document"


@tagged("post_install", "-at_install")
class TestRecordText(ClinicCase):

    # ---------------------------------------------------------------- migration
    def test_combine_legacy_texts(self):
        self.assertEqual(combine_legacy_texts("Kašle.", "Bez nálezu.", "Zdravý.\nKontrola za týden."),
                         "Anamnéza:\nKašle.\n\nVyšetření:\nBez nálezu.\n\nDiagnóza a doporučení:\nZdravý.\n"
                         "Kontrola za týden.")
        self.assertEqual(combine_legacy_texts("  Kašle.\n", None, "Zdravý."),
                         "Anamnéza:\nKašle.\n\nDiagnóza a doporučení:\nZdravý.")
        self.assertEqual(combine_legacy_texts(False, "Bez nálezu.\n\n", False), "Bez nálezu.",
                         "one filled part: the text without a heading")
        self.assertEqual(combine_legacy_texts(False, " \n ", None), "")

    def test_migration_combinations_and_idempotent(self):
        def record(**vals):
            return self.Record.create(dict({"pet_id": self.pet.id}, **vals))
        full = record(anamnesis="Kulhá od včera.", examination="Bolestivost karpu.", diagnosis="Distorze.")
        two = record(examination="Otok.", diagnosis="Klid 10 dní.")
        only_one = record(diagnosis="Zdravý.\n")
        blank = record(anamnesis="  ", temperature=38.5)
        none = record()
        kept = record(anamnesis="Staré.", record_text="Už přepsáno v novém poli.")
        self.env.flush_all()
        self.env.cr.execute("SELECT write_date FROM elite_vet_clinical_record WHERE id = %s", [full.id])
        write_date = self.env.cr.fetchone()[0]

        migrate_legacy_texts(self.env.cr)
        self.env.invalidate_all()
        self.assertEqual(full.record_text,
                         "Anamnéza:\nKulhá od včera.\n\nVyšetření:\nBolestivost karpu.\n\n"
                         "Diagnóza a doporučení:\nDistorze.")
        self.assertEqual(two.record_text, "Vyšetření:\nOtok.\n\nDiagnóza a doporučení:\nKlid 10 dní.")
        self.assertEqual(only_one.record_text, "Zdravý.")
        self.assertFalse(blank.record_text)
        self.assertFalse(none.record_text)
        self.assertEqual(kept.record_text, "Už přepsáno v novém poli.")
        self.assertEqual(full.anamnesis, "Kulhá od včera.", "the old texts stay in the database")
        self.env.cr.execute("SELECT write_date FROM elite_vet_clinical_record WHERE id = %s", [full.id])
        self.assertEqual(self.env.cr.fetchone()[0], write_date, "plain SQL, write date kept")

        # a second run changes nothing, also after the new text was edited
        full.record_text = "Upraveno po migraci."
        self.env.flush_all()
        self.assertEqual(migrate_legacy_texts(self.env.cr), 0)
        self.env.invalidate_all()
        self.assertEqual(full.record_text, "Upraveno po migraci.")
        self.assertEqual(two.record_text, "Vyšetření:\nOtok.\n\nDiagnóza a doporučení:\nKlid 10 dní.")

    # ---------------------------------------------------------------- template insert
    def test_insert_template_text(self):
        body = "Celkový stav dobrý.\n"
        self.assertEqual(insert_template_text("", body), ("Celkový stav dobrý.", 19))
        self.assertEqual(insert_template_text(False, body, 0), ("Celkový stav dobrý.", 19))
        # no cursor, or the cursor at the end: appended after a blank line
        self.assertEqual(insert_template_text("Kašle.\n", body)[0], "Kašle.\n\nCelkový stav dobrý.")
        self.assertEqual(insert_template_text("Kašle.", body, 6)[0], "Kašle.\n\nCelkový stav dobrý.")
        self.assertEqual(insert_template_text("Kašle.  \n", body, 7)[0], "Kašle.\n\nCelkový stav dobrý.")
        # inside the text: at the cursor on its own line, nothing replaced
        text, caret = insert_template_text("Kašle.\nTeplota.", body, 7)
        self.assertEqual(text, "Kašle.\nCelkový stav dobrý.\nTeplota.")
        self.assertEqual(text[caret:], "\nTeplota.")
        self.assertEqual(insert_template_text("Kašle. Teplota.", body, 7)[0], "Kašle. \nCelkový stav dobrý.\nTeplota.")
        self.assertEqual(insert_template_text("Kašle.", body, 0)[0], "Celkový stav dobrý.\nKašle.")
        self.assertEqual(insert_template_text("Kašle.", body, 99)[0], "Kašle.\n\nCelkový stav dobrý.",
                         "a position past the end = the end")
        self.assertEqual(insert_template_text("Kašle.", " ", 2), ("Kašle.", 2), "an empty template changes nothing")

    def test_title(self):
        self.assertEqual(record_text_title("Anamnéza:\n\n Kulhá od včera. \nVyšetření:\nOtok."), "Kulhá od včera.")
        self.assertEqual(record_text_title("Diagnóza a doporučení:"), "")
        self.assertEqual(record_text_title("x" * 200)[-1], "…")
        record = self.Record.create({"pet_id": self.pet.id, "record_text": "Vyšetření:\nOtok karpu."})
        self.assertEqual(record.record_summary, "Otok karpu.")

    # ---------------------------------------------------------------- readers use record_text only
    def test_report_prints_record_text_never_old_fields(self):
        record = self.Record.create({
            "pet_id": self.pet.id, "temperature": 38.4, "weight": 15.2,
            "record_text": "Kulhá od včera.\nKlid.\n\n" + "\n".join("Řádek %d dlouhého textu." % i for i in range(120)),
            "anamnesis": "STARAANAMNEZA", "examination": "STAREVYSETRENI", "diagnosis": "STARADIAGNOZA"})
        html = self.env["ir.actions.report"]._render_qweb_html(REPORT, record.ids)[0]
        html = html.decode() if isinstance(html, bytes) else html
        self.assertEqual(html.count("<h2>Záznam z vyšetření</h2>"), 1, "one section")
        self.assertIn("teplota 38,4 °C · hmotnost 15,2 kg", html)
        self.assertRegex(html, r"Kulhá od včera\.<br\s*/?>\s*Klid\.")
        self.assertIn("Řádek 119 dlouhého textu.", html, "a long text is printed whole (it paginates)")
        for text in ("STARAANAMNEZA", "STAREVYSETRENI", "STARADIAGNOZA", "Klinické vyšetření", "<h2>Anamnéza",
                     "<h2>Diagnóza"):
            self.assertNotIn(text, html, text)
        data = record._visit_report_data()
        self.assertNotIn("anamnesis", data)
        self.assertNotIn("examination", data)
        only_old = self.Record.create({"pet_id": self.pet.id, "diagnosis": "STARADIAGNOZA"})
        self.assertFalse(only_old._visit_report_has_content(), "the deprecated texts are not content")

    def test_card_reads_record_text(self):
        Card = self.Record.with_user(self.doctor_user)
        rec = Card.open_today_record(self.pet.id)
        Card.save_record(rec["id"], {"record_text": "Anamnéza:\nKašle.", "diagnosis": "ignorováno"})
        record = self.Record.browse(rec["id"])
        self.assertEqual((record.record_text, record.diagnosis), ("Anamnéza:\nKašle.", False))
        data = Card.card_data(self.pet.id)
        self.assertEqual(data["today_record"]["record_text"], "Anamnéza:\nKašle.")
        entry = next(e for e in data["timeline"] if e["type"] == "record" and e["id"] == record.id)
        self.assertEqual((entry["title"], entry["record_text"]), ("Kašle.", "Anamnéza:\nKašle."))
        for key in ("anamnesis", "examination", "diagnosis", "diagnosis_text"):
            self.assertNotIn(key, entry)
            self.assertNotIn(key, data["today_record"])
        # backend search over the record text
        self.assertIn(record, self.Record.search([("record_text", "ilike", "Kašle")]))

    def test_card_template_button_in_assets(self):
        bundle = self.env["ir.qweb"]._get_asset_bundle("web.assets_backend", css=False, js=True)
        templates = bundle.generate_xml_bundle()
        self.assertIn('name="record_text"', templates)
        self.assertIn("Vložit šablonu do záznamu z vyšetření", templates)
        self.assertNotIn("'tpl-' + s.key", templates, "one template button, not one per field")
