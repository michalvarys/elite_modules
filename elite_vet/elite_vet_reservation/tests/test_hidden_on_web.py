"""A doctor's service hidden on the website (follow-up of 16. 11., Lucie): the doctor stays in the
roster and the reservation calendar, but online booking does not offer her - neither in the list
of doctors nor in free times. Reception books her as usual."""
import json
from datetime import date, timedelta

from odoo import fields
from odoo.exceptions import UserError
from odoo.tests import HttpCase, tagged

from .common import ReservationCase


@tagged("post_install", "-at_install")
class TestHiddenOnWeb(ReservationCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.A = cls.env["elite.vet.availability"]
        cls.Assignment = cls.env["elite.vet.doctor.assignment"]
        cls.type_am = cls.env["elite.vet.shift.type"].create({"name": "T Ranní", "time_from": 8.0, "time_to": 14.0})
        cls.dr_a.default_room_id = cls.room1
        cls.day = fields.Date.context_today(cls.A) + timedelta(days=7)
        for wd in range(7):
            cls.hours(cls, cls.room1, wd, 8.0, 18.0)
        cls.env["elite.vet.setting"].nastaveni().write({
            "booking_require_doctor": True, "booking_max_days_ahead": 60,
            "booking_min_hours_before": 0, "booking_slot_step": 15})

    def shift(self, **vals):
        return self.env["elite.vet.shift"].create(dict(
            {"date": self.day, "type_id": self.type_am.id, "doctor_id": self.dr_a.id}, **vals))

    def linked(self, shift):
        return self.Assignment.search([("shift_id", "=", shift.id)])

    def test_shift_flag_goes_to_its_service(self):
        shift = self.shift(hide_on_web=True)
        self.assertTrue(self.linked(shift).hide_on_web)
        shift.hide_on_web = False
        self.assertFalse(self.linked(shift).hide_on_web)

    def test_roster_service_flag_only_in_the_roster(self):
        shift = self.shift()
        with self.assertRaises(UserError):
            self.linked(shift).hide_on_web = True

    def test_web_does_not_offer_hidden_doctor(self):
        self.shift(hide_on_web=True)
        self.assertFalse(self.A.slots(self.vacc, self.day, scope="web"))
        self.assertFalse(self.A.slots(self.vacc, self.day, self.dr_a, scope="web"))
        self.assertNotIn(self.day.isoformat(), self.A.days(self.vacc, self.day.year, self.day.month))
        # reception still books her
        internal = self.A.slots(self.vacc, self.day, scope="internal")
        self.assertTrue(internal)
        self.assertIn(self.dr_a.id, internal[0]["doctor_ids"])
        self.assertEqual(self.A.room_doctors(self.vacc, self.day, internal[0]), [(self.room1.id, self.dr_a.id)])

    def test_visible_doctor_next_to_hidden_one(self):
        """A weekend with two doctors: the website offers only the visible one and never names the other."""
        self.shift(hide_on_web=True)
        self.assign(self.dr_b, self.room1, self.day, 8.0, 14.0)
        web = self.A.slots(self.vacc, self.day, scope="web")
        self.assertTrue(web)
        self.assertTrue(all(s["doctor_ids"] == [self.dr_b.id] for s in web))

    def test_manual_service_can_be_hidden(self):
        a = self.assign(self.dr_a, self.room1, self.day, 8.0, 14.0)
        self.assertTrue(self.A.slots(self.vacc, self.day, scope="web"))
        a.hide_on_web = True
        self.assertFalse(self.A.slots(self.vacc, self.day, scope="web"))


@tagged("post_install", "-at_install")
class TestHiddenOnWebOptions(HttpCase):

    def test_options_skip_hidden_doctor(self):
        self.env["elite.vet.setting"].nastaveni().write({"web_booking_source": "elite"})
        room = self.env["elite.vet.room"].create({"name": "Ordinace H", "color": "teal"})
        Doctor = self.env["elite.vet.doctor"]
        shown = Doctor.create({"name": "MVDr. Viditelná Testová", "accepts_bookings": True})
        hidden = Doctor.create({"name": "MVDr. Skrytá Testová", "accepts_bookings": True})
        day = date.today() + timedelta(days=2)
        Assignment = self.env["elite.vet.doctor.assignment"]
        Assignment.create({"doctor_id": shown.id, "room_id": room.id, "date": day, "hour_from": 8, "hour_to": 14})
        Assignment.create({"doctor_id": hidden.id, "room_id": room.id, "date": day, "hour_from": 8, "hour_to": 14,
                           "hide_on_web": True})
        resp = self.url_open("/rezervace/api/options",
                             data=json.dumps({"jsonrpc": "2.0", "method": "call", "params": {}}),
                             headers={"Content-Type": "application/json"})
        ids = [d["id"] for d in resp.json()["result"]["doctors"]]
        self.assertIn(shown.id, ids)
        self.assertNotIn(hidden.id, ids)
