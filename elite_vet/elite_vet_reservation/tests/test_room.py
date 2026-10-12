from datetime import date

import psycopg2

from odoo.exceptions import ValidationError
from odoo.tests import tagged
from odoo.tools import mute_logger

from .common import ReservationCase


@tagged("post_install", "-at_install")
class TestRoom(ReservationCase):

    def test_room_defaults(self):
        self.assertTrue(self.room1.online)
        self.assertFalse(self.surgery.online)
        self.assertEqual(self.room1.color_hex, "#2b7870")

    def test_hours_require_from_before_to(self):
        with self.assertRaises(ValidationError):
            self.hours(self.room1, 0, 12.0, 8.0)

    def test_hours_no_overlap_same_day(self):
        self.hours(self.room1, 0, 8.0, 12.0)
        self.hours(self.room1, 0, 13.0, 18.0)          # a break is fine
        with self.assertRaises(ValidationError):
            self.hours(self.room1, 0, 11.0, 14.0)      # overlaps both

    def test_hours_display(self):
        line = self.hours(self.room1, 2, 8.25, 19.5)
        self.assertEqual(line.display_name, "St 8:15–19:30")

    @mute_logger("odoo.sql_db")  # expected DB error, keep it out of the log
    def test_exception_unique_per_day(self):
        Exc = self.env["elite.vet.room.exception"]
        Exc.create({"room_id": self.room1.id, "date": date(2026, 10, 28), "closed": True})
        with self.assertRaises(psycopg2.IntegrityError):
            Exc.create({"room_id": self.room1.id, "date": date(2026, 10, 28), "hour_from": 8, "hour_to": 12})

    def test_exception_open_requires_hours(self):
        with self.assertRaises(ValidationError):
            self.env["elite.vet.room.exception"].create({
                "room_id": self.room1.id, "date": date(2026, 10, 29), "closed": False,
            })

    def test_hours_overlap_allowed_when_validity_disjoint(self):
        # Summer and winter schedule: same day and time, but the validity periods do not overlap.
        self.hours(self.room1, 0, 8.0, 12.0, date_from=date(2026, 4, 1), date_to=date(2026, 9, 30))
        self.hours(self.room1, 0, 9.0, 13.0, date_from=date(2026, 10, 1), date_to=date(2027, 3, 31))

    def test_hours_overlap_refused_when_validity_overlaps(self):
        self.hours(self.room1, 0, 8.0, 12.0, date_from=date(2026, 4, 1), date_to=date(2026, 10, 31))
        with self.assertRaises(ValidationError):
            self.hours(self.room1, 0, 9.0, 13.0, date_from=date(2026, 10, 1), date_to=date(2027, 3, 31))

    def test_hours_validity_from_after_to_refused(self):
        with self.assertRaises(ValidationError):
            self.hours(self.room1, 0, 8.0, 12.0, date_from=date(2026, 10, 2), date_to=date(2026, 10, 1))

    def test_applies_on_day(self):
        window = self.hours(self.room1, 0, 8.0, 12.0, date_from=date(2026, 4, 1), date_to=date(2026, 9, 30))
        self.assertTrue(window.applies_on(date(2026, 6, 15)))
        self.assertTrue(window.applies_on(date(2026, 4, 1)))
        self.assertTrue(window.applies_on(date(2026, 9, 30)))
        self.assertFalse(window.applies_on(date(2026, 3, 31)))
        self.assertFalse(window.applies_on(date(2026, 10, 1)))
        open_ended = self.hours(self.room2, 1, 8.0, 12.0)
        self.assertTrue(open_ended.applies_on(date(2030, 1, 1)))
