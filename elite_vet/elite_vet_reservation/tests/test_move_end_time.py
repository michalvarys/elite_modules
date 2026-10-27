"""Task 28: the move / confirm dialog sets the end time ("do") too.

board_move / board_confirm take an optional end_minute; the overlap check and the doctor-on-duty
rule apply to the whole new interval, the second-room copy follows, the e-mail checkbox still
works. The reservation form keeps start and stop editable for reception; a moved start keeps the
reservation's own length."""
from datetime import timedelta

from odoo import fields
from odoo.exceptions import UserError, ValidationError
from odoo.tests import Form, tagged

from .common import ReservationCase


@tagged("post_install", "-at_install")
class TestMoveEndTime(ReservationCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.day = fields.Date.today() + timedelta(days=9)
        cls.R = cls.env["elite.vet.reservation"]
        cls.env["elite.vet.setting"].nastaveni().write({
            "booking_require_doctor": False, "booking_slot_step": 15})
        cls.reception = cls.env["res.users"].with_context(no_reset_password=True).create({
            "name": "T34 recepce konec", "login": "t34_reception_end",
            "groups_id": [(6, 0, [cls.env.ref("base.group_user").id,
                                   cls.env.ref("elite_vet_reservation.group_reservation_reception").id])]})

    def mails(self, email):
        return self.env["mail.mail"].search_count([("email_to", "ilike", email)])

    def test_longer_and_shorter(self):
        r = self.reservation(start=self.dt(self.day, 9, 0))      # vaccination, 15 min
        self.R.board_move(r.id, self.day.isoformat(), 9 * 60, self.room1.id, True, 9 * 60 + 45)
        self.assertEqual((r.start, r.stop), (self.dt(self.day, 9, 0), self.dt(self.day, 9, 45)))
        # another time and a shorter end at once
        self.R.board_move(r.id, self.day.isoformat(), 10 * 60, self.room2.id, True, 10 * 60 + 15)
        self.assertEqual((r.start, r.stop, r.room_id), (self.dt(self.day, 10, 0), self.dt(self.day, 10, 15), self.room2))
        # without an end the (new) duration is kept, as before task 28
        self.R.board_move(r.id, self.day.isoformat(), 11 * 60, self.room2.id)
        self.assertEqual(r.duration_minutes, 15)

    def test_end_must_be_after_start(self):
        r = self.reservation(start=self.dt(self.day, 9, 0))
        for end in (9 * 60, 8 * 60 + 45, 1441, "konec"):
            with self.assertRaises(UserError), self.env.cr.savepoint():
                self.R.board_move(r.id, self.day.isoformat(), 9 * 60, self.room1.id, True, end)
        self.assertEqual((r.start, r.stop), (self.dt(self.day, 9, 0), self.dt(self.day, 9, 15)))
        with self.assertRaises(UserError):
            r.action_reschedule(self.dt(self.day, 9, 0), stop=self.dt(self.day, 8, 0))

    def test_longer_into_a_taken_time_is_refused(self):
        r = self.reservation(start=self.dt(self.day, 9, 0))
        self.reservation(start=self.dt(self.day, 10, 0), contact_email=False)
        with self.assertRaises(ValidationError), self.env.cr.savepoint():
            self.R.board_move(r.id, self.day.isoformat(), 9 * 60, self.room1.id, False, 10 * 60 + 10)
        self.assertEqual((r.start, r.stop), (self.dt(self.day, 9, 0), self.dt(self.day, 9, 15)))
        # up to the next one is fine
        self.R.board_move(r.id, self.day.isoformat(), 9 * 60, self.room1.id, False, 10 * 60)
        self.assertEqual(r.stop, self.dt(self.day, 10, 0))

    def test_doctor_on_duty_for_the_whole_new_interval(self):
        self.env["elite.vet.setting"].nastaveni().booking_require_doctor = True
        self.assign(self.dr_a, self.room1, self.day, 8.0, 12.0)
        r = self.reservation(start=self.dt(self.day, 11, 0), doctor_id=self.dr_a.id)
        with self.assertRaisesRegex(UserError, "neslouží"), self.env.cr.savepoint():
            self.R.board_move(r.id, self.day.isoformat(), 11 * 60, self.room1.id, True, 12 * 60 + 30)
        self.assertEqual(r.stop, self.dt(self.day, 11, 15))
        self.R.board_move(r.id, self.day.isoformat(), 11 * 60, self.room1.id, True, 12 * 60)
        self.assertEqual((r.stop, r.doctor_id), (self.dt(self.day, 12, 0), self.dr_a))

    def test_mail_checkbox_with_a_new_end(self):
        r = self.reservation(start=self.dt(self.day, 9, 0), contact_email="t34.konec@example.cz")
        before = self.mails("t34.konec@example.cz")
        # only the end changes: the e-mail shows the start only, so nothing goes out (as for a room change)
        self.R.board_move(r.id, self.day.isoformat(), 9 * 60, self.room1.id, True, 9 * 60 + 30)
        self.assertEqual(self.mails("t34.konec@example.cz"), before)
        # a new start and end, the checkbox unticked: silent, the chatter says so
        self.R.board_move(r.id, self.day.isoformat(), 10 * 60, self.room1.id, False, 10 * 60 + 45)
        self.assertEqual((r.start, r.stop), (self.dt(self.day, 10, 0), self.dt(self.day, 10, 45)))
        self.assertEqual(self.mails("t34.konec@example.cz"), before)
        self.assertTrue(r.message_ids.filtered(lambda m: "Klient nebyl o změně informován." in (m.body or "")))
        # ticked: one e-mail
        self.R.board_move(r.id, self.day.isoformat(), 11 * 60, self.room1.id, True, 11 * 60 + 20)
        self.assertEqual(self.mails("t34.konec@example.cz"), before + 1)
        self.assertEqual(r.duration_minutes, 20)

    def test_second_room_copy_follows_the_new_end(self):
        main = self.reservation(start=self.dt(self.day, 14, 0), doctor_id=self.dr_a.id)
        second = main.add_second_room(self.room2, self.dr_b)
        self.R.board_move(main.id, self.day.isoformat(), 14 * 60 + 30, self.room1.id, True, 15 * 60 + 30)
        self.assertEqual((second.start, second.stop, second.room_id),
                         (self.dt(self.day, 14, 30), self.dt(self.day, 15, 30), self.room2))

    def test_confirm_request_with_an_end(self):
        w = self.reservation(start=self.dt(self.day, 9, 0), state="web_new", source="web", room_id=False,
                             contact_email="t34.zadost@example.cz")
        self.R.board_confirm(w.id, self.day.isoformat(), 9 * 60 + 15, self.room1.id, None, False, 10 * 60)
        self.assertEqual((w.state, w.start, w.stop), ("confirmed", self.dt(self.day, 9, 15), self.dt(self.day, 10, 0)))
        self.assertFalse(self.mails("t34.zadost@example.cz"))
        other = self.reservation(start=self.dt(self.day, 11, 0), state="web_new", source="web", room_id=False,
                                 contact_email=False)
        with self.assertRaises(UserError), self.env.cr.savepoint():
            self.R.board_confirm(other.id, self.day.isoformat(), 11 * 60, self.room1.id, None, True, 11 * 60)
        self.assertEqual(other.state, "web_new")

    def test_reception_edits_start_and_end_in_the_form(self):
        """Backend "Upravit": Začátek and Konec are editable for reception; a new start keeps the
        reservation's own (longer) length, Konec can then be changed by hand."""
        r = self.reservation(start=self.dt(self.day, 9, 0))
        r.stop = self.dt(self.day, 9, 40)
        with Form(r.with_user(self.reception)) as form:
            form.start = self.dt(self.day + timedelta(days=1), 13, 0)
            self.assertEqual(form.stop, self.dt(self.day + timedelta(days=1), 13, 40))
            form.stop = self.dt(self.day + timedelta(days=1), 14, 0)
        self.assertEqual((r.start, r.stop), (self.dt(self.day + timedelta(days=1), 13, 0),
                                             self.dt(self.day + timedelta(days=1), 14, 0)))
        # a new reservation (or another procedure) takes the procedure's duration
        with Form(self.R.with_user(self.reception)) as form:
            form.procedure_id = self.derm
            form.room_id = self.room1
            form.contact_name = "T34 Formulář"
            form.start = self.dt(self.day, 15, 0)
            self.assertEqual(form.stop, self.dt(self.day, 15, 30))

    def test_dialog_has_the_end_time(self):
        from odoo.tools import file_open
        with file_open("elite_vet_reservation/static/src/move_dialog/move_dialog.xml") as f:
            xml = f.read()
        with file_open("elite_vet_reservation/static/src/move_dialog/move_dialog.js") as f:
            js = f.read()
        with file_open("elite_vet_reservation/static/src/board/board.js") as f:
            board = f.read()
        self.assertIn("o_ev_move_end", xml)
        self.assertIn(">Do<", xml)
        self.assertIn("endMinute", js)
        self.assertIn("Konec musí být po začátku.", js)
        self.assertIn("notify, endMinute, force]", board)
