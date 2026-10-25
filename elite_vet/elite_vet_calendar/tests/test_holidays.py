"""Task 17: Czech public holidays in Rozpis služeb (computed, nothing entered)."""
from datetime import date, timedelta

from odoo.tests import HttpCase, TransactionCase, tagged

from ..models.holidays import holiday_name, holidays_between


def holiday_in_shown_months(today):
    """A holiday in the current or the next month (the two months of /rozpis-lekaru), or None."""
    first = today.replace(day=1)
    after_next = ((first + timedelta(days=32)).replace(day=1) + timedelta(days=32)).replace(day=1)
    found = sorted(holidays_between(first, after_next - timedelta(days=1)))
    return found[0] if found else None


@tagged("post_install", "-at_install")
class TestShiftHolidays(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Shift = cls.env["elite.vet.shift"]
        cls.doctor = cls.env["elite.vet.doctor"].create({"name": "MVDr. Svátková T21"})
        cls.work = cls.env["elite.vet.shift.type"].create({"name": "Služba T21", "time_from": 8, "time_to": 14})
        cls.note = cls.env["elite.vet.shift.type"].create({"name": "Poznámka T21", "is_note": True, "color": "red"})

    def test_holiday_map(self):
        self.assertEqual(self.Shift.holiday_map(date(2026, 12, 21), date(2027, 1, 3)), {
            "2026-12-24": "Štědrý den", "2026-12-25": "1. svátek vánoční",
            "2026-12-26": "2. svátek vánoční", "2027-01-01": "Den obnovy samostatného českého státu, Nový rok"})
        self.assertEqual(self.Shift.holiday_map(False, "2026-12-31"), {})

    def test_roster_holidays_hand_note_wins(self):
        oct_28, nov_17 = date(2026, 10, 28), date(2026, 11, 17)
        self.assertEqual(self.Shift.roster_holidays(date(2026, 10, 1), date(2026, 12, 1)),
                         {oct_28: holiday_name(oct_28), nov_17: holiday_name(nov_17)})
        # a doctor on duty does not hide the holiday
        self.Shift.create({"date": oct_28, "doctor_id": self.doctor.id, "type_id": self.work.id})
        self.assertIn(oct_28, self.Shift.roster_holidays(date(2026, 10, 1), date(2026, 11, 1)))
        # a full-day note entered by hand does
        self.Shift.create({"date": oct_28, "type_id": self.note.id, "note": "Zavřeno T21"})
        self.assertEqual(self.Shift.roster_holidays(date(2026, 10, 1), date(2026, 11, 1)), {})
        # end exclusive (the first day of the next month)
        self.assertEqual(self.Shift.roster_holidays(date(2026, 11, 18), date(2026, 12, 24)), {})

    def test_calendar_view_uses_the_holiday_view(self):
        arch = self.env.ref("elite_vet_calendar.view_vet_shift_calendar").arch
        self.assertIn('js_class="elite_vet_holiday_calendar"', arch)


@tagged("post_install", "-at_install")
class TestRosterPageHolidays(HttpCase):

    def setUp(self):
        super().setUp()
        self.day = holiday_in_shown_months(date.today())
        if not self.day:
            self.skipTest("no public holiday in the current and the next month")
        self.name = holiday_name(self.day)
        self.doctor = self.env["elite.vet.doctor"].create({"name": "MVDr. Webová Svátková T21"})
        self.work = self.env["elite.vet.shift.type"].create({"name": "Služba web T21", "time_from": 8, "time_to": 14})
        self.note = self.env["elite.vet.shift.type"].create({"name": "Poznámka web T21", "is_note": True, "color": "red"})
        # the doctor serves on the holiday (the month is shown only with an entry)
        self.env["elite.vet.shift"].create({"date": self.day, "doctor_id": self.doctor.id, "type_id": self.work.id})

    def page(self):
        resp = self.url_open("/rozpis-lekaru")
        self.assertEqual(resp.status_code, 200)
        return resp.text

    def test_holiday_name_in_the_day_cell(self):
        html = self.page()
        self.assertIn('class="rs-cell-note rs-cell-holiday"', html)
        self.assertIn(self.name, html)
        self.assertIn("MVDr. Webová Svátková T21", html)   # still listed

    def test_hand_entered_note_wins(self):
        self.env["elite.vet.shift"].create({"date": self.day, "type_id": self.note.id, "note": "Zavřeno web T21"})
        html = self.page()
        self.assertIn("Zavřeno web T21", html)
        self.assertNotIn(self.name, html)
