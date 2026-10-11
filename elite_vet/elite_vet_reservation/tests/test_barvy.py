from datetime import date

from odoo.tests import tagged

from .common import ReservationCase
from ..models.reservation import BARVY_LEKAREK, barva_lekarky

D = date(2026, 10, 14)


@tagged("post_install", "-at_install")
class TestBarvy(ReservationCase):
    """Karta má barvu úkonu, proužek vlevo barvu lékařky."""

    def test_card_keeps_procedure_colour_with_doctor(self):
        self.dr_a.barva = "#123456"
        r = self.reservation(start=self.dt(D, 9, 0), doctor_id=self.dr_a.id)
        self.assertEqual(r.color_hex, self.vacc.color_hex)

    def test_without_doctor_procedure_colour(self):
        r = self.reservation(start=self.dt(D, 9, 0))
        self.assertEqual(r.color_hex, self.vacc.color_hex)

    def test_automatic_colour_when_none_chosen(self):
        self.dr_b.barva = False
        self.assertEqual(barva_lekarky(self.dr_b), BARVY_LEKAREK[self.dr_b.id % len(BARVY_LEKAREK)])

    def test_new_doctor_gets_colour_when_flagged(self):
        d = self.env["elite.vet.doctor"].create({"name": "MVDr. Nová Barva"})
        self.assertFalse(d.barva)
        d.prijima_rezervace = True
        self.assertTrue(d.barva)

    def test_board_doctor_stripe_colour(self):
        self.hours(self.room1, 2, 8.0, 18.0)
        self.assign(self.dr_a, self.room1, D, 8.0, 12.0)
        self.dr_a.barva = "#abcdef"
        r = self.reservation(start=self.dt(D, 9, 0), doctor_id=self.dr_a.id)
        data = self.env["elite.vet.reservation"].board_data("2026-10-14")
        ev = next(e for e in data["events"] if e["id"] == r.id)
        self.assertEqual(ev["color_hex"], self.vacc.color_hex)
        self.assertEqual(ev["doctor_color"], "#abcdef")
        bez = self.reservation(start=self.dt(D, 10, 0))
        ev = next(e for e in self.env["elite.vet.reservation"].board_data("2026-10-14")["events"] if e["id"] == bez.id)
        self.assertFalse(ev["doctor_color"])
        room = next(x for x in data["rooms"] if x["id"] == self.room1.id)
        self.assertEqual(room["doctors"][0]["color"], "#abcdef")
