from unittest.mock import patch

from odoo.exceptions import AccessError
from odoo.tests import new_test_user, tagged

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

    def test_plain_cashier_can_print(self):
        """A cashier has no rights to accounting records, which Odoo's sale details read."""
        cashier = new_test_user(
            self.env, login="elite_cashier", groups="base.group_user,point_of_sale.group_pos_user",
            company_id=self.company.id, company_ids=self.company.ids,
        )
        data = self.pos_session.with_user(cashier).get_elite_closing_receipt()
        self.assertAlmostEqual(data["total"], 363)
        self.assertAlmostEqual(data["cash"]["expected"], 221)

    def test_user_without_pos_access_is_refused(self):
        stranger = new_test_user(
            self.env, login="elite_stranger", groups="base.group_user",
            company_id=self.company.id, company_ids=self.company.ids,
        )
        with self.assertRaises(AccessError):
            self.pos_session.with_user(stranger).get_elite_closing_receipt()

    def test_older_odoo_without_payments_per_method(self):
        """Older Odoo 18 builds return no "payments_per_method" in the sale details."""
        report = type(self.env["report.point_of_sale.report_saledetails"])
        original = report.get_sale_details

        def older(self_report, *args, **kwargs):
            details = original(self_report, *args, **kwargs)
            details.pop("payments_per_method", None)
            return details

        with patch.object(report, "get_sale_details", older):
            data = self.pos_session.get_elite_closing_receipt()
        payments = {p["name"]: p["total"] for p in data["payments"]}
        self.assertAlmostEqual(payments[self.cash_pm1.name], 121)
        self.assertAlmostEqual(payments[self.bank_pm1.name], 242)

    def _close(self, counted):
        self.pos_session.post_closing_cash_details(counted)
        self.pos_session.close_session_from_ui()
        self.assertEqual(self.pos_session.state, "closed")

    def test_closed_session_shows_counted_cash_and_difference(self):
        # 100 opening + 121 cash sales = 221 expected; the cashier counts 211 (10 short).
        self._close(211)
        cash = self.pos_session.get_elite_closing_receipt()["cash"]
        self.assertAlmostEqual(cash["opening"], 100)
        self.assertAlmostEqual(cash["payments"], 121)
        self.assertEqual(cash["moves"], [], "the counting difference is not a cash move")
        self.assertAlmostEqual(cash["expected"], 221)
        self.assertAlmostEqual(cash["counted"], 211)
        self.assertAlmostEqual(cash["difference"], -10)

    def test_cash_moves_survive_closing(self):
        self.pos_session.try_cash_in_out("in", 50, "drobne", {"translatedType": "in"})
        before = self.pos_session.get_elite_closing_receipt()["cash"]
        self.assertAlmostEqual(before["expected"], 271)
        self._close(271)
        after = self.pos_session.get_elite_closing_receipt()["cash"]
        self.assertEqual(after["moves"], before["moves"])
        self.assertAlmostEqual(after["expected"], 271)
        self.assertAlmostEqual(after["expected"], self.pos_session.cash_register_balance_end)
        self.assertAlmostEqual(after["difference"], 0)

    def test_open_session_has_no_counted_cash(self):
        cash = self.pos_session.get_elite_closing_receipt()["cash"]
        self.assertNotIn("counted", cash)

    def test_reprint_from_back_office(self):
        self._close(221)
        cashier = new_test_user(
            self.env, login="elite_cashier_reprint", groups="base.group_user,point_of_sale.group_pos_user",
            company_id=self.company.id, company_ids=self.company.ids,
        )
        html, _type = self.env["ir.actions.report"].with_user(cashier)._render_qweb_html(
            "elite_pos_closing_receipt.report_closing_receipt", self.pos_session.ids
        )
        html = html.decode()
        self.assertIn("Uzávěrka", html)
        self.assertIn(self.pos_session.name, html)
        self.assertIn("Uzavřena", html)
        self.assertIn("Spočítáno", html)
        self.assertIn("Drink", html)
        # One .article per session: without it the PDF loses the UTF-8 layout (garbled Czech).
        self.assertIn('class="article elite-cr"', html)

    def test_print_action_opens_browser_print(self):
        action = self.pos_session.action_print_elite_closing_receipt()
        self.assertEqual(action["tag"], "elite_pos_closing_receipt.print")
        self.assertEqual(action["params"]["session_ids"], self.pos_session.ids)
        report = self.env.ref("elite_pos_closing_receipt.action_report_closing_receipt")
        self.assertFalse(report.binding_model_id, "the Print menu uses the print action, not the PDF report")
