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

    # ---------------------------------------------------------------- task 25: date / time / e-mail choice

    def notes(self, rec, text):
        return rec.message_ids.filtered(lambda m: text in (m.body or ""))

    def test_move_to_another_day_and_time(self):
        """The dialog may change the date as well: board_move takes the chosen day."""
        r = self.reservation(start=self.dt(self.day, 9, 0))
        other = self.day + timedelta(days=1)
        self.env["elite.vet.reservation"].board_move(r.id, other.isoformat(), 10 * 60 + 5, self.room2.id)
        self.assertEqual((r.start, r.room_id), (self.dt(other, 10, 5), self.room2))

    def test_move_without_e_mail(self):
        Mail = self.env["mail.mail"]
        Res = self.env["elite.vet.reservation"]
        quiet = self.reservation(start=self.dt(self.day, 9, 0), contact_email="t31.ticho@example.cz")
        loud = self.reservation(start=self.dt(self.day, 11, 0), contact_email="t31.nahlas@example.cz")
        count = lambda email: Mail.search_count([("email_to", "ilike", email)])
        quiet_before, loud_before = count("t31.ticho@example.cz"), count("t31.nahlas@example.cz")
        Res.board_move(quiet.id, self.day.isoformat(), 9 * 60 + 30, self.room1.id, False)
        self.assertEqual(quiet.start, self.dt(self.day, 9, 30))
        self.assertEqual(count("t31.ticho@example.cz"), quiet_before)
        self.assertTrue(self.notes(quiet, "Klient nebyl o změně informován."))
        self.assertFalse(quiet.reminder_sent)
        Res.board_move(loud.id, self.day.isoformat(), 11 * 60 + 30, self.room1.id, True)
        self.assertEqual(count("t31.nahlas@example.cz"), loud_before + 1)
        self.assertTrue(Mail.search([("email_to", "ilike", "t31.nahlas@example.cz")]).filtered(
            lambda m: m.state == "outgoing"))
        self.assertFalse(self.notes(loud, "Klient nebyl o změně informován."))
        # the next move of the quiet one e-mails again (only that one move was silent)
        Res.board_move(quiet.id, self.day.isoformat(), 10 * 60, self.room1.id)
        self.assertEqual(count("t31.ticho@example.cz"), quiet_before + 1)

    def test_confirm_without_e_mail(self):
        Mail = self.env["mail.mail"]
        Res = self.env["elite.vet.reservation"]
        quiet = self.reservation(start=self.dt(self.day, 9, 0), state="web_new", source="web", room_id=False,
                                 contact_email="t31.potvrzeni@example.cz")
        loud = self.reservation(start=self.dt(self.day, 10, 0), state="web_new", source="web", room_id=False,
                                contact_email="t31.potvrzeni2@example.cz")
        # the dialog may also move the time before confirming
        Res.board_confirm(quiet.id, self.day.isoformat(), 9 * 60 + 15, self.room1.id, None, False)
        self.assertEqual((quiet.state, quiet.start), ("confirmed", self.dt(self.day, 9, 15)))
        self.assertFalse(Mail.search_count([("email_to", "ilike", "t31.potvrzeni@example.cz")]))
        self.assertTrue(self.notes(quiet, "Klient nebyl o potvrzení informován."))
        Res.board_confirm(loud.id, self.day.isoformat(), 10 * 60, self.room1.id, None, True)
        self.assertEqual(Mail.search_count([("email_to", "ilike", "t31.potvrzeni2@example.cz"),
                                            ("state", "=", "outgoing")]), 1)
        self.assertFalse(self.notes(loud, "Klient nebyl o potvrzení informován."))

    def test_busy_time_keeps_the_reservation(self):
        """A taken time: the server refuses (the dialog shows it) and nothing changes."""
        from odoo.exceptions import ValidationError
        r = self.reservation(start=self.dt(self.day, 9, 0))
        self.reservation(start=self.dt(self.day, 12, 0), contact_email=False)
        with self.assertRaises(ValidationError), self.env.cr.savepoint():
            self.env["elite.vet.reservation"].board_move(r.id, self.day.isoformat(), 12 * 60, self.room1.id, False)
        self.assertEqual(r.start, self.dt(self.day, 9, 0))

    def test_board_assets_have_the_move_dialog(self):
        from odoo.tools import file_open
        with file_open("elite_vet_reservation/static/src/board/board.js") as f:
            js = f.read()
        with file_open("elite_vet_reservation/static/src/move_dialog/move_dialog.xml") as f:
            xml = f.read()
        self.assertIn("MoveConfirmDialog", js)
        for text in ('type="date"', 'type="time"', "o_ev_move_room", "o_ev_move_error", "props.mailLabel"):
            self.assertIn(text, xml)
        self.assertIn("Poslat klientovi e-mail o změně", js)
        self.assertIn("Poslat klientovi potvrzení", js)
