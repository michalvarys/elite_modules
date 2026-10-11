"""Nepotvrzená žádost z webu drží na webu místo (jinak by se na stejný čas
přihlásil další klient). Recepci nic neomezuje."""
from datetime import date, timedelta

from odoo import fields
from odoo.tests import tagged

from .common import ReservationCase


@tagged("post_install", "-at_install")
class TestCekajiciDrziMisto(ReservationCase):

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

    def zadost(self, h, m=0, **vals):
        return self.reservation(state="web_new", source="web", room_id=False,
                                start=self.dt(self.day, h, m), **vals)

    def test_dve_ordinace_dve_zadosti(self):
        self.zadost(10)
        self.assertIn("10:00", self.web_times(), "jedna ordinace je ještě volná")
        self.zadost(10)
        self.assertNotIn("10:00", self.web_times())
        self.assertIn("10:15", self.web_times())

    def test_ukon_jen_v_jedne_ordinaci(self):
        # Dermatologie jen v Ordinaci 1: jedna žádost čas zabere, i když je Ordinace 2 volná.
        self.zadost(10, procedure_id=self.derm.id)
        self.assertNotIn("10:00", self.web_times(self.derm))
        self.assertIn("10:00", self.web_times(), "vakcinace jde do Ordinace 2")
        self.zadost(10)
        self.assertNotIn("10:00", self.web_times())

    def test_prekryv_delky(self):
        self.zadost(10, procedure_id=self.derm.id)   # 10:00–10:30
        times = self.web_times(self.derm)
        self.assertNotIn("10:15", times)
        self.assertIn("10:30", times)

    def test_zvolena_lekarka(self):
        self.assign(self.dr_a, self.room1, self.day, 8.0, 18.0)
        self.assign(self.dr_b, self.room2, self.day, 8.0, 18.0)
        self.zadost(10, doctor_id=self.dr_a.id)
        self.assertNotIn("10:00", self.web_times(doctor=self.dr_a))
        self.assertIn("10:00", self.web_times(doctor=self.dr_b))

    def test_zrusena_a_potvrzena(self):
        a, b = self.zadost(10), self.zadost(10)
        a.action_cancel()
        self.assertIn("10:00", self.web_times())
        b.write({"room_id": self.room2.id})
        b.action_confirm()
        self.assertIn("10:00", self.web_times(), "Ordinace 1 zůstala volná")

    def test_recepce_neomezena(self):
        self.zadost(10)
        self.zadost(10)
        internal = self.A.slots(self.vacc, self.day, min_hours=0, scope="internal",
                                rooms=self.vacc.rooms_for_reception())
        self.assertIn("10:00", [s["time"] for s in internal])

    def test_board_suggestions_stale(self):
        """Návrhy na tabuli se počítají bez držení – žádost samu sebe neblokuje."""
        w = self.zadost(10)
        self.assertTrue(self.env["elite.vet.reservation"].board_suggestions(w.id))
