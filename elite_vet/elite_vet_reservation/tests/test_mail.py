from datetime import date, timedelta

from odoo import fields
from odoo.tests import HttpCase, tagged

from .common import ReservationCase

WED = date(2026, 10, 14)


@tagged("post_install", "-at_install")
class TestMail(ReservationCase):

    def mails_to(self, email):
        return self.env["mail.mail"].search([("email_to", "ilike", email)], order="id")

    def test_web_received_sends_two_mails(self):
        r = self.reservation(start=self.dt(WED, 9, 0), state="web_new", source="web", room_id=False)
        r._po_prijeti_z_webu()
        self.assertEqual(len(self.mails_to("klient@example.cz")), 1)
        self.assertEqual(len(self.mails_to("info@elite-vet.cz")), 1)
        self.assertIn("Vaccination", self.mails_to("klient@example.cz").subject)

    def test_confirm_sends_confirmation_with_cancel_link(self):
        r = self.reservation(start=self.dt(WED, 9, 0), state="web_new", source="web")
        r.action_confirm()
        mail = self.mails_to("klient@example.cz")[-1]
        self.assertIn("/rezervace/zruseni/" + r.cancel_token, mail.body_html)
        self.assertIn("Ordinace 1", mail.body_html)

    def test_cancel_sends_mail(self):
        r = self.reservation(start=self.dt(WED, 9, 0))
        r.action_cancel("clinic")
        self.assertTrue(self.mails_to("klient@example.cz"))

    def test_reminder_cron_marks_and_sends_once(self):
        soon = fields.Datetime.now() + timedelta(hours=20)
        r = self.reservation(start=soon)
        s = self.env["elite.vet.setting"].nastaveni()
        s.write({"booking_reminder_enabled": True, "booking_reminder_hours_before": 24})
        self.env["elite.vet.reservation"]._cron_pripominky()
        self.assertTrue(r.reminder_sent)
        self.assertEqual(len(self.mails_to("klient@example.cz")), 1)
        self.env["elite.vet.reservation"]._cron_pripominky()
        self.assertEqual(len(self.mails_to("klient@example.cz")), 1)

    def test_start_display_in_prague_time(self):
        r = self.reservation(start=self.dt(WED, 9, 0))
        self.assertEqual(r.start_display, "14. 10. 2026 9:00")


@tagged("post_install", "-at_install")
class TestCancelPage(HttpCase):

    def setUp(self):
        super().setUp()
        room = self.env["elite.vet.room"].create({"name": "R", "color": "teal"})
        proc = self.env["elite.vet.procedure"].create({"name": "P", "duration": 15})
        self.far = self.env["elite.vet.reservation"].create({
            "procedure_id": proc.id, "room_id": room.id, "state": "confirmed",
            "start": fields.Datetime.now() + timedelta(days=3), "contact_name": "A B", "contact_email": "a@example.cz"})
        self.near = self.env["elite.vet.reservation"].create({
            "procedure_id": proc.id, "room_id": room.id, "state": "confirmed",
            "start": fields.Datetime.now() + timedelta(hours=2), "contact_name": "A B", "contact_email": "a@example.cz"})

    def test_cancel_page_and_post(self):
        resp = self.url_open("/rezervace/zruseni/" + self.far.cancel_token)
        self.assertEqual(resp.status_code, 200)
        self.assertIn("A B", resp.text)
        resp = self.url_open("/rezervace/zruseni/" + self.far.cancel_token, data={"potvrdit": "1"})
        self.assertEqual(resp.status_code, 200)
        self.far.invalidate_recordset()
        self.assertEqual((self.far.state, self.far.cancel_reason), ("cancelled", "client"))

    def test_cancel_page_after_deadline(self):
        resp = self.url_open("/rezervace/zruseni/" + self.near.cancel_token, data={"potvrdit": "1"})
        self.assertEqual(resp.status_code, 200)
        self.near.invalidate_recordset()
        self.assertEqual(self.near.state, "confirmed")

    def test_cancel_twice(self):
        self.far.action_cancel("client")
        resp = self.url_open("/rezervace/zruseni/" + self.far.cancel_token, data={"potvrdit": "1"})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(self.far.state, "cancelled")

    def test_unknown_token_404(self):
        resp = self.url_open("/rezervace/zruseni/neexistuje")
        self.assertEqual(resp.status_code, 404)

    def test_deposit_page_renders(self):
        resp = self.url_open("/rezervace/platba/" + self.far.cancel_token)
        self.assertEqual(resp.status_code, 200)
        self.assertIn("No deposit", resp.text)
