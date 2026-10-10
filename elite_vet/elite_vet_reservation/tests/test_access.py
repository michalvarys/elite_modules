from datetime import date

from odoo.exceptions import AccessError
from odoo.tests import tagged

from .common import ReservationCase

WED = date(2026, 10, 14)


@tagged("post_install", "-at_install")
class TestAccess(ReservationCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Users = cls.env["res.users"].with_context(no_reset_password=True)
        cls.reception = Users.create({
            "name": "Recepce Test", "login": "recepce_test",
            "groups_id": [(6, 0, [cls.env.ref("base.group_user").id,
                                  cls.env.ref("elite_vet_reservation.group_reservation_reception").id])]})
        cls.manager = Users.create({
            "name": "Správce Test", "login": "spravce_test",
            "groups_id": [(6, 0, [cls.env.ref("base.group_user").id,
                                  cls.env.ref("elite_vet_reservation.group_reservation_manager").id])]})
        cls.plain = Users.create({
            "name": "Plain Test", "login": "plain_test",
            "groups_id": [(6, 0, [cls.env.ref("base.group_user").id])]})

    def test_reception_board_and_doctors(self):
        self.assign(self.dr_a, self.room1, WED, 8.0, 12.0)
        self.reservation(start=self.dt(WED, 9, 0), doctor_id=self.dr_a.id)
        R = self.env["elite.vet.reservation"].with_user(self.reception)
        data = R.board_data("2026-10-14")
        self.assertTrue(data["events"])
        self.assertTrue(data["rooms"][0]["doctors"] or data["rooms"][1]["doctors"])
        self.assertTrue(self.env["elite.vet.doctor"].with_user(self.reception).search([]))

    def test_reception_confirms_web_new(self):
        r = self.reservation(start=self.dt(WED, 10, 0), state="web_new", source="web", room_id=False,
                             doctor_id=self.dr_a.id)
        r = r.with_user(self.reception)
        r.room_id = self.room1
        r.action_confirm()
        self.assertEqual(r.state, "confirmed")

    def test_reception_cannot_create_room(self):
        with self.assertRaises(AccessError):
            self.env["elite.vet.room"].with_user(self.reception).create({"name": "Nová"})

    def test_reception_sees_app_menu(self):
        root = self.env.ref("elite_vet_web.menu_rezervace_root")
        visible = self.env["ir.ui.menu"].with_user(self.reception)._visible_menu_ids()
        self.assertIn(root.id, visible)

    def test_manager_sees_app_menu_and_saves_settings(self):
        root = self.env.ref("elite_vet_web.menu_rezervace_root")
        self.assertIn(root.id, self.env["ir.ui.menu"].with_user(self.manager)._visible_menu_ids())
        setting = self.env["elite.vet.setting"].with_user(self.manager).nastaveni()
        setting.write({"booking_slot_step": 30})
        self.assertEqual(setting.booking_slot_step, 30)

    def test_plain_internal_user_partner_form(self):
        partner = self.env["res.partner"].create({"name": "Klient X", "is_vet_client": True})
        P = self.env["res.partner"].with_user(self.plain)
        self.assertEqual(P.browse(partner.id).read(["name"])[0]["name"], "Klient X")
        P.get_view(view_id=self.env.ref("base.view_partner_form").id)
