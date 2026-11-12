"""Request 4. 11. (Lucie): a reservation may go over another one after a warning, never over a full block."""
from datetime import timedelta

from odoo import fields
from odoo.exceptions import UserError, ValidationError
from odoo.tests import Form, tagged

from odoo.addons.elite_vet_reservation.models.reservation import OverlapRuleError

from .common import ReservationCase


@tagged("post_install", "-at_install")
class TestOverlap(ReservationCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        for wd in range(7):
            cls.hours(cls, cls.room1, wd, 0.0, 24.0)
            cls.hours(cls, cls.room2, wd, 0.0, 24.0)
        cls.env["elite.vet.setting"].nastaveni().write({
            "booking_require_doctor": False, "booking_max_days_ahead": 60,
            "booking_min_hours_before": 24, "booking_slot_step": 15})
        cls.day = fields.Date.today() + timedelta(days=10)
        cls.day_str = fields.Date.to_string(cls.day)
        cls.reception = cls.env["res.users"].with_context(no_reset_password=True).create({
            "name": "Recepce Překryv", "login": "recepce_prekryv",
            "groups_id": [(6, 0, [cls.env.ref("base.group_user").id,
                                  cls.env.ref("elite_vet_reservation.group_reservation_reception").id])]})
        cls.R = cls.env["elite.vet.reservation"].with_user(cls.reception)
        cls.first = cls.reservation(cls, start=cls.dt(cls, cls.day, 9, 0), room_id=cls.room1.id, title="První")

    def vals(self, **extra):
        return dict({"kind": "reservation", "state": "confirmed", "procedure_id": self.vacc.id,
                     "room_id": self.room1.id, "start": self.dt(self.day, 9, 0), "contact_name": "Druhý"}, **extra)

    def over_first(self):
        return self.R.with_context(ev_allow_overlap=True).create(self.vals())

    def wizard(self, **vals):
        return self.env["elite.vet.reservation.wizard"].with_user(self.reception).create(
            dict({"procedure_id": self.vacc.id, "date": self.day}, **vals))

    def fill(self, w):
        w.write({"partner_mode": "new", "contact_name": "Překryv Nový", "contact_phone": "+420 606 000 555",
                 "contact_email": "prekryv.novy@example.cz", "pet_name": "Micka"})

    def block(self, room=None):
        return self.env["elite.vet.reservation"].create({
            "kind": "block", "state": "confirmed", "block_reason": "Oběd překryv", "block_scope": "full",
            "room_id": (room or self.room2).id, "start": self.dt(self.day, 12), "stop": self.dt(self.day, 13)})

    # ------------------------------------------------------------------ the rule
    def test_refused_without_the_yes(self):
        with self.assertRaises(OverlapRuleError):
            self.R.create(self.vals())

    def test_allowed_after_the_yes_and_noted(self):
        second = self.over_first()
        self.assertEqual(second.start, self.first.start)
        self.assertIn("Uloženo přes obsazený termín", second.message_ids[0].body)

    # ------------------------------------------------------------------ the reservation form
    def moved_to_first(self):
        return self.R.create(self.vals(start=self.dt(self.day, 11, 0), contact_name="Přesouvaný"))

    def test_form_save_refused_without_the_tick(self):
        other = self.moved_to_first()
        with self.assertRaises(OverlapRuleError):
            other.write({"start": self.dt(self.day, 9, 0), "stop": self.dt(self.day, 9, 15), "allow_overlap": False})

    def test_form_save_over_a_reservation_with_the_tick(self):
        other = self.moved_to_first()
        other.write({"start": self.dt(self.day, 9, 0), "stop": self.dt(self.day, 9, 15), "allow_overlap": True})
        self.assertEqual(other.start, self.dt(self.day, 9, 0))
        self.assertIn("Uloženo přes obsazený termín", other.message_ids[0].body)

    def test_form_tick_does_not_go_over_a_block(self):
        other = self.moved_to_first()
        self.block(self.room1)
        with self.assertRaisesRegex(ValidationError, "obsazený") as caught:
            other.write({"start": self.dt(self.day, 12, 0), "stop": self.dt(self.day, 12, 15), "allow_overlap": True})
        self.assertNotIsInstance(caught.exception, OverlapRuleError)

    def test_form_warns_while_changing_the_time(self):
        form = Form(self.moved_to_first())
        self.assertFalse(form.overlap_warning)
        form.start = self.dt(self.day, 9, 0)
        form.stop = self.dt(self.day, 9, 15)
        self.assertIn("Termín je obsazený", form.overlap_warning)
        self.assertTrue(form.overlap_can_override)
        form.allow_overlap = True
        record = form.save()
        self.assertEqual(record.start, self.dt(self.day, 9, 0))

    def test_form_warning_says_a_block_cannot_be_overridden(self):
        self.block(self.room1)
        form = Form(self.moved_to_first())
        form.start = self.dt(self.day, 12, 0)
        form.stop = self.dt(self.day, 12, 15)
        self.assertTrue(form.overlap_warning)
        self.assertFalse(form.overlap_can_override)

    # ------------------------------------------------------------------ "Potvrdit" on the form (request 11. 11.)
    def web_request(self, h, room=None):
        """A web request placed while the time was free (11:00 is free at first)."""
        return self.R.with_context(ev_no_mail=True).create(self.vals(
            state="web_new", source="web", room_id=(room or self.room1).id, start=self.dt(self.day, h), contact_name="Z webu"))

    def test_confirm_into_a_time_taken_meanwhile_asks_then_confirms(self):
        web = self.web_request(11)
        taken = self.R.with_context(ev_allow_overlap=True).create(self.vals(start=self.dt(self.day, 11), contact_name="Mezitím"))
        with self.assertRaises(OverlapRuleError):
            web.action_confirm()
        action = web.action_confirm_ask()
        self.assertEqual(action["res_model"], "elite.vet.reservation.confirm.wizard")
        self.assertEqual(web.state, "web_new", "nothing confirmed before the yes")
        wizard = self.env[action["res_model"]].with_user(self.reception).with_context(action["context"]).create({})
        self.assertIn(taken.name, wizard.overlap_warning)
        wizard.action_confirm()
        self.assertEqual(web.state, "confirmed")
        self.assertIn("Uloženo přes obsazený termín", web.message_ids.mapped("body")[0])

    def test_confirm_into_a_free_time_does_not_ask(self):
        web = self.web_request(15)
        self.assertFalse(web.with_context(ev_no_mail=True).action_confirm_ask())
        self.assertEqual(web.state, "confirmed")

    def test_confirm_never_over_a_block(self):
        web = self.web_request(12, room=self.room2)
        self.env["elite.vet.reservation"].with_context(ev_allow_overlap=True).create({
            "kind": "block", "state": "confirmed", "block_reason": "Oběd překryv", "block_scope": "full",
            "room_id": self.room2.id, "start": self.dt(self.day, 12), "stop": self.dt(self.day, 13)})
        with self.assertRaises(ValidationError) as caught:
            web.action_confirm_ask()
        self.assertNotIsInstance(caught.exception, OverlapRuleError)
        self.assertEqual(web.state, "web_new")

    # ------------------------------------------------------------------ orange button on the board (request 12. 11.)
    def busy_rooms(self, web):
        return [(s["room_id"], s["clash"]) for s in self.R.board_busy_suggestions(web.id)]

    def board_row(self, web):
        return next(x for x in self.R.board_data(self.day_str)["waiting"] if x["id"] == web.id)

    def test_board_offers_a_taken_room_and_confirms_over_it(self):
        web = self.R.with_context(ev_no_mail=True).create(self.vals(
            state="web_new", source="web", room_id=False, start=self.dt(self.day, 10), contact_name="Z webu"))
        for room in (self.room1, self.room2):
            self.R.create(self.vals(room_id=room.id, start=self.dt(self.day, 10), contact_name="V " + room.name))
        row = self.board_row(web)
        self.assertEqual(row["suggestions"], [])
        self.assertEqual([s["room_id"] for s in row["busy_suggestions"]], [self.room1.id, self.room2.id])
        self.assertIn("V Ordinace 1", row["busy_suggestions"][0]["clash"])
        self.R.board_confirm(web.id, self.day_str, 600, self.room2.id, None, False, None, False, True)
        self.assertEqual((web.state, web.room_id), ("confirmed", self.room2))
        self.assertIn("Uloženo přes obsazený termín", web.message_ids.mapped("body")[0])

    def test_board_offers_taken_rooms_only_when_nothing_is_free(self):
        web = self.R.with_context(ev_no_mail=True).create(self.vals(
            state="web_new", source="web", room_id=False, start=self.dt(self.day, 10), contact_name="Z webu"))
        self.R.create(self.vals(room_id=self.room1.id, start=self.dt(self.day, 10), contact_name="Jen v jedné"))
        row = self.board_row(web)
        self.assertEqual([s["room_id"] for s in row["suggestions"]], [self.room2.id])
        self.assertEqual(row["busy_suggestions"], [])

    def test_board_never_offers_a_room_under_a_block(self):
        web = self.R.with_context(ev_no_mail=True).create(self.vals(
            state="web_new", source="web", room_id=False, start=self.dt(self.day, 13), contact_name="Z webu"))
        self.R.create(self.vals(room_id=self.room1.id, start=self.dt(self.day, 13), contact_name="Obsazeno"))
        self.env["elite.vet.reservation"].create({
            "kind": "block", "state": "confirmed", "block_reason": "Oběd", "block_scope": "full",
            "room_id": self.room2.id, "start": self.dt(self.day, 13), "stop": self.dt(self.day, 14)})
        self.assertEqual([r for r, _c in self.busy_rooms(web)], [self.room1.id])

    def test_context_key_needs_reception(self):
        """A user outside Recepce cannot use the key (the public website goes through sudo with no key)."""
        with self.assertRaises(OverlapRuleError):
            self.env["elite.vet.reservation"].with_user(self.env.ref("base.public_user")).sudo().with_context(
                ev_allow_overlap=True).create(self.vals())

    def test_full_block_stays_final(self):
        self.block()
        with self.assertRaises(ValidationError) as caught:
            self.R.with_context(ev_allow_overlap=True).create(self.vals(room_id=self.room2.id, start=self.dt(self.day, 12)))
        self.assertNotIsInstance(caught.exception, OverlapRuleError)

    def test_state_changes_of_overlapping_reservations_pass(self):
        second = self.over_first()
        second.write({"state": "done"})
        self.first.write({"state": "done"})
        self.first.write({"state": "confirmed"})
        self.assertEqual((self.first.state, second.state), ("confirmed", "done"))

    def test_coming_back_to_a_taken_time_warns(self):
        second = self.over_first()
        second.write({"state": "cancelled"})
        with self.assertRaises(OverlapRuleError):
            second.with_context(ev_allow_overlap=False).write({"state": "confirmed"})

    def test_moving_an_overlapping_reservation_warns_again(self):
        second = self.over_first()
        with self.assertRaises(OverlapRuleError):
            self.R.board_move(second.id, self.day_str, 9 * 60 + 5, self.room1.id)
        self.R.board_move(second.id, self.day_str, 9 * 60 + 5, self.room1.id, force_overlap=True)
        self.assertEqual(second.start, self.dt(self.day, 9, 5))

    def test_board_move_force_of_the_doctor_rule_is_not_a_yes_to_the_overlap(self):
        other = self.reservation(start=self.dt(self.day, 11, 0), room_id=self.room1.id, contact_phone="+420 606 000 666")
        with self.assertRaises(OverlapRuleError):
            self.R.board_move(other.id, self.day_str, 9 * 60, self.room1.id, force=True)
        self.R.board_move(other.id, self.day_str, 9 * 60, self.room1.id, force=True, force_overlap=True)
        self.assertEqual(other.start, self.first.start)

    def test_web_still_does_not_offer_the_time(self):
        self.assign(self.dr_a, self.room1, self.day, 8.0, 12.0)
        self.over_first()
        minutes = [s["minute"] for s in self.env["elite.vet.availability"].slots(self.vacc, self.day)
                   if self.room1.id in s["room_ids"]]
        self.assertNotIn(9 * 60, minutes)

    # ------------------------------------------------------------------ wizard
    def test_wizard_board_click_on_a_taken_time(self):
        w = self.wizard(minute=9 * 60, room_id=self.room1.id)
        w.action_step_time()
        self.assertEqual((w.step, w.overlap_room_id), ("time", self.room1))
        w.action_force_overlap()
        self.assertEqual((w.step, w.room_id, w.overlap_ok), ("client", self.room1, True))
        self.fill(w)
        w.action_step_summary()
        self.assertIn("Překryv", w.summary)
        w.action_save()
        second = self.env["elite.vet.reservation"].search([("contact_email", "=", "prekryv.novy@example.cz")])
        self.assertEqual(second.start, self.first.start)

    def test_wizard_manual_time_warns_and_a_block_refuses(self):
        w = self.wizard()
        w.action_step_time()
        w.write({"manual": True, "manual_room_id": self.room1.id, "manual_time": "09:00"})
        w.action_use_manual_time()
        self.assertEqual((w.step, w.overlap_room_id), ("time", self.room1))
        self.assertIn("je obsazený", w.warning)
        self.block()
        w.write({"manual_room_id": self.room2.id, "manual_time": "12:00"})
        with self.assertRaises(UserError):
            w.action_use_manual_time()

    def test_wizard_picking_a_free_time_drops_the_yes(self):
        self.assign(self.dr_a, self.room2, self.day, 8.0, 12.0)
        w = self.wizard(minute=9 * 60, room_id=self.room1.id)
        w.action_step_time()
        w.slot_ids.filtered(lambda ln: ln.room_id == self.room2)[:1].action_select()
        self.assertFalse(w.overlap_ok)
        self.assertFalse(w.overlap_room_id)
