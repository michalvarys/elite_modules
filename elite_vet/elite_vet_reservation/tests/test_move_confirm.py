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

    def test_waiting_request_data_for_the_confirm_question(self):
        """Task 19: the board asks "Potvrdit žádost <pet (client)> na …?" before board_confirm and
        mentions the confirmation e-mail only for a request with an e-mail - what board_confirm
        (action_confirm) actually sends."""
        Mail = self.env["mail.mail"]
        with_mail = self.reservation(start=self.dt(self.day, 9, 0), state="web_new", source="web",
                                     room_id=False, contact_name="Jana T23", pet_name="Rex T23",
                                     contact_email="t23@example.cz")
        quiet = self.reservation(start=self.dt(self.day, 10, 0), state="web_new", source="web",
                                 room_id=False, contact_name="Petr T23", pet_name="Bobík T23",
                                 contact_email=False)
        waiting = {w["id"]: w for w in self.env["elite.vet.reservation"].board_data(self.day.isoformat())["waiting"]}
        self.assertEqual((waiting[with_mail.id]["pet"], waiting[with_mail.id]["owner"],
                          waiting[with_mail.id]["email"]), ("Rex T23", "Jana T23", "t23@example.cz"))
        self.assertEqual((waiting[quiet.id]["pet"], waiting[quiet.id]["email"]), ("Bobík T23", ""))
        before = Mail.search_count([("email_to", "ilike", "t23@example.cz")])
        Res = self.env["elite.vet.reservation"]
        Res.board_confirm(with_mail.id, self.day.isoformat(), 9 * 60, self.room1.id)
        self.assertEqual(with_mail.state, "confirmed")
        self.assertEqual(Mail.search_count([("email_to", "ilike", "t23@example.cz")]), before + 1)
        mails = Mail.search_count([])
        Res.board_confirm(quiet.id, self.day.isoformat(), 10 * 60, self.room1.id)
        self.assertEqual(quiet.state, "confirmed")
        self.assertEqual(Mail.search_count([]), mails)
