"""Procedure for two doctors (second room), the doctor on duty in the wizard
and light / custom procedure colours."""
from datetime import timedelta

from odoo import fields
from odoo.exceptions import UserError, ValidationError
from odoo.tests import Form, tagged

from ..models.procedure import LIGHT_COLORS
from .common import ReservationCase


@tagged("post_install", "-at_install")
class TestSecondRoom(ReservationCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.R = cls.env["elite.vet.reservation"]
        cls.day = fields.Date.today() + timedelta(days=10)

    def main_reservation(self, **vals):
        return self.reservation(start=self.dt(self.day, 9, 0), doctor_id=self.dr_a.id, **vals)

    def client_mails(self):
        return self.env["mail.mail"].search([("email_to", "ilike", "klient@example.cz")])

    def test_add_copies_and_links(self):
        r = self.main_reservation()
        mail_count = len(self.client_mails())
        d = r.add_second_room(self.room2, self.dr_b)
        self.assertEqual((d.room_id, d.doctor_id, d.start, d.stop), (self.room2, self.dr_b, r.start, r.stop))
        self.assertEqual((d.partner_id, d.pet_name, d.procedure_id), (r.partner_id, r.pet_name, r.procedure_id))
        self.assertEqual((r.linked_reservation_id, d.linked_reservation_id), (d, r))
        self.assertTrue(d.is_second_room and not r.is_second_room)
        self.assertEqual(len(self.client_mails()), mail_count, "the client receives nothing more")

    def test_second_room_busy(self):
        self.reservation(start=self.dt(self.day, 9, 0), room_id=self.room2.id)
        r = self.main_reservation()
        with self.assertRaises(ValidationError):
            r.add_second_room(self.room2, self.dr_b)

    def test_not_twice_nor_same_room(self):
        r = self.main_reservation()
        with self.assertRaises(UserError):
            r.add_second_room(self.room1)
        d = r.add_second_room(self.room2)
        with self.assertRaises(UserError):
            r.add_second_room(self.surgery)
        with self.assertRaises(UserError):
            d.add_second_room(self.surgery)

    def test_reschedule_moves_both(self):
        r = self.main_reservation()
        d = r.add_second_room(self.room2, self.dr_b)
        r.action_reschedule(self.dt(self.day, 11, 0))
        self.assertEqual((d.start, d.stop, d.room_id), (r.start, r.stop, self.room2))
        d.action_reschedule(self.dt(self.day, 13, 0))
        self.assertEqual(r.start, self.dt(self.day, 13, 0))

    def test_reschedule_into_busy_second_room_fails(self):
        r = self.main_reservation()
        r.add_second_room(self.room2, self.dr_b)
        self.reservation(start=self.dt(self.day, 11, 0), room_id=self.room2.id)
        with self.assertRaises(ValidationError):
            r.action_reschedule(self.dt(self.day, 11, 0))

    def test_cancel_main_cancels_both_one_email(self):
        r = self.main_reservation()
        d = r.add_second_room(self.room2, self.dr_b)
        mail_count = len(self.client_mails())
        r.action_cancel()
        self.assertEqual((r.state, d.state), ("cancelled", "cancelled"))
        self.assertEqual(len(self.client_mails()), mail_count + 1)

    def test_cancel_second_only(self):
        r = self.main_reservation()
        d = r.add_second_room(self.room2, self.dr_b)
        mail_count = len(self.client_mails())
        d.action_cancel()
        self.assertEqual((r.state, d.state), ("confirmed", "cancelled"))
        self.assertFalse(r.linked_reservation_id)
        self.assertEqual(len(self.client_mails()), mail_count)
        r.add_second_room(self.surgery)   # possible again

    def test_done_and_reschedule_second_without_email(self):
        r = self.main_reservation()
        d = r.add_second_room(self.room2, self.dr_b)
        mail_count = len(self.client_mails())
        r.action_reschedule(self.dt(self.day, 10, 0))
        self.assertEqual(len(self.client_mails()), mail_count + 1, "only one e-mail about the reschedule")
        r.action_done()
        self.assertEqual(d.state, "done")

    def test_board_shows_link(self):
        r = self.main_reservation()
        r.add_second_room(self.room2, self.dr_b)
        ev = {e["id"]: e for e in self.R.board_data(fields.Date.to_string(self.day))["events"]}
        self.assertEqual(ev[r.id]["linked"], "Ordinace 2 · " + self.dr_b.name)
        self.assertEqual(ev[r.linked_reservation_id.id]["linked"], "Ordinace 1 · " + self.dr_a.name)

    def test_wizard_prefills_doctor_on_duty(self):
        r = self.main_reservation()
        self.assign(self.dr_b, self.room2, self.day, 8.0, 12.0)
        w = Form(self.env["elite.vet.reservation.second.room.wizard"].with_context(default_reservation_id=r.id))
        w.room_id = self.room2
        self.assertEqual(w.doctor_id, self.dr_b)
        w.save().action_add()
        self.assertEqual(r.linked_reservation_id.doctor_id, self.dr_b)


@tagged("post_install", "-at_install")
class TestServingDoctor(ReservationCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.day = fields.Date.today() + timedelta(days=10)
        cls.W = cls.env["elite.vet.reservation.wizard"]
        for wd in range(7):
            cls.hours(cls, cls.room1, wd, 8.0, 19.0)
        cls.env["elite.vet.setting"].nastaveni().write({
            "booking_require_doctor": False, "booking_max_days_ahead": 60, "booking_slot_step": 15})

    def form(self, minute):
        ctx = {"default_date": fields.Date.to_string(self.day), "default_minute": minute,
               "default_room_id": self.room1.id}
        f = Form(self.W.with_context(**ctx))
        f.procedure_id = self.vacc
        return f

    def test_single_doctor_on_duty_is_selected(self):
        self.assign(self.dr_a, self.room1, self.day, 8.0, 14.0)
        self.assign(self.dr_b, self.room1, self.day, 14.0, 19.0)
        self.assertEqual(self.form(9 * 60).doctor_id, self.dr_a)
        self.assertEqual(self.form(15 * 60).doctor_id, self.dr_b)

    def test_overlap_offers_choice(self):
        self.assign(self.dr_a, self.room1, self.day, 8.0, 14.0)
        self.assign(self.dr_b, self.room1, self.day, 12.0, 19.0)
        f = self.form(13 * 60)
        self.assertFalse(f.doctor_id)
        self.assertEqual(set(f.serving_doctor_ids.ids), {self.dr_a.id, self.dr_b.id})
        f.serving_doctor_id = self.dr_b
        self.assertEqual(f.doctor_id, self.dr_b)
        w = f.save()
        w.action_step_time()
        self.assertEqual((w.step, w.slot_doctor_id), ("client", self.dr_b))

    def test_no_board_click_no_doctor(self):
        self.assign(self.dr_a, self.room1, self.day, 8.0, 14.0)
        f = Form(self.W.with_context(default_date=fields.Date.to_string(self.day)))
        f.procedure_id = self.vacc
        self.assertFalse(f.doctor_id)


@tagged("post_install", "-at_install")
class TestProcedureColors(ReservationCase):

    def test_light_and_custom_colour(self):
        self.vacc.color = "light_yellow"
        self.assertEqual(self.vacc.color_hex, LIGHT_COLORS["light_yellow"][1])
        self.vacc.custom_color = "#ffeedd"
        self.assertEqual(self.vacc.color_hex, "#ffeedd")
        with Form(self.vacc) as f:
            f.color = "light_blue"
            self.assertFalse(f.custom_color)
        self.assertEqual(self.vacc.color_hex, LIGHT_COLORS["light_blue"][1])
