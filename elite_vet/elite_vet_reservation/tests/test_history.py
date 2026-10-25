"""Request 25. 10.: Historie rezervací (Správce rezervací) and Obnovit of a cancelled reservation."""
from datetime import timedelta

from odoo import fields
from odoo.exceptions import AccessError, UserError
from odoo.tests import Form, tagged
from odoo.tools.safe_eval import safe_eval

from .common import ReservationCase


@tagged("post_install", "-at_install")
class TestReservationHistory(ReservationCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.day = fields.Date.today() + timedelta(days=12)
        Users = cls.env["res.users"].with_context(no_reset_password=True)

        def user(login, group):
            return Users.create({"name": "T22 %s" % login, "login": login, "groups_id": [
                (6, 0, [cls.env.ref("base.group_user").id, cls.env.ref(group).id])]})

        cls.manager = user("t22_hist_manager", "elite_vet_reservation.group_reservation_manager")
        cls.reception = user("t22_hist_reception", "elite_vet_reservation.group_reservation_reception")

    def commit_tracking(self):
        """Mail tracking values are written in the pre-commit hook."""
        self.env.flush_all()
        self.env.cr.precommit.run()

    def client_mails(self):
        return self.env["mail.mail"].search_count([("email_to", "ilike", "klient@example.cz")])

    def restore(self, reservation, user=None, **vals):
        Wizard = self.env["elite.vet.reservation.restore.wizard"].with_user(user or self.manager)
        action = reservation.with_user(user or self.manager).action_restore_wizard()
        with Form(Wizard.with_context(action["context"])) as form:
            for key, value in vals.items():
                setattr(form, key, value)
        return form.record.action_restore()

    def test_menu_and_action_for_the_manager_only(self):
        menu = self.env.ref("elite_vet_reservation.menu_reservation_history")
        self.assertEqual(menu.groups_id, self.env.ref("elite_vet_reservation.group_reservation_manager"))
        action = self.env.ref("elite_vet_reservation.action_reservation_history")
        self.assertEqual(safe_eval(action.domain), [("kind", "=", "reservation")])
        visible = self.env["ir.ui.menu"].with_user(self.reception)._visible_menu_ids()
        self.assertNotIn(menu.id, visible)
        self.assertIn(menu.id, self.env["ir.ui.menu"].with_user(self.manager)._visible_menu_ids())

    def test_tracking_of_the_important_fields(self):
        fields_ = self.env["elite.vet.reservation"]._fields
        for name in ("state", "start", "room_id", "doctor_id", "procedure_id", "partner_id", "pet_id",
                     "cancel_reason"):
            self.assertTrue(fields_[name].tracking, name)

    def test_who_and_when_cancelled(self):
        r = self.reservation(start=self.dt(self.day, 9, 0))
        r.with_user(self.manager).action_cancel()
        self.assertEqual(r.cancelled_by_id, self.manager)
        self.assertTrue(r.cancelled_at)
        self.assertEqual(r.cancel_reason, "clinic")

    def test_moved_filter(self):
        moved = self.reservation(start=self.dt(self.day, 9, 0))
        still = self.reservation(start=self.dt(self.day, 11, 0))
        self.commit_tracking()
        moved.action_reschedule(self.dt(self.day, 10, 0))
        still.write({"note": "jen poznámka"})
        self.commit_tracking()
        search = self.env.ref("elite_vet_reservation.view_reservation_history_search")
        self.assertIn("('was_moved', '=', True)", search.arch)
        # as the manager (tracking values themselves are for the administrator only)
        R = self.env["elite.vet.reservation"].with_user(self.manager)
        both = [("id", "in", (moved | still).ids)]
        self.assertEqual(R.search(both + [("was_moved", "=", True)]), moved)
        self.assertEqual(R.search(both + [("was_moved", "=", False)]), still)
        self.assertEqual((moved.was_moved, still.was_moved), (True, False))

    def test_restore_free_slot_without_mail(self):
        r = self.reservation(start=self.dt(self.day, 9, 0))
        r.action_cancel()
        mails = self.client_mails()
        self.restore(r)
        self.assertEqual(r.state, "confirmed")
        self.assertFalse(r.cancel_reason or r.cancelled_by_id or r.cancelled_at)
        self.assertEqual(self.client_mails(), mails, "no e-mail unless ticked")
        self.assertIn("Rezervaci obnovil(a) T22 t22_hist_manager", r.message_ids[0].body)

    def test_restore_with_confirmation_mail(self):
        r = self.reservation(start=self.dt(self.day, 10, 0))
        r.action_cancel()
        mails = self.client_mails()
        self.restore(r, send_confirmation=True)
        self.assertEqual(r.state, "confirmed")
        self.assertEqual(self.client_mails(), mails + 1)

    def test_restore_taken_slot(self):
        r = self.reservation(start=self.dt(self.day, 13, 0))
        r.action_cancel()
        self.reservation(start=self.dt(self.day, 13, 0), contact_email="jiny@example.cz")
        with self.assertRaisesRegex(UserError, "termín už není volný"):
            self.restore(r)
        self.assertEqual(r.state, "cancelled")
        # another time offered in the same wizard
        self.restore(r, start=self.dt(self.day, 14, 0))
        self.assertEqual((r.state, r.start), ("confirmed", self.dt(self.day, 14, 0)))

    def test_restore_rules(self):
        past = self.reservation(start=self.dt(fields.Date.today() - timedelta(days=3), 9, 0))
        past.action_cancel()
        with self.assertRaisesRegex(UserError, "v minulosti"):
            self.restore(past)
        confirmed = self.reservation(start=self.dt(self.day, 16, 0))
        with self.assertRaises(UserError):
            confirmed.with_user(self.manager).action_restore_wizard()
        cancelled = self.reservation(start=self.dt(self.day, 17, 0))
        cancelled.action_cancel()
        with self.assertRaises(UserError):
            cancelled.with_user(self.reception).action_restore_wizard()
        with self.assertRaises(AccessError):
            self.env["elite.vet.reservation.restore.wizard"].with_user(self.reception).create(
                {"reservation_id": cancelled.id})
