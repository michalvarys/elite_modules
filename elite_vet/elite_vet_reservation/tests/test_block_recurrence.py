"""Repeated blocks like in WinVet (feedback 31. 10., B1): period, every N, weekdays, end."""
from datetime import date, timedelta

from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, tagged

from ..models.recurrence import occurrence_dates
from .common import ReservationCase

SAT = date(2026, 10, 31)   # Saturday


@tagged("post_install", "-at_install")
class TestOccurrenceDates(TransactionCase):

    def test_daily_every_two_days_count(self):
        self.assertEqual(occurrence_dates(SAT, "daily", 2, (), "count", count=3),
                         [SAT, SAT + timedelta(days=2), SAT + timedelta(days=4)])

    def test_weekly_days_and_odd_weeks(self):
        # every 2nd week on Monday and Saturday, from Saturday 31. 10. (week of 26. 10.)
        got = occurrence_dates(SAT, "weekly", 2, (0, 5), "until", until=date(2026, 11, 23))
        self.assertEqual(got, [SAT, date(2026, 11, 9), date(2026, 11, 14), date(2026, 11, 23)])

    def test_weekly_without_days_uses_start_day(self):
        self.assertEqual(occurrence_dates(SAT, "weekly", 1, (), "count", count=2), [SAT, SAT + timedelta(days=7)])

    def test_start_not_on_a_checked_day(self):
        # the start date itself is not an occurrence then
        self.assertEqual(occurrence_dates(SAT, "weekly", 1, (0,), "count", count=2),
                         [date(2026, 11, 2), date(2026, 11, 9)])

    def test_monthly_skips_missing_days_and_yearly_leap_day(self):
        self.assertEqual(occurrence_dates(date(2027, 1, 31), "monthly", 1, (), "count", count=3),
                         [date(2027, 1, 31), date(2027, 3, 31), date(2027, 5, 31)])
        self.assertEqual(occurrence_dates(date(2028, 2, 29), "yearly", 1, (), "count", count=2),
                         [date(2028, 2, 29), date(2032, 2, 29)])

    def test_without_end_is_one_year_ahead(self):
        got = occurrence_dates(SAT, "weekly", 1, (), "never")
        self.assertEqual((got[0], got[-1], len(got)), (SAT, date(2027, 10, 30), 53))


@tagged("post_install", "-at_install")
class TestBlockRecurrence(ReservationCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.R = cls.env["elite.vet.reservation"]

    def block(self, **vals):
        base = {"kind": "block", "block_reason": "Opakovaná", "block_scope": "full", "room_id": self.room1.id,
                "start": self.dt(SAT, 8), "stop": self.dt(SAT, 8, 15)}
        base.update(vals)
        return self.R.create(base)

    def blocks(self):
        return self.R.search([("block_reason", "=", "Opakovaná")], order="start")

    def test_weekly_saturday_like_winvet(self):
        self.block(repeat_rule="weekly", repeat_interval=1, repeat_sat=True, repeat_end="count", repeat_count=10)
        blocks = self.blocks()
        self.assertEqual(len(blocks), 10)
        # 8:00 local stays 8:00 (31. 10. is summer time, the rest winter time)
        self.assertEqual([b.start for b in blocks[:2]], [self.dt(SAT, 8), self.dt(SAT + timedelta(days=7), 8)])
        self.assertEqual(blocks[-1].stop, self.dt(SAT + timedelta(days=63), 8, 15))
        self.assertEqual(set(blocks.mapped("repeat_rule")), {"none"}, "the rule is used once, at creation")

    def test_until_and_several_rooms(self):
        self.block(room_id=False, block_room_ids=[(6, 0, (self.room1 | self.room2).ids)],
                   repeat_rule="daily", repeat_interval=1, repeat_end="until", repeat_until=SAT + timedelta(days=2))
        blocks = self.blocks()
        self.assertEqual(len(blocks), 6)
        self.assertEqual(blocks.room_id, self.room1 | self.room2)

    def test_old_weekly_until_still_works(self):
        self.block(repeat_weekly_until=SAT + timedelta(days=14))
        self.assertEqual(len(self.blocks()), 3)

    def test_wrong_input_refused(self):
        with self.assertRaises(ValidationError):
            self.block(repeat_rule="daily", repeat_interval=0)
        with self.assertRaises(ValidationError):
            self.block(repeat_rule="daily", repeat_end="until", repeat_until=SAT - timedelta(days=1))
        with self.assertRaises(ValidationError):
            self.block(repeat_rule="daily", repeat_end="count", repeat_count=0)
