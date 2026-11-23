"""Request 23. 11. (Lucie): a doctor booked at the same time in another room warns, but the
reservation can still be saved after a yes (like a taken time)."""
from datetime import timedelta

from odoo import fields
from odoo.tests import Form, tagged

from odoo.addons.elite_vet_reservation.models.reservation import OverlapRuleError

from .common import ReservationCase


@tagged("post_install", "-at_install")
class TestDoctorClash(ReservationCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        for wd in range(7):
            cls.hours(cls, cls.room1, wd, 0.0, 24.0)
            cls.hours(cls, cls.room2, wd, 0.0, 24.0)
        cls.env["elite.vet.setting"].nastaveni().write({
            "booking_require_doctor": False, "booking_max_days_ahead": 60,
            "booking_min_hours_before": 0, "booking_slot_step": 15})
        cls.day = fields.Date.today() + timedelta(days=10)

    def book(self, room, h, m=0, minutes=30, doctor=None, **vals):
        start = self.dt(self.day, h, m)
        return self.reservation(room_id=room.id, doctor_id=(doctor or self.dr_a).id,
                                start=start, stop=start + timedelta(minutes=minutes), **vals)

    def test_same_doctor_other_room_warns(self):
        self.book(self.room1, 9)
        with self.assertRaises(OverlapRuleError) as err:
            self.book(self.room2, 9, 15)
        self.assertIn(self.dr_a.name, str(err.exception))
        self.assertIn(self.room1.name, str(err.exception))

    def test_yes_saves_and_logs(self):
        self.book(self.room1, 9)
        rec = self.book(self.room2, 9, 15, **{"allow_overlap": True})
        self.assertEqual(rec.state, "confirmed")
        self.assertTrue(any("Uloženo i přes upozornění" in (m.body or "") for m in rec.message_ids))
        other = self.env["elite.vet.reservation"].with_context(ev_allow_doctor_clash=True)
        start = self.dt(self.day, 9, 0)   # room 2 is free until 9:15, the doctor is in room 1
        other.create({"kind": "reservation", "state": "confirmed", "source": "internal",
                      "procedure_id": self.vacc.id, "room_id": self.room2.id, "doctor_id": self.dr_a.id,
                      "start": start, "stop": start + timedelta(minutes=10), "contact_name": "Klient B"})

    def test_no_warning_without_clash(self):
        self.book(self.room1, 9)
        self.book(self.room2, 9, 30)                      # right after
        self.book(self.room2, 9, doctor=self.dr_b, minutes=15)   # another doctor at the same time
        self.book(self.room1, 10, doctor=self.env["elite.vet.doctor"])   # no doctor at all

    def test_changing_the_doctor_warns(self):
        self.book(self.room1, 9)
        rec = self.book(self.room2, 9, doctor=self.dr_b)
        with self.assertRaises(OverlapRuleError):
            rec.doctor_id = self.dr_a
        with Form(rec) as form:
            form.doctor_id = self.dr_a
            self.assertIn(self.dr_a.name, form.overlap_warning)
            self.assertTrue(form.overlap_can_override)
            form.allow_overlap = True
        self.assertEqual(rec.doctor_id, self.dr_a)

    def test_two_rooms_of_one_procedure_do_not_clash(self):
        main = self.book(self.room1, 9)
        copy = main.add_second_room(self.room2, self.dr_b)
        self.assertTrue(copy)
        copy.doctor_id = self.dr_a   # the same visit, not a double booking

    def test_wizard_warns_in_summary_and_saves(self):
        self.book(self.room1, 9)
        w = self.env["elite.vet.reservation.wizard"].create({
            "procedure_id": self.vacc.id, "date": self.day, "doctor_id": self.dr_a.id, "room_id": self.room2.id,
            "minute": 9 * 60 + 15, "partner_mode": "new", "contact_name": "Nový Klient",
            "contact_phone": "+420777000999", "step": "client", "reached_step": 2})
        self.assertIn(self.dr_a.name, w.doctor_warning)
        w.action_step_summary()
        self.assertTrue(w.doctor_clash_ok)
        self.assertIn(self.dr_a.name, str(w.summary))
        w.action_save()
        self.assertTrue(self.env["elite.vet.reservation"].search_count(
            [("room_id", "=", self.room2.id), ("doctor_id", "=", self.dr_a.id)]))
