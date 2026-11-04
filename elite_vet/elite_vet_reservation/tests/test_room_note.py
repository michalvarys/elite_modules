from datetime import date

from odoo.exceptions import ValidationError
from odoo.tests import tagged

from .common import ReservationCase

MON = date(2026, 11, 9)


@tagged("post_install", "-at_install")
class TestRoomNote(ReservationCase):

    def setUp(self):
        super().setUp()
        self.Note = self.env["elite.vet.room.note"]

    def note(self, **vals):
        return self.Note.create(dict({"room_id": self.room1.id, "date": MON, "text": "Jen očkování"}, **vals))

    def days(self):
        return self.Note.search([("room_id", "=", self.room1.id)]).mapped("date")

    def test_shown_on_the_board_of_its_day_and_room_only(self):
        note = self.note()
        rooms = {r["id"]: r for r in self.env["elite.vet.reservation"].board_data("2026-11-09")["rooms"]}
        self.assertEqual(rooms[self.room1.id]["notes"], [{"id": note.id, "text": "Jen očkování"}])
        self.assertEqual(rooms[self.room2.id]["notes"], [])
        rooms = {r["id"]: r for r in self.env["elite.vet.reservation"].board_data("2026-11-10")["rooms"]}
        self.assertEqual(rooms[self.room1.id]["notes"], [])

    def test_single_note_has_no_series(self):
        self.assertFalse(self.note().in_series)

    def test_weekly_until(self):
        self.note(repeat_rule="weekly", repeat_end="until", repeat_until=date(2026, 11, 23))
        self.assertEqual(self.days(), [MON, date(2026, 11, 16), date(2026, 11, 23)])

    def test_weekly_on_chosen_days_counts_the_note_itself(self):
        self.note(repeat_rule="weekly", repeat_mon=True, repeat_wed=True, repeat_end="count", repeat_count=3)
        self.assertEqual(self.days(), [MON, date(2026, 11, 11), date(2026, 11, 16)])

    def test_until_before_the_note_is_refused(self):
        with self.assertRaises(ValidationError):
            self.note(repeat_rule="daily", repeat_end="until", repeat_until=date(2026, 11, 8))

    def test_edit_changes_one_day_only(self):
        note = self.note(repeat_rule="daily", repeat_end="count", repeat_count=2)
        note.text = "Jiný text"
        self.assertEqual(sorted(self.Note.search([("room_id", "=", self.room1.id)]).mapped("text")),
                         ["Jen očkování", "Jiný text"])

    def test_delete_following_keeps_earlier_days(self):
        self.note(repeat_rule="daily", repeat_end="count", repeat_count=3)
        self.Note.search([("date", "=", date(2026, 11, 10))]).action_delete_following()
        self.assertEqual(self.days(), [MON])

    def test_delete_one_day(self):
        self.note(repeat_rule="daily", repeat_end="count", repeat_count=3)
        self.Note.search([("date", "=", date(2026, 11, 10))]).action_delete()
        self.assertEqual(self.days(), [MON, date(2026, 11, 11)])
