from odoo.exceptions import AccessError
from odoo.tests import tagged

from .common import ReceptionCase

RECEPTION = "elite_vet_reservation.group_reservation_reception"
NURSE = "elite_vet_clinic.group_clinic_nurse"
MANAGER = "elite_vet_reservation.group_reservation_manager"


@tagged("post_install", "-at_install")
class TestRoles(ReceptionCase):
    """Role home screens, pruned menus and POS employee login (Task 4)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.pos_action = cls.env.ref("elite_vet_reception.action_open_reception_pos")
        cls.card_action = cls.env.ref("elite_vet_clinic.action_patient_card")
        cls.dashboard_action = cls.env.ref("elite_vet_winvet.action_winvet_dashboard")
        cls.custom_action = cls.env.ref("elite_vet_clinic.action_clinical_record")

    def new_user(self, login, *groups):
        return self.env["res.users"].with_context(no_reset_password=True).create({
            "name": "Role %s" % login, "login": login, "email": "%s@example.invalid" % login,
            "groups_id": [(6, 0, [self.env.ref("base.group_user").id] + [self.env.ref(g).id for g in groups])]})

    def visible(self, user):
        return self.env["ir.ui.menu"].with_user(user)._visible_menu_ids()

    # ------------------------------------------------------------------ home screens

    def test_home_action_per_role(self):
        expected = {self.reception: self.pos_action, self.nurse: self.card_action,
                    self.doctor_user: self.card_action, self.manager: self.dashboard_action}
        for user, action in expected.items():
            with self.subTest(user=user.login):
                self.assertEqual(user._elite_vet_home_action().id, action.id)
                self.assertEqual(user.action_id.id, action.id)

    def test_reception_action_opens_recepce_till(self):
        self.assertEqual(self.pos_action.type, "ir.actions.act_url")
        self.assertEqual(self.pos_action.target, "self")
        self.assertEqual(self.pos_action.url, "/pos/ui?config_id=%d" % self.pos_config.id)

    def test_home_action_follows_role_change(self):
        user = self.new_user("role_change_test")
        self.assertFalse(user.action_id)
        user.write({"groups_id": [(4, self.env.ref(RECEPTION).id)]})
        self.assertEqual(user.action_id.id, self.pos_action.id)
        user.write({"groups_id": [(4, self.env.ref(NURSE).id)]})
        self.assertEqual(user.action_id.id, self.card_action.id)
        user.write({"groups_id": [(4, self.env.ref(MANAGER).id)]})
        self.assertEqual(user.action_id.id, self.dashboard_action.id)

    def test_custom_home_action_kept(self):
        user = self.new_user("role_custom_test", RECEPTION)
        user.action_id = self.custom_action.id
        user.write({"groups_id": [(4, self.env.ref(NURSE).id)]})
        self.assertEqual(user.action_id.id, self.custom_action.id)
        self.env.ref("elite_vet_reception.action_set_home_actions").with_context(
            active_model="res.users", active_ids=user.ids).run()
        self.assertEqual(user.action_id.id, self.custom_action.id)

    def test_set_home_actions_button(self):
        users = self.nurse | self.reception
        users.write({"action_id": False})
        server_action = self.env.ref("elite_vet_reception.action_set_home_actions")
        self.assertIn(self.env.ref(MANAGER), server_action.groups_id)
        self.assertEqual(server_action.binding_model_id.model, "res.users")
        result = server_action.with_user(self.manager).with_context(
            active_model="res.users", active_ids=self.nurse.ids).run()
        self.assertEqual(self.nurse.action_id.id, self.card_action.id)
        # Applies to all users, not only the selected ones.
        self.assertEqual(self.reception.action_id.id, self.pos_action.id)
        self.assertEqual(result["tag"], "display_notification")

    def test_set_home_actions_only_for_managers(self):
        with self.assertRaises(AccessError):
            self.env["res.users"].with_user(self.doctor_user).action_elite_vet_set_home_actions()

    # ------------------------------------------------------------------ menus

    def test_reception_menus(self):
        visible = self.visible(self.reception)
        self.assertIn(self.env.ref("point_of_sale.menu_point_root").id, visible)
        self.assertIn(self.env.ref("elite_vet_web.menu_rezervace_root").id, visible)
        for xmlid in ("sale.sale_menu_root", "account.menu_finance", "stock.menu_stock_root",
                      "elite_vet_winvet.menu_winvet_root", "hr.menu_hr_root",
                      "elite_vet_calendar.menu_rozpis_root", "elite_vet_clinic.menu_clinic_root"):
            with self.subTest(menu=xmlid):
                self.assertNotIn(self.env.ref(xmlid).id, visible)
        # Items of a hidden app are not loaded in the web client (the menu tree starts at the
        # visible roots; _visible_menu_ids alone does not check the parents).
        loaded = self.env["ir.ui.menu"].with_user(self.reception).load_menus(False)
        for xmlid in ("elite_vet_sale.menu_stock_overview_clinic", "elite_vet_sale.menu_goods_receipt_clinic",
                      "elite_vet_clinic.menu_patient_card"):
            with self.subTest(loaded=xmlid):
                self.assertNotIn(self.env.ref(xmlid).id, loaded)
        self.assertIn(self.env.ref("elite_vet_reservation.menu_reservation_board").id, loaded)

    def test_only_management_sees_website_dashboards_apps(self):
        hidden = ("website.menu_website_configuration", "spreadsheet_dashboard.spreadsheet_dashboard_menu_root",
                  "base.menu_management")
        for user in (self.reception, self.nurse, self.doctor_user):
            visible = self.visible(user)
            with self.subTest(user=user.login):
                for xmlid in hidden:
                    self.assertNotIn(self.env.ref(xmlid).id, visible, xmlid)
                self.assertIn(self.env.ref("mail.menu_root_discuss").id, visible)
        visible = self.visible(self.manager)
        for xmlid in ("website.menu_website_configuration", "spreadsheet_dashboard.spreadsheet_dashboard_menu_root"):
            self.assertIn(self.env.ref(xmlid).id, visible, xmlid)

    def test_existing_users_get_home_action_on_update(self):
        user = self.new_user("role_update_test", RECEPTION)
        custom = self.new_user("role_update_custom_test", RECEPTION)
        custom.action_id = self.custom_action.id
        self.env.cr.execute("UPDATE res_users SET action_id = NULL WHERE id = %s", [user.id])
        user.invalidate_recordset(["action_id"])
        self.env["res.users"]._elite_vet_apply_home_actions_all()
        self.assertEqual(user.action_id.id, self.pos_action.id)
        self.assertEqual(custom.action_id.id, self.custom_action.id)

    def test_nurse_and_doctor_menus(self):
        stock_root = self.env.ref("stock.menu_stock_root")
        overview = self.env.ref("elite_vet_sale.menu_stock_overview")
        receipt = self.env.ref("elite_vet_sale.menu_goods_receipt_stock")
        self.assertEqual(receipt.parent_id, stock_root)
        self.assertEqual(receipt.sequence, overview.sequence + 1)
        others = self.env["ir.ui.menu"].with_context(**{"ir.ui.menu.full_list": True}).search(
            [("parent_id", "=", stock_root.id), ("id", "not in", (overview | receipt).ids)])
        self.assertTrue(others)
        for user in (self.nurse, self.doctor_user):
            visible = self.visible(user)
            with self.subTest(user=user.login):
                for xmlid in ("stock.menu_stock_root", "elite_vet_sale.menu_stock_overview",
                              "elite_vet_sale.menu_goods_receipt_stock", "elite_vet_sale.menu_goods_receipt_clinic",
                              "elite_vet_sale.menu_stock_overview_clinic", "elite_vet_clinic.menu_clinic_root",
                              "point_of_sale.menu_point_root", "elite_vet_web.menu_rezervace_root"):
                    self.assertIn(self.env.ref(xmlid).id, visible, xmlid)
                self.assertFalse(set(others.ids) & visible, others.filtered(lambda m: m.id in visible).mapped("name"))
                for xmlid in ("sale.sale_menu_root", "account.menu_finance", "elite_vet_winvet.menu_winvet_root",
                              "hr.menu_hr_root", "elite_vet_calendar.menu_rozpis_root"):
                    self.assertNotIn(self.env.ref(xmlid).id, visible, xmlid)

    def test_manager_menus(self):
        visible = self.visible(self.manager)
        for xmlid in ("account.menu_finance", "stock.menu_stock_root", "stock.menu_stock_warehouse_mgmt",
                      "elite_vet_winvet.menu_winvet_root", "hr.menu_hr_root", "elite_vet_calendar.menu_rozpis_root",
                      "point_of_sale.menu_point_root", "elite_vet_clinic.menu_clinic_root"):
            with self.subTest(menu=xmlid):
                self.assertIn(self.env.ref(xmlid).id, visible)
        # The Sales root may be archived (sale_management activates it); its groups are manager only.
        self.assertEqual(self.env.ref("sale.sale_menu_root").groups_id, self.env.ref(MANAGER))

    def test_role_menus_survive_reapply(self):
        self.env["ir.ui.menu"]._elite_vet_apply_role_menus()
        self.env["ir.ui.menu"]._elite_vet_apply_role_menus()
        self.assertEqual(self.env.ref("account.menu_finance").groups_id, self.env.ref(MANAGER))
        self.assertEqual(self.env.ref("point_of_sale.menu_point_root").groups_id, self.env.ref(RECEPTION))

    # ------------------------------------------------------------------ POS employees

    def close_open_sessions(self):
        """ev_test may hold a till session opened by browser checks; close it inside the test."""
        self.pos_config.session_ids.filtered(lambda s: s.state != "closed").write({"state": "closed"})

    def test_recepce_has_employee_login(self):
        self.close_open_sessions()
        if self.pos_config.module_pos_hr:
            self.pos_config.module_pos_hr = False
        self.env["elite.vet.sale.setup"].ensure_setup()
        self.assertTrue(self.pos_config.module_pos_hr)

    def test_employee_login_not_forced_during_open_session(self):
        self.close_open_sessions()
        self.pos_config.module_pos_hr = False
        self.pos_session()
        with self.assertLogs("odoo.addons.elite_vet_reception.models.setup", level="WARNING"):
            self.env["elite.vet.sale.setup"].ensure_setup()
        self.assertFalse(self.pos_config.module_pos_hr)

    def test_manager_can_create_employees(self):
        employee = self.env["hr.employee"].with_user(self.manager).create({"name": "Recepční Testová PIN", "pin": "4321"})
        self.assertEqual(employee.pin, "4321")

    def test_reception_tabs_only_in_recepce_till(self):
        """The POS loads `is_elite_vet_reception` with the config: tabs and Dnes only in Recepce."""
        self.assertTrue(self.pos_config.is_elite_vet_reception)
        other = self.env["pos.config"].create({"name": "Jiná pokladna test recepce"})
        self.assertFalse(other.is_elite_vet_reception)
        self.assertIn("is_elite_vet_reception", self.pos_config._load_pos_data_fields(self.pos_config.id) or
                      self.pos_config.fields_get())
