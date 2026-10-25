"""Task 27: the visit report prints the lot and expiry of the medicines once the bill is paid
(read from the till's delivery), never the prices."""
from datetime import datetime

from odoo.tests import tagged

from .common import SaleCase

REPORT = "elite_vet_clinic.report_visit_document"


@tagged("post_install", "-at_install")
class TestVisitReportLots(SaleCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        warehouse = cls.env["stock.warehouse"].search([("company_id", "=", cls.company.id)], limit=1)
        cls.product = cls.vaccine.product_id
        assert cls.product.tracking == "lot", "the vaccine item is a lot-tracked product"
        cls.lot = cls.env["stock.lot"].create({"name": "SARZE-T27", "product_id": cls.product.id,
                                               "expiration_date": datetime(2027, 4, 30, 12, 0)})
        cls.env["stock.quant"]._update_available_quantity(cls.product, warehouse.lot_stock_id, 5, lot_id=cls.lot)

    def render(self, record, user=None):
        Report = self.env["ir.actions.report"].with_user(user) if user else self.env["ir.actions.report"]
        html = Report._render_qweb_html(REPORT, record.ids)[0]
        return html.decode() if isinstance(html, bytes) else html

    def record(self):
        api = self.as_user(self.nurse)
        data = api.open_today_record(self.pet.id, force_new=True)
        api.add_item(data["id"], self.vaccine.id)
        data = api.add_item(data["id"], self.exam.id)
        api.save_record(data["id"], {"diagnosis": "Vakcinace provedena."})
        api.mark_done(data["id"])
        return self.Record.browse(data["id"])

    def test_lot_and_expiry_after_payment(self):
        record = self.record()
        html = self.render(record)
        self.assertNotIn("SARZE-T27", html, "not paid yet: the lot is not known")
        self.assertNotIn("Šarže", html)
        self.settle(record.sale_order_id)
        self.assertEqual(record.payment_state, "paid")
        for user in (None, self.reception, self.nurse):
            html = self.render(record, user=user)
            self.assertIn("Šarže", html)
            self.assertIn("SARZE-T27", html)
            self.assertIn("30. 4. 2027", html)
            self.assertNotIn("620,5", html)
            self.assertNotIn("620.5", html)
        lots = record._visit_report_lots()
        vaccine_line = record.line_ids.filtered(lambda l: l.item_id == self.vaccine)
        exam_line = record.line_ids.filtered(lambda l: l.item_id == self.exam)
        self.assertEqual(lots[vaccine_line.id], [("SARZE-T27", datetime(2027, 4, 30).date())])
        self.assertNotIn(exam_line.id, lots)
