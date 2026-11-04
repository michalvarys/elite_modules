import csv

from odoo.exceptions import UserError
from odoo.tools.misc import file_path
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestTrafikaPosSetup(TransactionCase):
    """Runs in a database with the company "Elite Trafika", alone or as a branch (see README, Testy)."""

    def setUp(self):
        super().setUp()
        self.setup = self.env["elite.trafika.pos.setup"]
        self.company = self.setup.target_company("Elite Trafika")
        self.root = self.company.root_id  # the company itself, or the company of which it is a branch
        self.tax = self.setup.sale_tax(self.root)
        self.tax_12 = self.setup.sale_tax(self.root, 12.0)
        with open(file_path("elite_trafika_pos/zbozi.csv"), encoding="utf-8") as f:
            self.listed = {row["xmlid"]: row for row in csv.DictReader(f)}

    def test_company_is_czech(self):
        for company in self.root | self.company:
            self.assertEqual(company.chart_template, "cz", company.name)
            self.assertEqual(company.currency_id, self.env.ref("base.CZK"), company.name)
            self.assertTrue(company.account_sale_tax_id, company.name)
        self.assertEqual(self.root.account_price_include, "tax_included")

    def test_sale_taxes_are_price_included(self):
        for tax, rate in ((self.tax, 21.0), (self.tax_12, 12.0)):
            self.assertEqual(tax.amount, rate)
            self.assertEqual(tax.type_tax_use, "sale")
            self.assertEqual(tax.company_id, self.root)
            self.assertTrue(tax.price_include)

    def test_products(self):
        """Every product of zbozi.csv (the Dotykačka export) exists with its price, VAT rate and barcode."""
        products = self.setup._module_products()
        self.assertEqual(len(products), len(self.listed))
        for xmlid, row in self.listed.items():
            product = self.env.ref("elite_trafika_pos.%s" % xmlid)
            self.assertEqual(product.name, row["název"])
            self.assertAlmostEqual(product.list_price, float(row["cena"]), msg=product.name)
            self.assertEqual(product.taxes_id, self.tax_12 if row["dph"] == "12" else self.tax, product.name)
            self.assertEqual(product.barcode or "", row["ean"], product.name)
            self.assertEqual(product.company_id, self.company, product.name)
            self.assertTrue(product.available_in_pos, product.name)
            self.assertTrue(product.is_storable, product.name)
            self.assertEqual(product.pos_categ_ids.name, row["skupina"], product.name)

    def test_price_is_final_price(self):
        """166 Kč at the till = 166 Kč total, of which the 21 % VAT is included."""
        product = self.env.ref("elite_trafika_pos.product_3247546801968706")  # MARLBORO RED crafted
        res = product.taxes_id.compute_all(product.list_price, product=product.product_variant_id)
        self.assertAlmostEqual(res["total_included"], 166.0)
        self.assertAlmostEqual(res["total_excluded"], 137.19, places=2)

    def test_pos_config(self):
        config = self.env.ref("elite_trafika_pos.pos_config_trafika")
        self.assertEqual(config.company_id, self.company)
        self.assertEqual(set(config.payment_method_ids.mapped("name")), {"Hotově", "Kartou"})
        self.assertEqual(config.payment_method_ids.company_id, self.company)
        for journal in config.payment_method_ids.journal_id | config.invoice_journal_id:
            self.assertIn(journal.company_id, self.root | self.company, journal.name)
        self.assertEqual(config.invoice_journal_id.type, "sale")
        self.assertEqual(config.picking_type_id.warehouse_id.company_id, self.company)
        self.assertTrue(config.limit_categories)
        self.assertEqual(len(config.iface_available_categ_ids), 35)

    def test_setup_is_repeatable(self):
        models = ("pos.payment.method", "pos.config", "account.tax", "account.journal", "stock.warehouse")
        counts = [self.env[m].search_count([]) for m in models]
        reduced = [self.env.ref("elite_trafika_pos.%s" % x).id for x, row in self.listed.items() if row["dph"] == "12"]
        self.setup.ensure_setup({"company": "Elite Trafika", "pos_name": "Elite Trafika", "reduced_vat": reduced})
        self.assertEqual([self.env[m].search_count([]) for m in models], counts)

    def test_missing_barcodes_are_added(self):
        """A product installed without its EAN gets it on the next run; a barcode set in Odoo stays."""
        coke = self.env.ref("elite_trafika_pos.product_3247546801968706").product_variant_id
        other = self.env.ref("elite_trafika_pos.product_3216940881868041").product_variant_id
        ean = coke.barcode
        coke.barcode = False
        other.barcode = "1234567890128"
        self.setup.ensure_setup({"company": "Elite Trafika", "pos_name": "Elite Trafika"})
        self.assertEqual(coke.barcode, ean)
        self.assertEqual(other.barcode, "1234567890128")

    def test_images(self):
        products = self.setup._module_products()
        self.assertEqual(len(products), 506)
        self.assertFalse(products.filtered(lambda p: not p.image_1920).mapped("name"))
        categories = self.setup._module_records("pos.category")
        self.assertEqual(len(categories), 35)
        self.assertFalse(categories.filtered(lambda c: not c.image_128).mapped("name"))

    def test_existing_image_is_kept(self):
        product = self.setup._module_products()[0]
        category = self.setup._module_records("pos.category")[0]
        product.image_1920 = category.image_128
        image, category_image = product.image_1920, category.image_128
        self.setup._ensure_images()
        self.assertEqual(product.image_1920, image)
        self.assertEqual(category.image_128, category_image)

    def test_unknown_company_stops(self):
        with self.assertRaises(UserError):
            self.setup.ensure_setup({"company": "Neexistující firma"})
