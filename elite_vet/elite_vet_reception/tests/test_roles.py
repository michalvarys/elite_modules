from odoo.exceptions import AccessError
from odoo.tests import tagged

from .common import ReceptionCase

RECEPTION = "elite_vet_reservation.group_reservation_reception"
NURSE = "elite_vet_clinic.group_clinic_nurse"
DOCTOR = "elite_vet_clinic.group_clinic_doctor"
MANAGER = "elite_vet_reservation.group_reservation_manager"
TILL = "elite_vet_sale.group_till_stock"


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

    # ------------------------------------------------------------------ till group (task 14)

    def has_till(self, user):
        user.invalidate_recordset(["groups_id"])
        return self.env.ref(TILL) in user.groups_id

    def test_till_group_follows_role_change(self):
        user = self.new_user("role_till_test")
        self.assertFalse(self.has_till(user))
        user.write({"groups_id": [(4, self.env.ref(RECEPTION).id)]})
        self.assertTrue(self.has_till(user))
        self.assertTrue(user.has_group("point_of_sale.group_pos_user"))
        self.assertTrue(user.has_group("stock.group_stock_user"))
        user.write({"groups_id": [(4, self.env.ref(NURSE).id)]})
        self.assertFalse(self.has_till(user))
        for group in ("point_of_sale.group_pos_user", "sales_team.group_sale_salesman", "stock.group_stock_user"):
            self.assertFalse(user.has_group(group), group)
        # back to Recepce through the role selection of the user form
        field = next(name for name in self.env["res.users"].fields_get(attributes=["type"])
                     if name.startswith("sel_groups_") and str(self.env.ref(RECEPTION).id) in name.split("_")[2:]
                     and str(self.env.ref(NURSE).id) in name.split("_")[2:])
        user.write({field: self.env.ref(RECEPTION).id})
        self.assertFalse(user.has_group(NURSE))
        self.assertTrue(self.has_till(user))
        user.write({field: self.env.ref(DOCTOR).id})
        self.assertFalse(self.has_till(user))
        self.assertFalse(user.has_group("point_of_sale.group_pos_user"))
        user.write({field: self.env.ref(MANAGER).id})
        self.assertTrue(user.has_group(TILL))
        self.assertTrue(user.has_group("point_of_sale.group_pos_manager"))

    def test_new_users_by_role(self):
        self.assertTrue(self.has_till(self.new_user("role_till_new_reception", RECEPTION)))
        for login, role in (("role_till_new_nurse", NURSE), ("role_till_new_doctor", DOCTOR)):
            user = self.new_user(login, role)
            self.assertFalse(user.has_group(TILL), login)
            self.assertFalse(user.has_group("point_of_sale.group_pos_user"), login)
        self.assertFalse(self.has_till(self.new_user("role_till_new_none")))

    def test_manual_till_tick_is_kept(self):
        nurse = self.new_user("role_till_tick_nurse", NURSE)
        nurse.write({"groups_id": [(4, self.env.ref(TILL).id)]})
        self.assertTrue(self.has_till(nurse))
        self.assertTrue(nurse.has_group("point_of_sale.group_pos_user"))
        # another change that is not a role change keeps it
        nurse.write({"groups_id": [(4, self.env.ref("base.group_partner_manager").id)]})
        self.assertTrue(self.has_till(nurse))
        reception = self.new_user("role_till_untick_reception", RECEPTION)
        reception.write({"groups_id": [(3, self.env.ref(TILL).id)]})
        reception.write({"groups_id": [(4, self.env.ref("base.group_partner_manager").id)]})
        self.assertFalse(self.has_till(reception))

    def test_till_group_on_user_form(self):
        """The till group is outside the role selection (its own category)."""
        role_field = next(name for name in self.env["res.users"].fields_get(attributes=["type"])
                          if name.startswith("sel_groups_") and str(self.env.ref(NURSE).id) in name.split("_")[2:])
        self.assertNotIn(str(self.env.ref(TILL).id), role_field.split("_")[2:])
        arch = self.env["res.users"].get_view(self.env.ref("base.view_users_form").id)["arch"]
        till_fields = [name for name in self.env["res.users"].fields_get(attributes=["type"])
                       if name.startswith(("sel_groups_", "in_group_"))
                       and str(self.env.ref(TILL).id) in name.split("_")[2:]]
        self.assertTrue(till_fields)
        self.assertTrue(any(name in arch for name in till_fields))

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
        # Task 14: the stock root with Přehled skladu and Příjem zboží (till group), nothing else of it
        for xmlid in ("stock.menu_stock_root", "elite_vet_sale.menu_stock_overview",
                      "elite_vet_sale.menu_goods_receipt_stock"):
            self.assertIn(self.env.ref(xmlid).id, visible, xmlid)
        stock_root = self.env.ref("stock.menu_stock_root")
        others = self.env["ir.ui.menu"].with_context(**{"ir.ui.menu.full_list": True}).search(
            [("parent_id", "=", stock_root.id), ("id", "not in", self.env.ref("elite_vet_sale.menu_stock_overview").ids
              + self.env.ref("elite_vet_sale.menu_goods_receipt_stock").ids)])
        self.assertFalse(set(others.ids) & visible, others.filtered(lambda m: m.id in visible).mapped("name"))
        for xmlid in ("sale.sale_menu_root", "account.menu_finance",
                      "elite_vet_winvet.menu_winvet_root", "hr.menu_hr_root",
                      "elite_vet_calendar.menu_rozpis_root"):
            with self.subTest(menu=xmlid):
                self.assertNotIn(self.env.ref(xmlid).id, visible)
        # Task 15: the Ordinace app with only its first item, the screen Ordinace
        self.assertIn(self.env.ref("elite_vet_clinic.menu_clinic_root").id, visible)
        # Items of a hidden app are not loaded in the web client (the menu tree starts at the
        # visible roots; _visible_menu_ids alone does not check the parents).
        loaded = self.env["ir.ui.menu"].with_user(self.reception).load_menus(False)
        for xmlid in ("elite_vet_sale.menu_stock_overview_clinic", "elite_vet_sale.menu_goods_receipt_clinic",
                      "elite_vet_clinic.menu_patient_card", "elite_vet_clinic.menu_clinical_record",
                      "elite_vet_clinic.menu_pet_alert", "elite_vet_clinic.menu_clinic_config"):
            with self.subTest(loaded=xmlid):
                self.assertNotIn(self.env.ref(xmlid).id, loaded)
        self.assertIn(self.env.ref("elite_vet_reception.menu_room_board").id, loaded)
        self.assertIn(self.env.ref("elite_vet_reservation.menu_reservation_board").id, loaded)

    def test_settings_menus_only_for_management(self):
        """Task 16: Nastavení kontaktu and Nastavení rezervace for Vedení only."""
        menus = [self.env.ref(x) for x in ("elite_vet_web.menu_nastaveni_root", "elite_vet_web.menu_nastaveni_web",
                                            "elite_vet_web.menu_rezervace_nastaveni")]
        for user in (self.reception, self.nurse, self.doctor_user):
            visible = self.visible(user)
            for menu in menus:
                self.assertNotIn(menu.id, visible, (user.login, menu.name))
            with self.assertRaises(AccessError):
                self.env["elite.vet.setting"].nastaveni().with_user(user).write({"booking_slot_step": 30})
        visible = self.visible(self.manager)
        for menu in menus:
            self.assertIn(menu.id, visible, menu.name)
        # Vedení implies the calendar manager (whose rule only reads) and still saves
        self.assertTrue(self.manager.has_group("elite_vet_calendar.group_calendar_manager"))
        self.env["elite.vet.setting"].nastaveni().with_user(self.manager).write({"booking_slot_step": 30})

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

    def test_apps_menu_back_to_administrators_on_update(self):
        """Final review M-1: an earlier version gave Apps to Vedení; the update restores the stock group."""
        apps = self.env.ref("base.menu_management")
        # an earlier version gave it to Vedení; base_install_request opens it to everyone
        for groups in ([self.env.ref(MANAGER).id], []):
            apps.groups_id = [(6, 0, groups)]
            self.env["ir.ui.menu"]._elite_vet_apply_role_menus()
            self.assertEqual(apps.groups_id, self.env.ref("base.group_system"))
        if not self.manager.has_group("base.group_system"):
            self.assertNotIn(apps.id, self.visible(self.manager))

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
        """Task 14: Ordinace, Rezervace, Diskuze – no Pokladna, no stock."""
        stock_root = self.env.ref("stock.menu_stock_root")
        overview = self.env.ref("elite_vet_sale.menu_stock_overview")
        receipt = self.env.ref("elite_vet_sale.menu_goods_receipt_stock")
        self.assertEqual(receipt.parent_id, stock_root)
        self.assertEqual(receipt.sequence, overview.sequence + 1)
        for menu in (stock_root, overview, receipt):
            self.assertEqual(menu.groups_id, self.env.ref(TILL) | self.env.ref(MANAGER), menu.name)
        for user in (self.nurse, self.doctor_user):
            visible = self.visible(user)
            with self.subTest(user=user.login):
                for xmlid in ("elite_vet_clinic.menu_clinic_root", "elite_vet_web.menu_rezervace_root",
                              "mail.menu_root_discuss", "elite_vet_clinic.menu_patient_card"):
                    self.assertIn(self.env.ref(xmlid).id, visible, xmlid)
                for xmlid in ("stock.menu_stock_root", "elite_vet_sale.menu_stock_overview",
                              "elite_vet_sale.menu_goods_receipt_stock", "elite_vet_sale.menu_goods_receipt_clinic",
                              "elite_vet_sale.menu_stock_overview_clinic", "point_of_sale.menu_point_root",
                              "sale.sale_menu_root", "account.menu_finance", "elite_vet_winvet.menu_winvet_root",
                              "hr.menu_hr_root", "elite_vet_calendar.menu_rozpis_root"):
                    self.assertNotIn(self.env.ref(xmlid).id, visible, xmlid)
                loaded = self.env["ir.ui.menu"].with_user(user).load_menus(False)
                self.assertNotIn(stock_root.id, loaded)
                self.assertNotIn(self.env.ref("point_of_sale.menu_point_root").id, loaded)

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
        self.assertEqual(self.env.ref("point_of_sale.menu_point_root").groups_id, self.env.ref(TILL))

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
        # pos.config loads all its fields into the POS ([] = every field), the flag included
        self.assertEqual(self.pos_config._load_pos_data_fields(self.pos_config.id), [])
        data = self.pos_config.read(self.pos_config._load_pos_data_fields(self.pos_config.id), load=False)[0]
        self.assertIs(data["is_elite_vet_reception"], True)
