from datetime import date

from odoo.exceptions import ValidationError
from odoo.tests import tagged

from .common import ReservationCase


@tagged("post_install", "-at_install")
class TestDoctorAssignment(ReservationCase):

    def test_display_name(self):
        a = self.assign(self.dr_a, self.room1, date(2026, 10, 14), 8.0, 14.0)
        self.assertEqual(a.display_name, "MVDr. Alena Testová · Ordinace 1 · 8:00–14:00")

    def test_doctor_cannot_overlap_herself_in_one_room(self):
        self.assign(self.dr_a, self.room1, date(2026, 10, 14), 8.0, 14.0)
        self.assign(self.dr_a, self.room1, date(2026, 10, 14), 14.0, 18.0)   # adjacent, ok
        with self.assertRaises(ValidationError):
            self.assign(self.dr_a, self.room1, date(2026, 10, 14), 13.0, 15.0)

    def test_doctor_may_serve_two_rooms_at_once(self):
        self.assign(self.dr_a, self.room1, date(2026, 10, 14), 8.0, 14.0)
        both = self.assign(self.dr_a, self.room2, date(2026, 10, 14), 13.0, 15.0)
        self.assertTrue(both.exists())

    def test_serves_all_when_no_restriction(self):
        a = self.assign(self.dr_a, self.room1, date(2026, 10, 14), 8.0, 14.0)
        self.assertTrue(a.serves(self.vacc))
        self.assertTrue(a.serves(self.derm))

    def test_serves_only_listed_procedures(self):
        a = self.assign(self.dr_a, self.room1, date(2026, 10, 14), 8.0, 14.0, procedures=self.derm)
        self.assertFalse(a.serves(self.vacc))
        self.assertTrue(a.serves(self.derm))
