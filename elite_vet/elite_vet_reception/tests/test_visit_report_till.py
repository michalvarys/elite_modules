"""Task 27: K pokladně in the Recepce till has a print icon for the visit report; the reception
renders it (read rights), without the internal notes."""
from odoo.tests import tagged
from odoo.tools import file_open

from odoo.addons.elite_vet_clinic.tests.common import ClinicCase


@tagged("post_install", "-at_install")
class TestVisitReportTill(ClinicCase):

    def test_print_icon_in_to_pay_rows(self):
        with file_open("elite_vet_reception/static/src/pos/today_screen/today_screen.xml") as f:
            xml = f.read()
        with file_open("elite_vet_reception/static/src/pos/today_screen/today_screen.js") as f:
            js = f.read()
        self.assertIn("o_ev_print_report", xml)
        self.assertIn("/report/pdf/elite_vet_clinic.report_visit_document/", js)

    def test_reception_prints_without_notes(self):
        record = self.Record.create({"pet_id": self.pet.id, "record_text": "Zdráv.", "reception_note": "RECNOTE",
                                     "room_note": "ROOMNOTE"})
        record.action_done()
        html = self.env["ir.actions.report"].with_user(self.reception)._render_qweb_html(
            "elite_vet_clinic.report_visit_document", record.ids)[0]
        html = html.decode() if isinstance(html, bytes) else html
        self.assertIn("Zdráv.", html)
        self.assertNotIn("RECNOTE", html)
        self.assertNotIn("ROOMNOTE", html)
