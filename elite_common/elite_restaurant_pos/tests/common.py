import datetime
from unittest.mock import patch

from odoo.tests import TransactionCase

from ..models import setup as setup_module


class RestaurantPosCase(TransactionCase):
    """Checks shared by the restaurant modules; a subclass sets MODULE, COMPANY, PARENT, PRODUCTS and
    looks at one food, one alcohol and one soft drink item of its menu (xml id suffixes)."""

    allow_inherited_tests_method = True  # Odoo runs only methods defined on the subclass otherwise
    MODULE = COMPANY = PARENT = None
    PRODUCTS = 0
    TABLES = 12  # tables created with the till
    FOOD = ALCOHOL = SOFT = None

    def setUp(self):
        super().setUp()
        self.setup = self.env["elite.restaurant.pos.setup"]
        self.company = self.env["res.company"].search([("name", "=", self.COMPANY)])
        self.root = self.company.root_id
        self.config = self.env.ref("%s.pos_config" % self.MODULE)

    def product(self, kod):
        return self.env.ref("%s.product_%s" % (self.MODULE, kod))

    def tax(self, rate):
        return self.setup.sale_tax(self.root, rate)

    def test_company(self):
        self.assertEqual(len(self.company), 1)
        self.assertEqual(self.company.parent_id.name or False, self.PARENT)
        self.assertEqual(self.root.chart_template, "cz")
        self.assertIn(self.company, self.env.ref("base.user_admin").company_ids)

    def test_products(self):
        products = self.setup._module_records(self.MODULE, "product.template")
        self.assertEqual(len(products), self.PRODUCTS)
        self.assertEqual(set(products.company_id), {self.company})
        self.assertTrue(all(products.mapped("available_in_pos")))
        self.assertTrue(all(products.mapped("pos_categ_ids")))

    def test_vat(self):
        self.assertEqual(self.product(self.FOOD).taxes_id, self.tax(12.0))
        self.assertEqual(self.product(self.ALCOHOL).taxes_id, self.tax(21.0))
        soft = self.product(self.SOFT)
        self.assertEqual(soft.taxes_id, self.tax(self.setup.soft_drink_rate()))
        self.assertIn(self.env.ref("elite_restaurant_pos.tag_soft_drink"), soft.product_tag_ids)
        self.assertTrue(self.tax(12.0).price_include and self.tax(21.0).price_include)

    def test_soft_drink_vat_from_2027(self):
        soft, alcohol = self.product(self.SOFT), self.product(self.ALCOHOL)
        self.setup._set_tax(soft, self.root, 21.0)
        cron = self.env.ref("elite_restaurant_pos.cron_soft_drink_vat")
        with patch.object(type(self.setup), "soft_drink_rate", lambda _self, day=None: 21.0):
            self.setup._cron_soft_drink_vat()
        self.assertEqual(soft.taxes_id, self.tax(21.0))
        self.assertTrue(cron.active)
        self.assertEqual(self.setup.soft_drink_rate(datetime.date(2026, 12, 31)), 21.0)
        self.assertEqual(self.setup.soft_drink_rate(setup_module.SOFT_DRINK_REDUCED_FROM), 12.0)
        with patch.object(type(self.setup), "soft_drink_rate", lambda _self, day=None: 12.0):
            self.setup._cron_soft_drink_vat()
        self.assertEqual(soft.taxes_id, self.tax(12.0))
        self.assertEqual(alcohol.taxes_id, self.tax(21.0))
        self.assertFalse(cron.active)

    def test_till(self):
        config = self.config
        self.assertEqual(config.company_id, self.company)
        self.assertTrue(config.module_pos_restaurant)
        self.assertEqual(len(config.floor_ids.table_ids), self.TABLES)
        self.assertEqual(set(config.payment_method_ids.mapped("name")), {"Hotově", "Kartou"})
        warehouse = config.picking_type_id.warehouse_id
        self.assertEqual(warehouse.company_id, self.company)
        self.assertTrue(config.limit_categories)
        self.assertFalse(config.iface_available_categ_ids.parent_id)

    def test_own_warehouse(self):
        others = self.env["pos.config"].search([("id", "!=", self.config.id), ("module_pos_restaurant", "=", True)])
        for other in others:
            self.assertNotEqual(other.picking_type_id.warehouse_id, self.config.picking_type_id.warehouse_id)

    def test_price_includes_vat(self):
        food = self.product(self.FOOD)
        res = food.taxes_id.compute_all(food.list_price, product=food.product_variant_id)
        self.assertAlmostEqual(res["total_included"], food.list_price)

    def test_setup_is_repeatable(self):
        models = ("res.company", "pos.config", "pos.payment.method", "account.journal", "stock.warehouse",
                  "restaurant.floor", "restaurant.table", "account.tax")
        counts = [self.env[m].search_count([]) for m in models]
        self.setup.ensure_setup(self.SETUP)
        self.assertEqual([self.env[m].search_count([]) for m in models], counts)
