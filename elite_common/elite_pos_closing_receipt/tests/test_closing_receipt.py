from odoo.tests import tagged

from odoo.addons.point_of_sale.tests.common import TestPoSCommon


@tagged("post_install", "-at_install")
class TestClosingReceipt(TestPoSCommon):

    def setUp(self):
        super().setUp()
        self.config = self.basic_config
        tax = self.taxes["tax21"]  # 21 %, price includes tax
        self.drink = self.create_product("Drink", self.categ_basic, 121.0, tax_ids=tax.ids)
        self.snack = self.create_product("Snack", self.categ_basic, 242.0, tax_ids=tax.ids)
        self.open_new_session(opening_cash=100)
        self._create_orders([
            {"pos_order_lines_ui_args": [(self.drink, 2)], "payments": [(self.cash_pm1, 242)]},
            {"pos_order_lines_ui_args": [(self.snack, 1)], "payments": [(self.bank_pm1, 242)]},
            {"pos_order_lines_ui_args": [(self.drink, -1)], "payments": [(self.cash_pm1, -121)]},
        ])

    def test_totals_and_payments(self):
        data = self.pos_session.get_elite_closing_receipt()
        self.assertEqual(data["orders"], 3)
        self.assertAlmostEqual(data["total"], 363)
        payments = {p["name"]: p["total"] for p in data["payments"]}
        self.assertAlmostEqual(payments[self.cash_pm1.name], 121)
        self.assertAlmostEqual(payments[self.bank_pm1.name], 242)
        self.assertEqual(data["config"], self.config.name)
        self.assertEqual(data["session"], self.pos_session.name)

    def test_cash_in_register(self):
        cash = self.pos_session.get_elite_closing_receipt()["cash"]
        self.assertAlmostEqual(cash["opening"], 100)
        self.assertAlmostEqual(cash["payments"], 121)
        self.assertAlmostEqual(cash["expected"], 221)

    def test_vat_is_net_of_refunds(self):
        vat = self.pos_session.get_elite_closing_receipt()["vat"]
        self.assertEqual(len(vat), 1)
        self.assertAlmostEqual(vat[0]["base"], 300)
        self.assertAlmostEqual(vat[0]["tax"], 63)
        self.assertAlmostEqual(vat[0]["total"], 363)

    def test_refunds_and_categories(self):
        data = self.pos_session.get_elite_closing_receipt()
        self.assertEqual(data["refunds"]["qty"], -1)
        self.assertAlmostEqual(data["refunds"]["total"], -121)
        self.assertEqual(data["discounts"]["count"], 0)
        products = {p["name"]: p for c in data["categories"] for p in c["products"]}
        self.assertEqual(products["Drink"]["qty"], 2)
        self.assertAlmostEqual(products["Drink"]["total"], 242)
        self.assertAlmostEqual(products["Snack"]["total"], 242)
        self.assertAlmostEqual(sum(c["total"] for c in data["categories"]), 484)
