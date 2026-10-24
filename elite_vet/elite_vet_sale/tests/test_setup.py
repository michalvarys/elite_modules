from unittest.mock import patch

from odoo.tests import tagged

from .common import SaleCase


@tagged("post_install", "-at_install")
class TestSetup(SaleCase):

    def test_company_accounting(self):
        self.assertEqual(self.company.currency_id, self.env.ref("base.CZK"))
        self.assertEqual(self.company.country_id, self.env.ref("base.cz"))
        self.assertEqual(self.company.chart_template, "cz")
        self.assertEqual(self.company.account_price_include, "tax_included")

    def test_country_currency_only_without_posted_moves(self):
        Setup = type(self.setup)
        usd = self.env.ref("base.USD")
        other = self.env["res.company"].create({"name": "Pobočka testovací", "currency_id": usd.id})
        with patch.object(Setup, "_has_posted_moves", lambda self, company: True), \
                self.assertLogs("odoo.addons.elite_vet_sale.models.setup", "WARNING"):
            self.setup._ensure_country_currency(other)
        self.assertEqual(other.currency_id, usd)
        self.assertFalse(other.country_id)
        self.setup._ensure_country_currency(other)
        self.assertEqual(other.currency_id, self.env.ref("base.CZK"))
        self.assertEqual(other.country_id, self.env.ref("base.cz"))

    def test_tax_for_rate(self):
        self.assertEqual(self.tax21.amount, 21)
        self.assertEqual(self.tax21.type_tax_use, "sale")
        self.assertTrue(self.tax21.price_include)
        self.assertAlmostEqual(self.tax21.compute_all(121.0)["total_excluded"], 100.0)
        self.assertEqual(self.tax12.amount, 12)
        self.assertTrue(self.tax12.price_include)
        self.assertEqual(self.tax0.amount, 0)
        self.assertEqual(self.tax0.type_tax_use, "sale")
        # Same tax on repeated lookup, integer and float rate alike.
        self.assertEqual(self.setup.tax_for_rate(21.0), self.tax21)

    def test_tax_for_unknown_rate_is_created_once(self):
        tax = self.setup.tax_for_rate(15)
        self.assertEqual(tax.amount, 15)
        self.assertEqual(tax.type_tax_use, "sale")
        self.assertEqual(tax.name, "15 % DPH (cena s DPH)")
        self.assertTrue(tax.price_include)
        self.assertAlmostEqual(tax.compute_all(115.0)["total_excluded"], 100.0)
        self.assertEqual(self.setup.tax_for_rate(15), tax)

    def test_ensure_setup_is_idempotent(self):
        PaymentMethod = self.env["pos.payment.method"]
        configs = self.env["pos.config"].search_count([])
        methods = PaymentMethod.search_count([])
        taxes = self.env["account.tax"].search_count([])
        self.setup.ensure_setup()
        self.setup.ensure_setup()
        self.assertEqual(self.env["pos.config"].search_count([]), configs)
        self.assertEqual(PaymentMethod.search_count([]), methods)
        self.assertEqual(self.env["account.tax"].search_count([]), taxes)
        self.assertEqual(self.setup.pos_config(), self.pos_config)

    def test_pos_config(self):
        config = self.pos_config
        self.assertEqual(config, self.env.ref("elite_vet_sale.pos_config_reception"))
        self.assertEqual(config.name, "Recepce")
        methods = {m.name: m for m in config.payment_method_ids}
        self.assertEqual(set(methods), {"Hotově", "Kartou", "Převodem"})
        self.assertEqual(methods["Hotově"].journal_id.type, "cash")
        self.assertTrue(methods["Hotově"].is_cash_count)
        for name in ("Kartou", "Převodem"):
            self.assertEqual(methods[name].journal_id.type, "bank")
            self.assertFalse(methods[name].use_payment_terminal)
        self.assertEqual(config.invoice_journal_id.type, "sale")
        self.assertEqual(config.currency_id, self.env.ref("base.CZK"))
        picking_type = config.picking_type_id
        self.assertEqual(picking_type.code, "outgoing")
        self.assertFalse(picking_type.use_existing_lots)
        self.assertFalse(picking_type.use_create_lots)

    def test_ensure_setup_with_open_till(self):
        config = self.pos_config
        transfer = config.payment_method_ids.filtered(lambda m: m.name == "Převodem")
        self.assertTrue(self.pos_session())
        config.with_context(bypass_payment_method_ids_forbidden_change=True).write(
            {"payment_method_ids": [(3, transfer.id)]})
        with self.assertLogs("odoo.addons.elite_vet_sale.models.setup", "WARNING") as logs:
            self.setup.ensure_setup()
        self.assertIn("payment methods not added", logs.output[0])
        self.assertNotIn(transfer, config.payment_method_ids)

    def test_stock_fefo(self):
        warehouse = self.env["stock.warehouse"].search([("company_id", "=", self.company.id)], limit=1)
        self.assertEqual(warehouse.lot_stock_id.removal_strategy_id, self.env.ref("product_expiry.removal_fefo"))
        self.assertEqual(self.pos_config.picking_type_id.default_location_src_id, warehouse.lot_stock_id)

    def test_free_product(self):
        product = self.setup.free_product()
        self.assertEqual(product, self.env.ref("elite_vet_sale.product_free_line"))
        self.assertEqual(product.name, "Volná položka")
        self.assertEqual(product.type, "service")
        self.assertTrue(product.available_in_pos)
        self.assertTrue(product.sale_ok)
        self.assertEqual(product.taxes_id, self.tax21)

    def test_winvet_master(self):
        Param = self.env["ir.config_parameter"].sudo()
        self.assertTrue(self.setup.is_winvet_master())
        Param.set_param("elite_vet_sale.winvet_master", "0")
        self.assertFalse(self.setup.is_winvet_master())
        Param.set_param("elite_vet_sale.winvet_master", "1")
        self.assertTrue(self.setup.is_winvet_master())

    def test_role_groups(self):
        """Task 14: only Recepce (the till group) and Vedení have the POS, sale and stock."""
        till = self.env.ref("elite_vet_sale.group_till_stock")
        for group in ("point_of_sale.group_pos_user", "sales_team.group_sale_salesman_all_leads",
                      "stock.group_stock_user"):
            self.assertIn(self.env.ref(group), till.implied_ids, group)
        self.assertIn(till, self.reception.groups_id)
        for group in ("point_of_sale.group_pos_user", "sales_team.group_sale_salesman", "stock.group_stock_user"):
            self.assertTrue(self.reception.has_group(group), group)
        self.assertFalse(self.reception.has_group("point_of_sale.group_pos_manager"))
        self.assertFalse(self.reception.has_group("stock.group_stock_manager"))
        for user in (self.nurse, self.doctor_user):
            for group in ("elite_vet_sale.group_till_stock", "point_of_sale.group_pos_user",
                          "sales_team.group_sale_salesman", "stock.group_stock_user"):
                self.assertFalse(user.has_group(group), (user.login, group))
        for group in ("elite_vet_sale.group_till_stock", "point_of_sale.group_pos_manager",
                      "stock.group_stock_manager", "sales_team.group_sale_manager"):
            self.assertTrue(self.manager.has_group(group), group)

    def test_role_chain_without_till(self):
        """The role groups no longer imply the POS, sale or stock groups (removed on upgrade)."""
        rights = self.env["res.users"]._elite_vet_till_rights()
        for xmlid in ("elite_vet_reservation.group_reservation_reception", "elite_vet_clinic.group_clinic_nurse",
                      "elite_vet_clinic.group_clinic_doctor"):
            group = self.env.ref(xmlid)
            self.assertFalse(group.trans_implied_ids & rights, xmlid)
        till = self.env.ref("elite_vet_sale.group_till_stock")
        self.assertIn(till, self.env.ref("elite_vet_reservation.group_reservation_manager").trans_implied_ids)
        self.assertNotEqual(till.category_id, self.env.ref("elite_vet_reservation.group_reservation_reception").category_id)

    def test_old_role_links_removed_on_update(self):
        """Earlier versions linked Recepce -> salesman / POS and Sestra -> stock; the update removes them."""
        reception = self.env.ref("elite_vet_reservation.group_reservation_reception")
        nurse = self.env.ref("elite_vet_clinic.group_clinic_nurse")
        reception.implied_ids = [(4, self.env.ref("sales_team.group_sale_salesman").id),
                                 (4, self.env.ref("point_of_sale.group_pos_user").id)]
        nurse.implied_ids = [(4, self.env.ref("stock.group_stock_user").id)]
        self.env["res.groups"]._elite_vet_unlink_role_till_rights()
        rights = self.env["res.users"]._elite_vet_till_rights()
        self.assertFalse(reception.implied_ids & rights)
        self.assertFalse(nurse.implied_ids & rights)
        self.assertIn(self.env.ref("elite_vet_reservation.group_reservation_reception"), nurse.implied_ids)

    def test_reception_sees_quotations_of_others(self):
        quotation = self.env["sale.order"].with_user(self.manager).create({"partner_id": self.owner.id})
        self.assertEqual(quotation.user_id, self.manager)
        self.assertEqual(self.env["sale.order"].with_user(self.reception).search([("id", "=", quotation.id)]),
                         quotation)
        self.assertTrue(self.reception.has_group("sales_team.group_sale_salesman_all_leads"))
        self.assertFalse(self.reception.has_group("sales_team.group_sale_manager"))
