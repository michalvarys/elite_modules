from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestArenaPosSetup(TransactionCase):
    """Runs in a database with the company "Elite Arena" (see README, Testy)."""

    def setUp(self):
        super().setUp()
        self.setup = self.env["elite.arena.pos.setup"]
        self.company = self.setup.target_company("Elite Arena")
        self.tax = self.setup.sale_tax(self.company)
        self.tax_12 = self.setup.sale_tax(self.company, 12.0)
        # food; every drink is 21 %, bottled water included
        self.reduced = {"16040", "16039", "16038", "16037", "16036", "16077", "16060", "16043", "16042",
                        "16076", "16062", "16069", "16078", "16075", "16041", "16061", "16068", "16067",
                        "16059", "16066"}

    def test_company_is_czech(self):
        self.assertEqual(self.company.chart_template, "cz")
        self.assertEqual(self.company.currency_id, self.env.ref("base.CZK"))
        self.assertTrue(self.company.account_sale_tax_id)

    def test_other_companies_untouched(self):
        others = self.env["res.company"].search([("id", "!=", self.company.id)])
        self.assertTrue(others)
        for company in others:
            self.assertFalse(company.chart_template, company.name)
            self.assertFalse(self.env["account.journal"].search_count([("company_id", "=", company.id)]),
                             company.name)

    def test_sale_taxes_are_price_included(self):
        for tax, rate in ((self.tax, 21.0), (self.tax_12, 12.0)):
            self.assertEqual(tax.amount, rate)
            self.assertEqual(tax.type_tax_use, "sale")
            self.assertEqual(tax.company_id, self.company)
            self.assertTrue(tax.price_include)

    def test_products(self):
        products = self.setup._module_products()
        self.assertEqual(len(products), 57)
        for product in products:
            expected = self.tax_12 if product.default_code in self.reduced else self.tax
            self.assertEqual(product.taxes_id, expected, product.name)
            self.assertEqual(product.company_id, self.company, product.name)
            self.assertTrue(product.available_in_pos, product.name)
            self.assertTrue(product.pos_categ_ids, product.name)
        coke = self.env.ref("elite_arena_pos.product_16015")
        self.assertEqual(coke.list_price, 55.0)
        self.assertTrue(coke.is_storable)
        self.assertTrue(coke.image_1920)
        self.assertEqual(self.env.ref("elite_arena_pos.product_16052").type, "service")

    def test_price_is_final_price(self):
        """55 Kč at the till = 55 Kč total, of which the 21 % VAT is included."""
        coke = self.env.ref("elite_arena_pos.product_16015")
        res = coke.taxes_id.compute_all(coke.list_price, product=coke.product_variant_id)
        self.assertAlmostEqual(res["total_included"], 55.0)
        self.assertAlmostEqual(res["total_excluded"], 45.45, places=2)

    def test_pos_config(self):
        config = self.env.ref("elite_arena_pos.pos_config_arena")
        self.assertEqual(config.company_id, self.company)
        self.assertEqual(set(config.payment_method_ids.mapped("name")), {"Hotově", "Kartou"})
        self.assertEqual(config.payment_method_ids.journal_id.company_id, self.company)
        self.assertEqual(config.invoice_journal_id.company_id, self.company)
        self.assertEqual(config.invoice_journal_id.type, "sale")
        self.assertEqual(config.picking_type_id.warehouse_id.company_id, self.company)
        self.assertTrue(config.limit_categories)

    def test_setup_is_repeatable(self):
        models = ("pos.payment.method", "pos.config", "account.tax", "account.journal")
        counts = [self.env[m].search_count([]) for m in models]
        self.setup.ensure_setup({"company": "Elite Arena", "pos_name": "Elite Arena",
                                 "reduced_vat": self.setup._module_products().filtered(
                                     lambda p: p.default_code in self.reduced).ids})
        self.assertEqual([self.env[m].search_count([]) for m in models], counts)

    def test_unknown_company_stops(self):
        with self.assertRaises(UserError):
            self.setup.ensure_setup({"company": "Neexistující firma"})
