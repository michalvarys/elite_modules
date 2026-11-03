from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestDotykackaImport(TransactionCase):
    """Runs after the install of the module (see README, Testy)."""

    def setUp(self):
        super().setUp()
        self.config = self.env.ref("elite_trafika_pos.pos_config_trafika")
        self.orders = self.env["pos.order"].search([("config_id", "=", self.config.id),
                                                    ("name", "=like", "Dotykačka %")])
        self.importer = self.env["elite.trafika.dotykacka.import"]

    def test_all_receipts_imported(self):
        """Totals as in the Dotykačka reports: 6 141 receipts, 2 104 511 Kč, 21 % VAT."""
        self.assertEqual(len(self.orders), 6141)
        self.assertAlmostEqual(sum(self.orders.mapped("amount_total")), 2104511.0, places=2)
        self.assertEqual(len(self.orders.lines), 8597)
        self.assertEqual(set(self.orders.mapped("state")), {"done"})
        self.assertEqual(self.orders.lines.tax_ids.mapped("amount"), [21.0])

    def test_receipt(self):
        order = self.orders.filtered(lambda o: o.pos_reference == "20260006141")
        self.assertEqual(order.lines.full_product_name, "TEREA Turquoise")
        self.assertAlmostEqual(order.amount_total, 150.0)
        self.assertAlmostEqual(order.amount_tax, 26.03)
        self.assertEqual(order.payment_ids.payment_method_id.name, "Kartou")
        self.assertEqual(str(order.date_order), "2026-11-03 18:07:02")  # 19:07 in Prague

    def test_payments(self):
        cash = self.orders.payment_ids.filtered(lambda p: p.payment_method_id.is_cash_count)
        self.assertAlmostEqual(sum(self.orders.payment_ids.mapped("amount")), 2104511.0 + 1606.0, places=2)
        self.assertTrue(cash)

    def test_outside_accounting_and_stock(self):
        """The history posts no journal entry and moves no stock."""
        sessions = self.orders.session_id
        self.assertEqual(len(sessions), 251)  # 253 shifts, 2 of them without a receipt
        self.assertEqual(set(sessions.mapped("state")), {"closed"})
        self.assertFalse(sessions.move_id)
        self.assertFalse(self.orders.account_move)
        self.assertFalse(self.orders.picking_ids)
        self.assertFalse(self.env["account.move.line"].search_count([("company_id", "=", self.config.company_id.id)]))

    def test_report(self):
        """The sales are in the Point of Sale analysis."""
        data = self.env["report.pos.order"].read_group([("config_id", "=", self.config.id)],
                                                         ["price_total:sum"], [])
        self.assertAlmostEqual(data[0]["price_total"], 2104511.0, places=0)

    def test_opening_stock(self):
        location = self.config.picking_type_id.warehouse_id.lot_stock_id
        quants = self.env["stock.quant"].search([("location_id", "=", location.id)])
        self.assertEqual(len(quants.product_id), 352)
        self.assertAlmostEqual(sum(quants.mapped("quantity")), 3019.0)

    def test_import_is_repeatable(self):
        self.assertEqual(self.importer.import_history(), 0)
        self.assertEqual(self.importer.import_stock(), 0)
