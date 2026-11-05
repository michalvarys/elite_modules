from datetime import date, timedelta

from odoo.exceptions import ValidationError
from odoo.tests import tagged

from .common import ReservationCase

WED = date(2026, 10, 14)


@tagged("post_install", "-at_install")
class TestBoard(ReservationCase):

    def setUp(self):
        super().setUp()
        self.hours(self.room1, 2, 8.25, 19.5)
        self.assign(self.dr_a, self.room1, WED, 8.0, 14.0)
        self.r = self.reservation(start=self.dt(WED, 9, 0))
        # The waiting queue shows only future requests, hence a relative date, not WED.
        self.future = date.today() + timedelta(days=30)
        self.w = self.reservation(start=self.dt(self.future, 10, 0), state="web_new", source="web", room_id=False)
        self.R = self.env["elite.vet.reservation"]

    def test_axis_starts_on_a_slot_step(self):
        """The grid lines must sit on the times the slots use, also with an odd opening time."""
        self.env["elite.vet.setting"].nastaveni().booking_slot_step = 20
        self.hours(self.room2, 2, 7.75, 12.0)   # 7:45 is not a multiple of 20
        self.assertEqual(self.R.board_data("2026-10-14")["axis"]["from"], 7 * 60 + 40)

    def test_board_data_shape(self):
        d = self.R.board_data("2026-10-14")
        self.assertEqual(d["date"], "2026-10-14")
        self.assertEqual(d["step"], 15)
        room = next(r for r in d["rooms"] if r["id"] == self.room1.id)
        self.assertEqual(room["open"], [[495, 1170]])
        self.assertEqual(room["doctors"][0]["name"], "MVDr. Alena Testová")
        ev = next(e for e in d["events"] if e["id"] == self.r.id)
        self.assertEqual((ev["start"], ev["end"], ev["room_id"]), (540, 555, self.room1.id))
        wrow = next(w for w in d["waiting"] if w["id"] == self.w.id)
        self.assertEqual(wrow["time"], "10:00")
        self.assertLessEqual(d["axis"]["from"], 480)
        self.assertGreaterEqual(d["axis"]["to"], 1170)

    def test_no_show_and_cancelled_leave_the_board(self):
        """The slot looks free again; the reservation stays in the history."""
        def on_board(res):
            return res.id in [e["id"] for e in self.R.board_data("2026-10-14")["events"]]

        cancelled = self.reservation(start=self.dt(WED, 10, 0))
        self.assertTrue(on_board(self.r) and on_board(cancelled))
        self.r.action_no_show()
        cancelled.action_cancel()
        self.assertFalse(on_board(self.r) or on_board(cancelled))
        self.assertEqual(self.r.state, "no_show")
        # the same time can be booked again
        self.assertTrue(self.reservation(start=self.dt(WED, 9, 0)))

    def test_board_move(self):
        self.R.board_move(self.r.id, "2026-10-14", 660, self.room2.id)
        self.assertEqual((self.r.start, self.r.room_id), (self.dt(WED, 11, 0), self.room2))

    def test_board_confirm_sets_room_and_state(self):
        self.R.board_confirm(self.w.id, "2026-10-14", 600, self.room1.id)
        self.assertEqual((self.w.state, self.w.room_id, self.w.start), ("confirmed", self.room1, self.dt(WED, 10, 0)))
        self.assertTrue(self.w.partner_id)

    def test_board_confirm_onto_busy_slot_fails(self):
        with self.assertRaises(ValidationError):
            self.R.board_confirm(self.w.id, "2026-10-14", 540, self.room1.id)

    def test_board_slot_utc(self):
        self.assertEqual(self.R.board_slot_utc("2026-10-14", 540), "2026-10-14 07:00:00")

    def test_board_data_hides_cancelled_block(self):
        block = self.env["elite.vet.reservation"].create({
            "kind": "block", "block_reason": "Test", "room_id": self.room1.id, "state": "confirmed",
            "start": self.dt(WED, 12, 0), "stop": self.dt(WED, 13, 0)})
        ids = [e["id"] for e in self.R.board_data("2026-10-14")["events"]]
        self.assertIn(block.id, ids)
        block.action_cancel()
        ids = [e["id"] for e in self.R.board_data("2026-10-14")["events"]]
        self.assertNotIn(block.id, ids)
