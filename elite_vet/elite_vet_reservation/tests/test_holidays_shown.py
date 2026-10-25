"""Task 17: Czech public holidays shown wherever a day is shown.

Reception is only warned, never blocked; the website keeps booking_block_holidays.
The holidays are computed (models/holidays.py, now in elite_vet_calendar), no records.
"""
import json
from datetime import date, timedelta

from odoo import fields
from odoo.tests import HttpCase, tagged

from odoo.addons.elite_vet_calendar.models import holidays as calendar_holidays

from ..models import holidays
from ..models.holidays import czech_holidays, easter_sunday, holiday_name, holidays_between
from .common import ReservationCase

OCT_28 = date(2026, 10, 28)   # Wednesday, Den vzniku samostatného československého státu
NOV_17 = date(2026, 11, 17)   # Tuesday, Den boje za svobodu a demokracii


def next_holiday(start, min_days=2):
    """The first holiday at least `min_days` after `start` (any year)."""
    day = start + timedelta(days=min_days)
    while not holiday_name(day):
        day += timedelta(days=1)
    return day


@tagged("post_install", "-at_install")
class TestHolidayCode(ReservationCase):

    def test_reexport_from_the_calendar_module(self):
        # moved to elite_vet_calendar; the old import path is the same code
        self.assertIs(holidays.holiday_name, calendar_holidays.holiday_name)
        self.assertIs(holidays.czech_holidays, calendar_holidays.czech_holidays)

    def test_easter_dates(self):
        for year, sunday in ((2024, date(2024, 3, 31)), (2025, date(2025, 4, 20)), (2027, date(2027, 3, 28)),
                             (2028, date(2028, 4, 16)), (2038, date(2038, 4, 25)), (2285, date(2285, 3, 22))):
            self.assertEqual(easter_sunday(year), sunday, year)
            self.assertEqual(czech_holidays(year)[sunday - timedelta(days=2)], "Velký pátek")
            self.assertEqual(czech_holidays(year)[sunday + timedelta(days=1)], "Velikonoční pondělí")
            self.assertEqual(len(czech_holidays(year)), 13)

    def test_holidays_between_spans_years(self):
        out = holidays_between(date(2026, 12, 24), date(2027, 1, 1))
        self.assertEqual(sorted(out), [date(2026, 12, 24), date(2026, 12, 25), date(2026, 12, 26), date(2027, 1, 1)])
        self.assertEqual(holidays_between(date(2026, 10, 29), date(2026, 11, 16)), {})

    def test_holiday_map_of_the_calendar_views(self):
        Shift = self.env["elite.vet.shift"]
        self.assertEqual(Shift.holiday_map("2026-10-26", "2026-11-22"), {
            "2026-10-28": "Den vzniku samostatného československého státu",
            "2026-11-17": "Den boje za svobodu a demokracii"})
        self.assertEqual(Shift.holiday_map("2026-11-02", "2026-11-08"), {})
        self.assertEqual(Shift.holiday_map("2026-11-08", "2026-11-02"), {})
        # a reception user (not a calendar manager) may ask too: nothing is read
        reception = self.env["res.users"].with_context(no_reset_password=True).create({
            "name": "Recepce Svátky", "login": "recepce_svatky_t21",
            "groups_id": [(6, 0, [self.env.ref("base.group_user").id,
                                  self.env.ref("elite_vet_reservation.group_reservation_reception").id])]})
        self.assertIn("2026-10-28", Shift.with_user(reception).holiday_map("2026-10-01", "2026-10-31"))
        # computed only: no shift records appear
        count = Shift.search_count([])
        Shift.holiday_map("2026-01-01", "2026-12-31")
        self.assertEqual(Shift.search_count([]), count)
        # a hand-made huge range is capped
        self.assertLessEqual(len(Shift.holiday_map("2000-01-01", "2100-12-31")), 20)


@tagged("post_install", "-at_install")
class TestHolidayOnTheBoard(ReservationCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.R = cls.env["elite.vet.reservation"]
        cls.s = cls.env["elite.vet.setting"].nastaveni()

    def test_badge_when_the_web_books(self):
        data = self.R.board_data(OCT_28.isoformat())
        self.assertEqual(data["holiday"], {
            "name": "Den vzniku samostatného československého státu", "web_closed": False,
            "label": "Státní svátek: Den vzniku samostatného československého státu"})
        self.assertEqual(data["day_note"], "")

    def test_badge_when_the_web_is_closed(self):
        self.s.booking_block_holidays = True
        data = self.R.board_data(NOV_17.isoformat())
        self.assertEqual(data["holiday"]["label"],
                         "Státní svátek: Den boje za svobodu a demokracii · web neobjednává")
        self.assertTrue(data["holiday"]["web_closed"])
        # day_note stays as before (older screens)
        self.assertEqual(data["day_note"], "Státní svátek: Den boje za svobodu a demokracii – web neobjednává")

    def test_no_holiday(self):
        data = self.R.board_data("2026-10-27")
        self.assertIs(data["holiday"], False)
        self.assertEqual(data["week_holidays"], {"2026-10-28": "Den vzniku samostatného československého státu"})
        self.assertEqual(self.R.board_data("2026-11-04")["week_holidays"], {})

    def test_week_chips(self):
        self.assertEqual(self.R.board_data("2026-12-27")["week_holidays"], {
            "2026-12-24": "Štědrý den", "2026-12-25": "1. svátek vánoční", "2026-12-26": "2. svátek vánoční"})
        # Monday-Sunday of the shown day, across the new year
        self.assertEqual(sorted(self.R.board_data("2026-12-31")["week_holidays"]), ["2027-01-01"])


@tagged("post_install", "-at_install")
class TestHolidayInTheWizard(ReservationCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        for wd in range(7):
            cls.hours(cls, cls.room1, wd, 8.0, 18.0)
        cls.env["elite.vet.setting"].nastaveni().write({
            "booking_require_doctor": False, "booking_block_holidays": True, "booking_slot_step": 15})
        cls.W = cls.env["elite.vet.reservation.wizard"]

    def test_warning_only_on_a_holiday(self):
        w = self.W.create({"procedure_id": self.vacc.id, "date": NOV_17})
        self.assertEqual(w.holiday_warning,
                         "Státní svátek: Den boje za svobodu a demokracii – jen upozornění, rezervaci lze uložit.")
        w.date = NOV_17 + timedelta(days=1)
        self.assertFalse(w.holiday_warning)
        self.assertFalse(self.W.create({"procedure_id": self.vacc.id, "date": date(2026, 11, 18)}).holiday_warning)

    def test_reception_still_books_on_a_holiday(self):
        day = next_holiday(fields.Date.today())
        w = self.W.create({"procedure_id": self.vacc.id, "date": day})
        self.assertTrue(w.holiday_warning)
        w.action_step_time()
        self.assertEqual(w.step, "time")
        self.assertTrue(w.slot_ids, "the holiday blocks the website only, reception gets free times")
        w.slot_ids[0].action_select()
        self.assertEqual(w.step, "client")

    def test_warning_in_the_form(self):
        arch = self.env.ref("elite_vet_reservation.view_reservation_wizard_form").arch
        self.assertIn('name="holiday_warning"', arch)
        self.assertIn('invisible="not holiday_warning"', arch)


@tagged("post_install", "-at_install")
class TestHolidayMonthResponse(HttpCase):

    def setUp(self):
        super().setUp()
        from odoo.addons.elite_vet_reservation.controllers import booking
        booking._SUBMITS.clear()
        self.env["elite.vet.reservation"].search([]).unlink()
        self.env["elite.vet.room"].search([]).write({"active": False})
        room = self.env["elite.vet.room"].create({"name": "Ordinace T21", "color": "teal"})
        for wd in range(7):
            self.env["elite.vet.room.hours"].create({"room_id": room.id, "weekday": str(wd),
                                                    "hour_from": 8.0, "hour_to": 18.0})
        self.proc = self.env["elite.vet.procedure"].create({"name": "Očkování T21", "duration": 15, "symbol": "V"})
        self.holiday = next_holiday(date.today(), min_days=3)
        self.setting = self.env["elite.vet.setting"].nastaveni()
        self.setting.write({"booking_block_weekends": False, "booking_block_holidays": False,
                            "booking_require_doctor": False, "booking_min_hours_before": 0,
                            "booking_max_days_ahead": (self.holiday - date.today()).days + 5})

    def rpc(self, path, params):
        resp = self.url_open(path, data=json.dumps({"jsonrpc": "2.0", "method": "call", "params": params}),
                             headers={"Content-Type": "application/json"})
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertNotIn("error", body, body.get("error"))
        return body["result"]

    def month(self, **extra):
        params = {"procedure_id": self.proc.id, "year": self.holiday.year, "month": self.holiday.month}
        params.update(extra)
        return self.rpc("/rezervace/api/days", params)

    def expected_holidays(self):
        return {d.isoformat(): n for d, n in czech_holidays(self.holiday.year).items() if d.month == self.holiday.month}

    def test_plain_list_stays_for_older_callers(self):
        res = self.month()
        self.assertIsInstance(res, list)
        self.assertIn(self.holiday.isoformat(), res)

    def test_holidays_marked_when_the_web_books(self):
        res = self.month(with_holidays=True)
        self.assertEqual(set(res), {"days", "holidays", "holidays_closed"})
        self.assertEqual(res["holidays"], self.expected_holidays())
        self.assertEqual(res["holidays"][self.holiday.isoformat()], holiday_name(self.holiday))
        self.assertFalse(res["holidays_closed"])
        self.assertIn(self.holiday.isoformat(), res["days"])   # open: just marked
        self.assertEqual(res["days"], self.month())

    def test_holidays_marked_when_the_web_is_closed(self):
        self.setting.booking_block_holidays = True
        res = self.month(with_holidays=True)
        self.assertTrue(res["holidays_closed"])
        self.assertNotIn(self.holiday.isoformat(), res["days"])   # unavailable, the reason is the holiday
        self.assertEqual(res["holidays"][self.holiday.isoformat()], holiday_name(self.holiday))

    def test_unknown_procedure_and_bad_month(self):
        self.assertEqual(self.rpc("/rezervace/api/days", {"procedure_id": 0, "year": 2026, "month": 10}), [])
        res = self.rpc("/rezervace/api/days", {"procedure_id": 0, "year": 2026, "month": 10, "with_holidays": True})
        self.assertEqual(res, {"days": [], "holidays_closed": False,
                               "holidays": {"2026-10-28": "Den vzniku samostatného československého státu"}})
        res = self.rpc("/rezervace/api/days", {"procedure_id": 0, "year": "x", "month": 10, "with_holidays": True})
        self.assertEqual(res["holidays"], {})
