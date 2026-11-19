from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestDotykackaUpdate(TransactionCase):
    """Runs after the install of the module on top of elite_trafika_dotykacka (see README, Testy)."""

    def setUp(self):
        super().setUp()
        self.config = self.env.ref("elite_trafika_pos.pos_config_trafika")
        self.orders = self.env["pos.order"].search([("config_id", "=", self.config.id),
                                                    ("name", "=like", "Dotykačka %")])
        self.new = self.orders.filtered(lambda o: o.pos_reference > "20260006141")
        self.importer = self.env["elite.trafika.dotykacka.import"]

    def test_totals_as_in_dotykacka(self):
        """Report "Přehled tržeb" 1. 1. – 19. 11. 2026: 2 305 000 Kč; 463 receipts after the archive."""
        self.assertEqual(len(self.orders), 6604)
        self.assertEqual(len(set(self.orders.mapped("pos_reference"))), 6604)
        self.assertAlmostEqual(sum(self.orders.mapped("amount_total")), 2305000.0, places=2)
        self.assertEqual(len(self.new), 463)
        self.assertAlmostEqual(sum(self.new.mapped("amount_total")), 200489.0, places=2)
        self.assertEqual(len(self.orders.lines), 9285)
        self.assertEqual(set(self.orders.mapped("state")), {"done"})

    def test_last_receipt(self):
        order = self.orders.filtered(lambda o: o.pos_reference == "20260006604")
        self.assertEqual(str(order.date_order), "2026-11-19 18:39:26")  # 19:39 in Prague
        self.assertAlmostEqual(order.amount_total, 334.0)
        self.assertEqual(order.payment_ids.payment_method_id.name, "Kartou")
        self.assertEqual(order.session_id.state, "closed")

    def test_shifts(self):
        sessions = self.new.session_id
        self.assertEqual(set(sessions.mapped("state")), {"closed"})
        self.assertEqual(str(sessions.sorted("start_at")[-1].start_at), "2026-11-19 11:04:47")
        self.assertEqual(len(self.orders.session_id), 268)  # 270 shifts, 2 of them without a receipt

    def test_new_products(self):
        product = self.env.ref("elite_trafika_dotykacka_update.product_hist_bong_shisha").with_context(active_test=False)
        self.assertFalse(product.active)
        self.assertTrue(self.new.lines.filtered(lambda l: l.product_id.product_tmpl_id == product))

    def test_outside_accounting_and_stock(self):
        self.assertFalse(self.new.session_id.move_id)
        self.assertFalse(self.new.account_move)
        self.assertFalse(self.new.picking_ids)

    def test_report(self):
        data = self.env["report.pos.order"].read_group([("config_id", "=", self.config.id)], ["price_total:sum"], [])
        self.assertAlmostEqual(data[0]["price_total"], 2305000.0, places=0)

    def test_import_is_repeatable(self):
        self.assertEqual(self.importer.import_history("elite_trafika_dotykacka_update"), 0)
        self.assertEqual(self.importer.import_history(), 0)
