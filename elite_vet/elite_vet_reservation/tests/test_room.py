from datetime import date

from odoo.exceptions import ValidationError
from odoo.tests import tagged
from odoo.tools import mute_logger

from .common import ReservationCase


@tagged("post_install", "-at_install")
class TestRoom(ReservationCase):

    def test_room_defaults(self):
        self.assertTrue(self.room1.online)
        self.assertFalse(self.sal.online)
        self.assertEqual(self.room1.color_hex, "#2b7870")

    def test_hours_require_from_before_to(self):
        with self.assertRaises(ValidationError):
            self.hours(self.room1, 0, 12.0, 8.0)

    def test_hours_no_overlap_same_day(self):
        self.hours(self.room1, 0, 8.0, 12.0)
        self.hours(self.room1, 0, 13.0, 18.0)          # prestavka je v poradku
        with self.assertRaises(ValidationError):
            self.hours(self.room1, 0, 11.0, 14.0)      # prekryva obe

    def test_hours_display(self):
        line = self.hours(self.room1, 2, 8.25, 19.5)
        self.assertEqual(line.display_name, "St 8:15–19:30")

    @mute_logger("odoo.sql_db")  # ocekavana chyba DB, at nezasviti log
    def test_exception_unique_per_day(self):
        Exc = self.env["elite.vet.room.exception"]
        Exc.create({"room_id": self.room1.id, "date": date(2026, 10, 28), "closed": True})
        with self.assertRaises(Exception):
            Exc.create({"room_id": self.room1.id, "date": date(2026, 10, 28), "hour_from": 8, "hour_to": 12})

    def test_exception_open_requires_hours(self):
        with self.assertRaises(ValidationError):
            self.env["elite.vet.room.exception"].create({
                "room_id": self.room1.id, "date": date(2026, 10, 29), "closed": False,
            })
