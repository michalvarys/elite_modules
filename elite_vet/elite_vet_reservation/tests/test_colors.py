from datetime import date

from odoo.tests import tagged

from .common import ReservationCase
from ..models.reservation import DOCTOR_COLORS, doctor_color

D = date(2026, 10, 14)


@tagged("post_install", "-at_install")
class TestColors(ReservationCase):
    """The card has the procedure colour, the left stripe has the doctor colour."""

    def test_card_keeps_procedure_colour_with_doctor(self):
        self.dr_a.calendar_color = "#123456"
        r = self.reservation(start=self.dt(D, 9, 0), doctor_id=self.dr_a.id)
        self.assertEqual(r.color_hex, self.vacc.color_hex)

    def test_without_doctor_procedure_colour(self):
        r = self.reservation(start=self.dt(D, 9, 0))
        self.assertEqual(r.color_hex, self.vacc.color_hex)

    def test_automatic_colour_when_none_chosen(self):
        self.dr_b.calendar_color = False
        self.assertEqual(doctor_color(self.dr_b), DOCTOR_COLORS[self.dr_b.id % len(DOCTOR_COLORS)])

    def test_new_doctor_gets_colour_when_flagged(self):
        d = self.env["elite.vet.doctor"].create({"name": "MVDr. Nová Barva"})
        self.assertFalse(d.calendar_color)
        d.accepts_bookings = True
        self.assertTrue(d.calendar_color)

    def test_board_doctor_stripe_colour(self):
        self.hours(self.room1, 2, 8.0, 18.0)
        self.assign(self.dr_a, self.room1, D, 8.0, 12.0)
        self.dr_a.calendar_color = "#abcdef"
        r = self.reservation(start=self.dt(D, 9, 0), doctor_id=self.dr_a.id)
        data = self.env["elite.vet.reservation"].board_data("2026-10-14")
        ev = next(e for e in data["events"] if e["id"] == r.id)
        self.assertEqual(ev["color_hex"], self.vacc.color_hex)
        self.assertEqual(ev["doctor_color"], "#abcdef")
        no_doctor = self.reservation(start=self.dt(D, 10, 0))
        ev = next(e for e in self.env["elite.vet.reservation"].board_data("2026-10-14")["events"] if e["id"] == no_doctor.id)
        self.assertFalse(ev["doctor_color"])
        room = next(x for x in data["rooms"] if x["id"] == self.room1.id)
        self.assertEqual(room["doctors"][0]["color"], "#abcdef")
