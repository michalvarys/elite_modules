from datetime import date

from odoo.exceptions import AccessError
from odoo.tests import tagged

from odoo.addons.elite_vet_winvet.tests.common import BASE

from .common import SaleCase

ITEM = BASE + 7101
R1, R2, I1, I2, I3, OTHER = (BASE + n for n in (8101, 8102, 8103, 8104, 8105, 8106))


@tagged("post_install", "-at_install")
class TestStockRegleta(SaleCase):
    """Regleta skladu: receipts at their price, issues at WinVet's average cost, without and with VAT."""

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
            # receipt in September: 10 ks at 112 Kč with VAT; WinVet left the line rate 0 - the item's
            # purchase rate (12 %) applies, as in WinVet: net 100 per ks
            cls.move(R1, "in", "2026-09-05", 10, 1120.0, doc="SP0001"),
            # issues: WinVet's own net cost (weighted average), not the price of the receipt line
            cls.move(I1, "out", "2026-09-20", 2, 200.0, receipt=R1, doc="SV0001"),
            # receipt in October with the rate on the line: 5 ks at 134,40 with VAT (net 120 per ks)
            cls.move(R2, "in", "2026-10-03", 5, 672.0, rate=12.0, doc="SP0002"),
            # average after R2: (800 + 600) / 13 = 107,69 per ks
            cls.move(I2, "out", "2026-10-10", 3, 323.08, receipt=R1, doc="SV0002"),
            cls.move(I3, "out", "2026-10-12", 1, 107.69, receipt=R2, doc="SV0003"),
            # after the period: not in the October regleta
            cls.move(OTHER, "out", "2026-11-02", 1, 107.69, receipt=R1, doc="SV0004"),
        ])

    @classmethod
    def push_raw(cls, entity, records, mode="full"):
        cls.run_no += 1
        res = cls.sync.push({"entity": entity, "mode": mode, "records": records, "deleted": [],
                             "batch": 1, "batches": 1, "run_id": "regleta-%s" % cls.run_no})
        assert res.get("ok"), res
        return res

    @staticmethod
    def move(ref, direction, day, qty, amount, rate=0.0, receipt=None, doc=None, item_rate=12.0):
        return {"id": ref, "item_id": ITEM, "direction": direction, "move_type": "P" if direction == "in" else "V",
                "date": day, "document": doc, "document_type": "SP" if direction == "in" else "SV",
                "quantity": qty, "unit": "ks", "unit_price": amount / qty, "amount": amount, "vat_amount": 0.0,
                "vat_rate": rate, "amount_includes_vat": True, "receipt_id": receipt, "item_vat_rate": item_rate}

    def data(self, date_from=date(2026, 10, 1), date_to=date(2026, 10, 31)):
        return self.env["elite.vet.stock.regleta"].regleta_data(date_from, date_to)

    def row(self, r):
        return next(row for g in r["groups"] for row in g["rows"] if row["code"] == "RG1")

    def test_push_stores_moves(self):
        moves = self.env["elite.vet.winvet.stock.move"].search([("item_winvet_ref", "=", ITEM)])
        self.assertEqual(len(moves), 6)
        issue = moves.filtered(lambda m: m.winvet_ref == I2)
        self.assertEqual((issue.direction, issue.receipt_winvet_ref, issue.item_id.code, issue.item_vat_rate),
                         ("out", R1, "RG1", 12.0))

    def test_october(self):
        r = self.data()
        row = self.row(r)
        expected = {
            "opening": (8, 800.0, 896.0),      # 10 x 100 - 200
            "in": (5, 600.0, 672.0),
            "out": (4, 430.77, 482.4624),      # WinVet's cost 323,08 + 107,69, VAT 12 %
            "closing": (9, 969.23, 1085.5376),
        }
        for part, (qty, net, gross) in expected.items():
            self.assertAlmostEqual(row[part]["qty"], qty, msg=part)
            self.assertAlmostEqual(row[part]["net"], net, msg=part)
            self.assertAlmostEqual(row[part]["gross"], gross, msg=part)
        self.assertEqual([d["number"] for d in r["receipts"]], ["SP0002"])
        self.assertEqual([(v["rate"], round(v["net"], 2), v["gross"]) for v in r["vat_rows"]], [(12.0, 600.0, 672.0)])
        self.assertEqual((r["item_rate"]["count"], r["negative"]), (0, 0))

    def test_september_receipt_without_line_rate(self):
        r = self.data(date(2026, 9, 1), date(2026, 9, 30))
        doc = r["receipts"][0]
        self.assertEqual(doc["number"], "SP0001")
        for key, value in (("net", 1000.0), ("vat", 120.0), ("gross", 1120.0)):
            self.assertAlmostEqual(doc[key], value, msg=key)
        self.assertEqual((r["item_rate"]["count"], round(r["item_rate"]["net"], 2)), (1, 1000.0))
        row = self.row(r)
        self.assertAlmostEqual(row["out"]["net"], 200.0)
        self.assertAlmostEqual(row["out"]["gross"], 224.0)
        self.assertAlmostEqual(row["closing"]["gross"], 896.0)

    def test_sold_out_is_worth_nothing(self):
        r = self.data(date(2026, 11, 1), date(2026, 11, 30))
        closing = self.row(r)["closing"]
        self.assertAlmostEqual(closing["qty"], 8)
        self.assertAlmostEqual(closing["net"], 969.23 - 107.69)

    def test_values_and_rates(self):
        """WinVet's VAT amount is wrong on some lines (12 % of the price with VAT): not used."""
        Move = self.env["elite.vet.winvet.stock.move"]
        move = Move.new({"direction": "in", "amount": 300.0, "vat_amount": 36.0, "vat_rate": 12.0,
                         "amount_includes_vat": True})
        net, gross = move._values()
        self.assertAlmostEqual(net, 267.857, places=3)
        self.assertEqual(gross, 300.0)
        move = Move.new({"direction": "in", "amount": 100.0, "vat_rate": 21.0})
        self.assertAlmostEqual(move._values()[1], 121.0)
        # the line has no rate: the purchase rate of the item, else its sale rate (bridge before 6.1.0)
        move = Move.new({"direction": "in", "amount": 121.0, "item_vat_rate": 21.0, "amount_includes_vat": True})
        self.assertAlmostEqual(move._values()[0], 100.0)
        item = self.env["elite.vet.winvet.item"].search([("winvet_ref", "=", ITEM)])
        move = Move.new({"direction": "in", "amount": 112.0, "item_id": item.id, "amount_includes_vat": True})
        self.assertAlmostEqual(move._values()[0], 100.0)
        # no rate anywhere: goods 12 %, the rest 21 %
        self.assertEqual(Move.new({"direction": "in", "amount": 1.0})._rate(), 21.0)
        item.vat_rate = 0.0
        self.assertEqual(move._rate(), 12.0 if item.kind == "product" else 21.0)
        # an issue: WinVet's cost without VAT
        move = Move.new({"direction": "out", "quantity": 2.0, "unit_price": 50.0, "amount": 100.0,
                         "item_vat_rate": 21.0})
        self.assertEqual(move._values(), (100.0, 121.0))
        # a return with a wrong line total in WinVet: quantity x unit price
        move = Move.new({"direction": "in", "quantity": -2.0, "unit_price": 64.99, "amount": -1559.76,
                         "vat_rate": 12.0, "amount_includes_vat": True})
        self.assertAlmostEqual(move._values()[1], -129.98)

    def test_pdf_for_managers_only(self):
        wizard = self.env["elite.vet.stock.regleta.wizard"].with_user(self.manager).create(
            {"preset": "custom", "date_from": date(2026, 10, 1), "date_to": date(2026, 10, 31)})
        html, _type = self.env["ir.actions.report"].with_user(self.manager)._render_qweb_html(
            "elite_vet_sale.report_stock_regleta", wizard.ids)
        html = html.decode()
        self.assertIn("Regleta skladu", html)
        self.assertIn("Regleta lék", html)
        self.assertIn("SP0002", html)
        self.assertEqual(wizard._regleta_filename(), "Regleta_skladu_2026-10-01_2026-10-31")
        with self.assertRaises(AccessError):
            self.env["elite.vet.stock.regleta.wizard"].with_user(self.reception).create({}).action_print()
