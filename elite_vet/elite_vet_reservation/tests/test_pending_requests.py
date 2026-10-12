"""An unconfirmed web request holds its slot on the web (otherwise another client
could book the same time). Reception is not restricted."""
from datetime import date, timedelta

from odoo import fields
from odoo.tests import tagged

from .common import ReservationCase


@tagged("post_install", "-at_install")
class TestPendingRequestHoldsSlot(ReservationCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.A = cls.env["elite.vet.availability"]
        cls.day = fields.Date.today() + timedelta(days=10)
        for wd in range(7):
            cls.hours(cls, cls.room1, wd, 8.0, 18.0)
            cls.hours(cls, cls.room2, wd, 8.0, 18.0)
        cls.env["elite.vet.setting"].nastaveni().write({
            "booking_require_doctor": False, "booking_slot_step": 15, "booking_max_days_ahead": 60,
            "booking_min_hours_before": 24})

    def web_times(self, proc=None, doctor=None):
        return [s["time"] for s in self.A.slots(proc or self.vacc, self.day, doctor=doctor, scope="web")]

    def web_request(self, h, m=0, **vals):
        return self.reservation(state="web_new", source="web", room_id=False,
                                start=self.dt(self.day, h, m), **vals)

    def test_two_rooms_two_requests(self):
        self.web_request(10)
        self.assertIn("10:00", self.web_times(), "one room is still free")
        self.web_request(10)
        self.assertNotIn("10:00", self.web_times())
        self.assertIn("10:15", self.web_times())

    def test_procedure_in_single_room(self):
        # Dermatology only in Ordinace 1: one request takes the time even though Ordinace 2 is free.
        self.web_request(10, procedure_id=self.derm.id)
        self.assertNotIn("10:00", self.web_times(self.derm))
        self.assertIn("10:00", self.web_times(), "vaccination can go to Ordinace 2")
        self.web_request(10)
        self.assertNotIn("10:00", self.web_times())

    def test_duration_overlap(self):
        self.web_request(10, procedure_id=self.derm.id)   # 10:00–10:30
        times = self.web_times(self.derm)
        self.assertNotIn("10:15", times)
        self.assertIn("10:30", times)

    def test_chosen_doctor(self):
        self.assign(self.dr_a, self.room1, self.day, 8.0, 18.0)
        self.assign(self.dr_b, self.room2, self.day, 8.0, 18.0)
        self.web_request(10, doctor_id=self.dr_a.id)
        self.assertNotIn("10:00", self.web_times(doctor=self.dr_a))
        self.assertIn("10:00", self.web_times(doctor=self.dr_b))

    def test_cancelled_and_confirmed(self):
        a, b = self.web_request(10), self.web_request(10)
        a.action_cancel()
        self.assertIn("10:00", self.web_times())
        b.write({"room_id": self.room2.id})
        b.action_confirm()
        self.assertIn("10:00", self.web_times(), "Ordinace 1 stayed free")

    def test_reception_unrestricted(self):
        self.web_request(10)
        self.web_request(10)
        internal = self.A.slots(self.vacc, self.day, min_hours=0, scope="internal",
                                rooms=self.vacc.rooms_for_reception())
        self.assertIn("10:00", [s["time"] for s in internal])

    def test_board_suggestions_stale(self):
        """Board suggestions are computed without holds - a request does not block itself."""
        w = self.web_request(10)
        self.assertTrue(self.env["elite.vet.reservation"].board_suggestions(w.id))
