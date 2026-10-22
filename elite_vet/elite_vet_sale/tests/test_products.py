from odoo.tests import tagged

from odoo.addons.elite_vet_winvet.tests.common import BASE

from .common import SaleCase


@tagged("post_install", "-at_install")
class TestProducts(SaleCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.sync = cls.env["elite.vet.winvet.sync"]
        cls.Item = cls.env["elite.vet.winvet.item"]

    # helpers --------------------------------------------------------------
    def item_rec(self, n, classification="service", **over):
        rec = {"id": BASE + 5000 + n, "code": "P%s" % n, "name": "Testovací položka %s" % n,
               "classification": classification, "stock_tracked": classification == "product",
               "tracked_drug": False, "unit": "ks", "barcode": None, "price": 450.0,
               "price_untaxed": 371.9, "vat_rate": 21.0, "active": True}
        rec.update(over)
        return rec

    def push_items(self, *records):
        res = self.sync.push({"entity": "items", "mode": "incremental", "records": list(records),
                              "deleted": [], "batch": 1, "batches": 1, "run_id": "t3"})
        self.assertTrue(res.get("ok"), res)
        return res

    def item(self, n):
        return self.Item.with_context(active_test=False).search([("winvet_ref", "=", BASE + 5000 + n)])

    def product(self, n):
        return self.item(n).product_id.with_context(active_test=False)

    # tests ----------------------------------------------------------------
    def test_lot_and_expiry_groups(self):
        self.setup.ensure_setup()
        self.assertTrue(self.env.user.has_group("stock.group_production_lot"))
        self.assertTrue(self.env.ref("base.group_user").implied_ids.filtered(
            lambda g: g == self.env.ref("stock.group_production_lot")))

    def test_units_precision(self):
        unit = self.env.ref("uom.product_uom_unit")
        self.assertAlmostEqual(unit.rounding, 0.001)
        self.assertGreaterEqual(self.env.ref("product.decimal_product_uom").digits, 3)

    def test_pos_categories(self):
        self.assertEqual(self.env.ref("elite_vet_sale.pos_category_services").name, "Úkony")
        self.assertEqual(self.env.ref("elite_vet_sale.pos_category_products").name, "Léky a zboží")

    def test_service_item(self):
        self.push_items(self.item_rec(1))
        product = self.product(1)
        self.assertTrue(product)
        self.assertEqual(product.type, "service")
        self.assertEqual(product.list_price, 450.0)
        self.assertEqual(product.taxes_id, self.tax21)
        self.assertEqual(product.default_code, "P1")
        self.assertTrue(product.sale_ok)
        self.assertTrue(product.available_in_pos)
        self.assertEqual(product.pos_categ_ids, self.env.ref("elite_vet_sale.pos_category_services"))
        self.assertEqual(product.uom_id, self.env.ref("uom.product_uom_unit"))
        self.assertTrue(product.active)

    def test_stock_item(self):
        self.push_items(self.item_rec(2, "product", vat_rate=12.0, price=100.0, barcode="8590000000022"))
        product = self.product(2)
        self.assertEqual(product.type, "consu")
        self.assertTrue(product.is_storable)
        self.assertEqual(product.tracking, "lot")
        self.assertTrue(product.use_expiration_date)
        self.assertEqual(product.taxes_id, self.tax12)
        self.assertEqual(product.barcode, "8590000000022")
        self.assertEqual(product.pos_categ_ids, self.env.ref("elite_vet_sale.pos_category_products"))

    def test_non_stock_goods(self):
        self.push_items(self.item_rec(3, "product", stock_tracked=False))
        product = self.product(3)
        self.assertEqual(product.type, "consu")
        self.assertFalse(product.is_storable)
        self.assertEqual(product.tracking, "none")

    def test_other_kind_has_no_product(self):
        self.push_items(self.item_rec(4, "group"))
        self.assertTrue(self.item(4))
        self.assertFalse(self.item(4).product_id)

    def test_missing_price_and_vat(self):
        self.push_items(self.item_rec(5, price=None, vat_rate=None))
        product = self.product(5)
        self.assertEqual(product.list_price, 0.0)
        self.assertTrue(product.sale_ok)
        self.assertTrue(product.available_in_pos)
        self.assertEqual(product.taxes_id, self.tax0)

    def test_second_push_updates(self):
        self.push_items(self.item_rec(6))
        product = self.product(6)
        self.push_items(self.item_rec(6, price=500.0, name="Přejmenováno", vat_rate=12.0))
        self.assertEqual(self.product(6), product)
        self.assertEqual(product.list_price, 500.0)
        self.assertEqual(product.name, "Přejmenováno")
        self.assertEqual(product.taxes_id, self.tax12)

    def test_odoo_master_keeps_price_and_tax(self):
        self.push_items(self.item_rec(7))
        product = self.product(7)
        self.env["ir.config_parameter"].sudo().set_param("elite_vet_sale.winvet_master", "0")
        self.push_items(self.item_rec(7, price=999.0, vat_rate=12.0))
        self.assertEqual(product.list_price, 450.0)
        self.assertEqual(product.taxes_id, self.tax21)
        # a missing product is still created
        self.push_items(self.item_rec(8, price=77.0))
        self.assertEqual(self.product(8).list_price, 77.0)

    def test_archived_item_archives_product(self):
        self.push_items(self.item_rec(9))
        product = self.product(9)
        self.push_items(self.item_rec(9, active=False))
        self.assertFalse(product.active)
        self.push_items(self.item_rec(9, active=True))
        self.assertTrue(product.active)

    def test_inactive_new_item_creates_no_product(self):
        self.push_items(self.item_rec(10, active=False))
        self.assertFalse(self.item(10).product_id)

    def test_barcode_collision(self):
        self.push_items(self.item_rec(11, "product", barcode="8590000000110"),
                        self.item_rec(12, "product", barcode="8590000000110"))
        self.assertEqual(self.product(11).barcode, "8590000000110")
        self.assertTrue(self.product(12))
        self.assertFalse(self.product(12).barcode)

    def test_bad_item_does_not_stop_batch(self):
        from unittest.mock import patch
        Item = type(self.Item)
        original = Item._sync_product

        def flaky(rec):
            if rec.code == "P13":
                raise ValueError("boom")
            return original(rec)

        with patch.object(Item, "_sync_product", flaky), self.assertLogs(level="WARNING"):
            res = self.push_items(self.item_rec(13), self.item_rec(14))
        self.assertFalse(self.item(13).product_id)
        self.assertTrue(self.product(14))
        status = self.env["elite.vet.winvet.status"].get_status()
        self.assertIn("boom", status.last_error or "")

    def test_sync_products_for_existing_items(self):
        item = self.Item.create({"winvet_ref": BASE + 5900, "code": "P90", "name": "Starší položka",
                                 "classification": "service", "price": 10.0, "vat_rate": 21.0})
        self.assertFalse(item.product_id)
        item._sync_products()
        self.assertEqual(item.product_id.list_price, 10.0)

    def test_archive_via_drop_archives_product(self):
        self.push_items(self.item_rec(15))
        product = self.product(15)
        res = self.sync.push({"entity": "items", "mode": "incremental", "records": [],
                              "deleted": [BASE + 5015], "batch": 1, "batches": 1, "run_id": "t3"})
        self.assertTrue(res["ok"])
        self.assertFalse(self.item(15).active)
        self.assertFalse(product.active)
