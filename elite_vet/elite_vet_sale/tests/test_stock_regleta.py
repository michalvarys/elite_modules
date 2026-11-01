from datetime import date

from odoo.exceptions import AccessError
from odoo.tests import tagged

from odoo.addons.elite_vet_winvet.tests.common import BASE

from .common import SaleCase

ITEM = BASE + 7101
R1, R2, I1, I2, I3, OTHER = (BASE + n for n in (8101, 8102, 8103, 8104, 8105, 8106))


@tagged("post_install", "-at_install")
class TestStockRegleta(SaleCase):
    """Regleta skladu: every move valued by its receipt line, without and with VAT."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.sync = cls.env["elite.vet.winvet.sync"]
        cls.run_no = 0
        cls.push_raw("items", [
            {"id": ITEM, "code": "RG1", "name": "Regleta lék", "classification": "product",
             "stock_tracked": True, "tracked_drug": False, "unit": "ks", "barcode": None,
             "price": 200.0, "price_untaxed": 178.57, "vat_rate": 12.0, "active": True},
        ], mode="incremental")
        cls.push_raw("stock_moves", [
            # receipt in September: 10 ks for 1 120 Kč with 12 % VAT (net 100, gross 112 per ks)
            cls.move(R1, "in", "2026-09-05", 10, 1120.0, vat=120.0, rate=12.0, doc="SP0001"),
            # WinVet's own issue cost (190) is not used - the receipt price is
            cls.move(I1, "out", "2026-09-20", 2, 190.0, receipt=R1, doc="SV0001"),
            # receipt in October entered at VAT rate 0: taken as entered
            cls.move(R2, "in", "2026-10-03", 5, 500.0, doc="SP0002"),
            cls.move(I2, "out", "2026-10-10", 3, 270.0, receipt=R1, doc="SV0002"),
            cls.move(I3, "out", "2026-10-12", 1, 95.0, receipt=R2, doc="SV0003"),
            # after the period: not in the October regleta
            cls.move(OTHER, "out", "2026-11-02", 1, 90.0, receipt=R1, doc="SV0004"),
        ])

    @classmethod
    def push_raw(cls, entity, records, mode="full"):
        cls.run_no += 1
        res = cls.sync.push({"entity": entity, "mode": mode, "records": records, "deleted": [],
                             "batch": 1, "batches": 1, "run_id": "regleta-%s" % cls.run_no})
        assert res.get("ok"), res
        return res

    @staticmethod
    def move(ref, direction, day, qty, amount, vat=0.0, rate=0.0, receipt=None, doc=None):
        return {"id": ref, "item_id": ITEM, "direction": direction, "move_type": "P" if direction == "in" else "V",
                "date": day, "document": doc, "document_type": "SP" if direction == "in" else "SV",
                "quantity": qty, "unit": "ks", "unit_price": amount / qty, "amount": amount, "vat_amount": vat, "vat_rate": rate,
                "amount_includes_vat": True, "receipt_id": receipt}

    def data(self, date_from=date(2026, 10, 1), date_to=date(2026, 10, 31)):
        return self.env["elite.vet.stock.regleta"].regleta_data(date_from, date_to)

    def test_push_stores_moves(self):
        moves = self.env["elite.vet.winvet.stock.move"].search([("item_winvet_ref", "=", ITEM)])
        self.assertEqual(len(moves), 6)
        issue = moves.filtered(lambda m: m.winvet_ref == I2)
        self.assertEqual((issue.direction, issue.receipt_winvet_ref, issue.item_id.code), ("out", R1, "RG1"))

    def test_october(self):
        r = self.data()
        row = next(row for g in r["groups"] for row in g["rows"] if row["code"] == "RG1")
        expected = {
            "opening": (8, 800.0, 896.0),   # 10 - 2 ks at 100 / 112
            "in": (5, 500.0, 500.0),        # the 0 % receipt
            "out": (4, 400.0, 436.0),       # 3 ks from R1 (300 / 336) + 1 ks from R2 (100 / 100)
            "closing": (9, 900.0, 960.0),
        }
        for part, (qty, net, gross) in expected.items():
            self.assertAlmostEqual(row[part]["qty"], qty, msg=part)
            self.assertAlmostEqual(row[part]["net"], net, msg=part)
            self.assertAlmostEqual(row[part]["gross"], gross, msg=part)
        self.assertEqual([(d["number"], d["zero_vat"]) for d in r["receipts"]], [("SP0002", True)])
        self.assertEqual((r["zero_vat"]["count"], r["zero_vat"]["net"]), (1, 500.0))
        self.assertEqual([(v["rate"], v["net"]) for v in r["vat_rows"]], [(0.0, 500.0)])
        self.assertEqual((r["no_receipt"]["count"], r["negative"]), (0, 0))

    def test_september_receipt_with_vat(self):
        r = self.data(date(2026, 9, 1), date(2026, 9, 30))
        doc = r["receipts"][0]
        self.assertEqual(doc["number"], "SP0001")
        for key, value in (("net", 1000.0), ("vat", 120.0), ("gross", 1120.0)):
            self.assertAlmostEqual(doc[key], value, msg=key)
        row = next(row for g in r["groups"] for row in g["rows"] if row["code"] == "RG1")
        self.assertAlmostEqual(row["out"]["net"], 200.0)
        self.assertAlmostEqual(row["closing"]["gross"], 896.0)

    def test_net_from_the_rate_not_from_winvet_vat(self):
        """WinVet's VAT amount is wrong on some lines (12 % of the price with VAT): not used."""
        move = self.env["elite.vet.winvet.stock.move"].new(
            {"amount": 300.0, "vat_amount": 36.0, "vat_rate": 12.0, "amount_includes_vat": True})
        net, gross = move._receipt_values()
        self.assertAlmostEqual(net, 267.857, places=3)
        self.assertEqual(gross, 300.0)
        move = self.env["elite.vet.winvet.stock.move"].new({"amount": 100.0, "vat_rate": 21.0})
        self.assertAlmostEqual(move._receipt_values()[1], 121.0)
        # a return with a wrong line total in WinVet: quantity x unit price
        move = self.env["elite.vet.winvet.stock.move"].new(
            {"quantity": -2.0, "unit_price": 64.99, "amount": -1559.76, "vat_rate": 12.0, "amount_includes_vat": True})
        self.assertAlmostEqual(move._receipt_values()[1], -129.98)

    def test_pdf_for_managers_only(self):
        wizard = self.env["elite.vet.stock.regleta.wizard"].with_user(self.manager).create(
            {"preset": "custom", "date_from": date(2026, 10, 1), "date_to": date(2026, 10, 31)})
        html, _type = self.env["ir.actions.report"].with_user(self.manager)._render_qweb_html(
            "elite_vet_sale.report_stock_regleta", wizard.ids)
        html = html.decode()
        self.assertIn("Regleta skladu", html)
        self.assertIn("Regleta lék", html)
        self.assertIn("SP0002 *", html)
        self.assertEqual(wizard._regleta_filename(), "Regleta_skladu_2026-10-01_2026-10-31")
        with self.assertRaises(AccessError):
            self.env["elite.vet.stock.regleta.wizard"].with_user(self.reception).create({}).action_print()
