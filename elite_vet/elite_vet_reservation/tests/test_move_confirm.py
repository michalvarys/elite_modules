"""Request 25. 10.: a drop on the board asks first; the board data says whether the client gets
an e-mail about the new time."""
from datetime import timedelta

from odoo import fields
from odoo.tests import tagged

from .common import ReservationCase


@tagged("post_install", "-at_install")
class TestMoveConfirm(ReservationCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.day = fields.Date.today() + timedelta(days=9)

    def events(self):
        return {e["id"]: e for e in self.env["elite.vet.reservation"].board_data(self.day.isoformat())["events"]}

    def test_mail_on_move(self):
        with_mail = self.reservation(start=self.dt(self.day, 9, 0))
        without = self.reservation(start=self.dt(self.day, 10, 0), contact_email=False)
        done = self.reservation(start=self.dt(self.day, 11, 0), state="done")
        block = self.env["elite.vet.reservation"].create({
            "kind": "block", "state": "confirmed", "block_reason": "Oběd T22", "block_scope": "full",
            "room_id": self.room2.id, "start": self.dt(self.day, 12), "stop": self.dt(self.day, 13)})
        events = self.events()
        self.assertEqual(events[with_mail.id]["mail_on_move"], "klient@example.cz")
        self.assertFalse(events[without.id]["mail_on_move"])
        self.assertFalse(events[done.id]["mail_on_move"])
        self.assertFalse(events[block.id]["mail_on_move"])

    def test_second_room_tells_through_the_main(self):
        main = self.reservation(start=self.dt(self.day, 14, 0), doctor_id=self.dr_a.id)
        second = main.add_second_room(self.room2, self.dr_b)
        self.assertEqual(self.events()[second.id]["mail_on_move"], "klient@example.cz")

    def test_move_sends_the_mail_it_announces(self):
        """What the dialog promises is what board_move does: a new time e-mails the client,
        the same time in another room does not."""
        r = self.reservation(start=self.dt(self.day, 15, 0))
        Mail = self.env["mail.mail"]
        before = Mail.search_count([("email_to", "ilike", "klient@example.cz")])
        self.env["elite.vet.reservation"].board_move(r.id, self.day.isoformat(), 15 * 60, self.room2.id)
        self.assertEqual(Mail.search_count([("email_to", "ilike", "klient@example.cz")]), before)
        self.env["elite.vet.reservation"].board_move(r.id, self.day.isoformat(), 16 * 60, self.room2.id)
        self.assertEqual(Mail.search_count([("email_to", "ilike", "klient@example.cz")]), before + 1)
