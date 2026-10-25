from datetime import date

from odoo.exceptions import AccessError
from odoo.tests import tagged

from .common import ReservationCase

WED = date(2026, 10, 14)
BLOCK_MSG = "Blokace může měnit jen správce rezervací."
SETTING_MSG = "Nastavení může měnit jen správce rezervací."


@tagged("post_install", "-at_install")
class TestManagerOnly(ReservationCase):
    """Task 16: blocks and the settings are for Správce rezervací only."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Users = cls.env["res.users"].with_context(no_reset_password=True)

        def user(login, *groups):
            return Users.create({
                "name": "T16 %s" % login, "login": login,
                "groups_id": [(6, 0, [cls.env.ref("base.group_user").id] + [cls.env.ref(g).id for g in groups])]})

        cls.reception = user("t16_reception", "elite_vet_reservation.group_reservation_reception")
        cls.manager = user("t16_manager", "elite_vet_reservation.group_reservation_manager")
        cls.calendar_manager = user("t16_calendar", "elite_vet_calendar.group_calendar_manager")
        cls.plain = user("t16_plain")

    def block(self, h_from=12, h_to=13, room=None, **vals):
        values = {"kind": "block", "state": "confirmed", "block_reason": "Oběd T16", "block_scope": "full",
                  "room_id": (room or self.room1).id,
                  "start": self.dt(WED, h_from), "stop": self.dt(WED, h_to)}
        values.update(vals)
        return self.env["elite.vet.reservation"].create(values)

    def R(self, user):
        return self.env["elite.vet.reservation"].with_user(user)

    # ------------------------------------------------------------------ blocks: reception
    def test_reception_cannot_create_block(self):
        vals = {"kind": "block", "state": "confirmed", "block_reason": "Porada", "block_scope": "full",
                "room_id": self.room1.id, "start": self.dt(WED, 14), "stop": self.dt(WED, 15)}
        with self.assertRaisesRegex(AccessError, BLOCK_MSG):
            self.R(self.reception).create(vals)
        # "Nová blokace" fills the kind from the context, not the values
        vals.pop("kind")
        with self.assertRaisesRegex(AccessError, BLOCK_MSG):
            self.R(self.reception).with_context(default_kind="block").create(vals)
        # web-only block and a clinic-wide one as well
        with self.assertRaisesRegex(AccessError, BLOCK_MSG):
            self.R(self.reception).create(dict(vals, kind="block", block_scope="web", room_id=False))
        self.assertFalse(self.env["elite.vet.reservation"].search([("block_reason", "=", "Porada")]))

    def test_reception_cannot_edit_move_cancel_delete_block(self):
        block = self.block()
        mine = block.with_user(self.reception)
        for change in (lambda: mine.write({"block_reason": "Jiný"}),
                       lambda: mine.write({"start": self.dt(WED, 13), "stop": self.dt(WED, 14)}),
                       lambda: mine.action_reschedule(self.dt(WED, 15), room_id=self.room2.id),
                       lambda: self.R(self.reception).board_move(block.id, "2026-10-14", 900, self.room2.id),
                       lambda: mine.action_cancel(),
                       lambda: mine.unlink()):
            with self.assertRaisesRegex(AccessError, BLOCK_MSG):
                change()
        self.assertEqual((block.block_reason, block.start, block.room_id, block.state),
                         ("Oběd T16", self.dt(WED, 12), self.room1, "confirmed"))
        # reading stays
        self.assertEqual(mine.read(["name"])[0]["name"], block.name)

    def test_reception_cannot_turn_reservation_into_block(self):
        r = self.reservation(start=self.dt(WED, 9, 0))
        with self.assertRaisesRegex(AccessError, BLOCK_MSG):
            r.with_user(self.reception).write({"kind": "block", "block_reason": "X"})
        self.assertEqual(r.kind, "reservation")

    def test_record_rules_without_the_python_check(self):
        """The record rules alone refuse it too (e.g. a path that skips write())."""
        block, res = self.block(), self.reservation(start=self.dt(WED, 9, 0))
        for operation in ("write", "unlink"):
            with self.assertRaises(AccessError):
                block.with_user(self.reception).check_access(operation)
            res.with_user(self.reception).check_access(operation)
            block.with_user(self.manager).check_access(operation)
        block.with_user(self.reception).check_access("read")

    def test_nurse_and_doctor_cannot_change_blocks(self):
        """Roles above reception (they imply it) are not managers either."""
        for hour, xmlid in ((7, "elite_vet_clinic.group_clinic_nurse"), (9, "elite_vet_clinic.group_clinic_doctor")):
            group = self.env.ref(xmlid, raise_if_not_found=False)
            if not group:
                continue
            u = self.env["res.users"].with_context(no_reset_password=True).create({
                "name": "T16 %s" % xmlid, "login": "t16_%s" % xmlid.split(".")[1],
                "groups_id": [(6, 0, [self.env.ref("base.group_user").id, group.id])]})
            with self.assertRaisesRegex(AccessError, BLOCK_MSG):
                self.block(hour, hour + 1).with_user(u).write({"block_reason": "Jiný"})

    # ------------------------------------------------------------------ blocks: manager
    def test_manager_creates_moves_edits_deletes_block(self):
        Rm = self.R(self.manager)
        block = Rm.create({"kind": "block", "state": "confirmed", "block_reason": "Školení", "block_scope": "full",
                           "room_id": self.room1.id, "start": self.dt(WED, 14), "stop": self.dt(WED, 15)})
        Rm.board_move(block.id, "2026-10-14", 960, self.room2.id)
        self.assertEqual((block.start, block.room_id), (self.dt(WED, 16), self.room2))
        block.with_user(self.manager).write({"block_reason": "Školení 2"})
        block.with_user(self.manager).action_cancel()
        self.assertEqual(block.state, "cancelled")
        block.with_user(self.manager).unlink()
        self.assertFalse(block.exists())

    def test_manager_repeat_and_all_rooms_split(self):
        Rm = self.R(self.manager)
        Rm.create({"kind": "block", "state": "confirmed", "block_reason": "Týdně T16", "block_scope": "full",
                   "room_id": self.room1.id, "start": self.dt(WED, 7), "stop": self.dt(WED, 8),
                   "repeat_weekly_until": date(2026, 10, 28)})
        self.assertEqual(self.env["elite.vet.reservation"].search_count([("block_reason", "=", "Týdně T16")]), 3)
        self.block(12, 13, room=self.room1)
        Rm.create({"kind": "block", "state": "confirmed", "block_reason": "Celá klinika T16", "block_scope": "full",
                   "room_id": False, "start": self.dt(WED, 12), "stop": self.dt(WED, 13)})
        pieces = self.env["elite.vet.reservation"].search([("block_reason", "=", "Celá klinika T16")])
        self.assertEqual(set(pieces.room_id.ids), {self.room2.id, self.surgery.id})

    # ------------------------------------------------------------------ reservations unaffected
    def test_reception_reservations_unaffected(self):
        Rr = self.R(self.reception)
        r = Rr.create({"kind": "reservation", "state": "confirmed", "procedure_id": self.vacc.id,
                       "room_id": self.room1.id, "start": self.dt(WED, 10), "contact_name": "Klient T16"})
        Rr.board_move(r.id, "2026-10-14", 630, self.room2.id)
        self.assertEqual((r.start, r.room_id), (self.dt(WED, 10, 30), self.room2))
        r.with_user(self.reception).write({"note": "pozn."})
        r.with_user(self.reception).action_cancel()
        self.assertEqual(r.state, "cancelled")
        r.with_user(self.reception).unlink()
        self.assertFalse(r.exists())

    def test_reception_books_next_to_block(self):
        self.block(12, 13)
        r = self.R(self.reception).create({
            "kind": "reservation", "state": "confirmed", "procedure_id": self.vacc.id,
            "room_id": self.room1.id, "start": self.dt(WED, 13), "contact_name": "Klient T16 2"})
        self.assertEqual(r.state, "confirmed")

    # ------------------------------------------------------------------ board flag + read-only view
    def test_board_can_edit_blocks(self):
        self.block()
        self.assertFalse(self.R(self.reception).board_data("2026-10-14")["can_edit_blocks"])
        self.assertTrue(self.R(self.manager).board_data("2026-10-14")["can_edit_blocks"])
        self.assertTrue(self.env["elite.vet.reservation"].board_data("2026-10-14")["can_edit_blocks"])

    def test_read_only_block_view(self):
        view = self.env.ref("elite_vet_reservation.view_reservation_block_readonly_form")
        arch = self.R(self.reception).get_view(view.id, "form")["arch"]
        self.assertIn('edit="0"', arch)
        self.assertNotIn('name="action_cancel"', arch)
        # the default form is still the editable one
        default = self.R(self.reception).get_view(False, "form")["arch"]
        self.assertNotIn('edit="0"', default)

    # ------------------------------------------------------------------ settings
    def test_settings_write_only_for_manager(self):
        setting = self.env["elite.vet.setting"].nastaveni()
        setting.booking_slot_step = 15
        for user in (self.calendar_manager, self.reception, self.plain):
            with self.assertRaises(AccessError):
                setting.with_user(user).write({"booking_slot_step": 30})
        with self.assertRaisesRegex(AccessError, SETTING_MSG):
            setting.with_user(self.calendar_manager).write({"booking_slot_step": 30})
        with self.assertRaises(AccessError):
            self.env["elite.vet.setting"].with_user(self.calendar_manager).create({})
        self.assertEqual(setting.booking_slot_step, 15)
        setting.with_user(self.manager).write({"booking_slot_step": 30})
        self.assertEqual(setting.booking_slot_step, 30)

    def test_settings_rule_without_the_python_check(self):
        setting = self.env["elite.vet.setting"].nastaveni()
        with self.assertRaises(AccessError):
            setting.with_user(self.calendar_manager).check_access("write")
        setting.with_user(self.manager).check_access("write")
        # reading stays for everybody, the website included
        for user in (self.calendar_manager, self.reception, self.plain, self.env.ref("base.public_user")):
            setting.with_user(user).check_access("read")
            self.assertTrue(setting.with_user(user).read(["booking_slot_step"]))

    def test_settings_menus_and_actions(self):
        menus = [self.env.ref(x) for x in ("elite_vet_web.menu_nastaveni_root", "elite_vet_web.menu_nastaveni_web",
                                            "elite_vet_web.menu_rezervace_nastaveni")]
        Menu = self.env["ir.ui.menu"]
        for user in (self.calendar_manager, self.reception, self.plain):
            visible = Menu.with_user(user)._visible_menu_ids()
            for menu in menus:
                self.assertNotIn(menu.id, visible, (user.login, menu.name))
        visible = Menu.with_user(self.manager)._visible_menu_ids()
        for menu in menus:
            self.assertIn(menu.id, visible, menu.name)
        manager_group = self.env.ref("elite_vet_reservation.group_reservation_manager")
        for xmlid in ("elite_vet_web.action_setting_otevrit", "elite_vet_web.action_setting_rezervace"):
            action = self.env.ref(xmlid)
            self.assertEqual(action.groups_id, manager_group)
            with self.assertRaises(AccessError):
                action.with_user(self.calendar_manager).run()
            self.assertEqual(action.with_user(self.manager).run()["res_model"], "elite.vet.setting")

    def test_settings_menu_after_elite_vet_web_update(self):
        """-u elite_vet_web alone links the calendar manager to the root again (its menuitem has
        groups); the leaf menu keeps Správce rezervací, so the root stays hidden."""
        root = self.env.ref("elite_vet_web.menu_nastaveni_root")
        root.groups_id = [(4, self.env.ref("elite_vet_calendar.group_calendar_manager").id)]
        self.assertNotIn(root.id, self.env["ir.ui.menu"].with_user(self.calendar_manager)._visible_menu_ids())
        self.env["elite.vet.setting"]._elite_vet_apply_setting_groups()
        self.assertEqual(root.groups_id, self.env.ref("elite_vet_reservation.group_reservation_manager"))
