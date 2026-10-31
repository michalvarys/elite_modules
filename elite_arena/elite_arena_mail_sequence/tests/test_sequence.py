from datetime import datetime, timedelta
from unittest.mock import patch

from odoo.tests import HttpCase, tagged

from odoo.addons.elite_arena_ggleap.models.sync import GgleapSync
from odoo.addons.elite_arena_reward.tests.common import FakeGrant, free_hour_product

NOW = datetime(2026, 11, 2, 11, 0, 0)    # 12:00 in Prague


@tagged("post_install", "-at_install")
class TestMailSequence(HttpCase):

    def setUp(self):
        super().setUp()
        # only the players of this test count (the database may hold real synced data)
        self.env["elite.arena.ggleap.player"].search([]).write({"deleted": True})
        self.product = free_hour_product(self.env)
        self.env.ref("elite_arena_reward.reward_free_hour").product_id = self.product
        self.lost = self.env.ref("elite_arena_mail_sequence.sequence_lost")
        self.new = self.env.ref("elite_arena_mail_sequence.sequence_new")
        self.Mail = self.env["elite.arena.mail.sequence.mail"]

    def player(self, name, last_days, visits, first_days=None):
        partner = self.env["res.partner"].create({"name": name, "email": "%s@example.com" % name.split()[0].lower()})
        self.env["elite.arena.ggleap.player"].create({
            "uuid": "seq-%s" % partner.id, "partner_id": partner.id, "visit_count": visits,
            "last_visit": NOW - timedelta(days=last_days),
            "first_visit": NOW - timedelta(days=first_days if first_days is not None else last_days)})
        return partner

    def run_cron(self, now=NOW):
        return self.env["elite.arena.mail.sequence"]._cron_run(now=now)

    def test_installed_switched_off(self):
        self.assertEqual(self.lost.state, "draft")
        self.assertEqual(self.new.state, "draft")
        self.player("Karel Lost", 50, 3)
        self.assertEqual(self.run_cron(), 0)
        self.assertFalse(self.env["elite.arena.mail.sequence.enrollment"].search([]))

    def test_lost_series(self):
        karel = self.player("Karel Lost", 50, 3)
        self.player("Jana Active", 20, 5)
        self.player("Petr Gone", 200, 4)
        self.lost.include_existing = True
        self.lost.action_start()
        self.assertEqual(self.run_cron(), 1)
        enrollment = self.lost.enrollment_ids
        self.assertEqual(enrollment.partner_id, karel)
        mail = enrollment.mail_ids
        self.assertEqual(mail.step_id, self.env.ref("elite_arena_mail_sequence.sequence_lost_step_offer"))
        claim = mail.claim_id
        self.assertEqual((claim.partner_id, claim.state), (karel, "offered"))
        body = mail.mail_id.body_html
        self.assertIn("Ahoj Karel", body)
        self.assertIn("/odmena/%s" % claim.token, body)
        self.assertIn("/arena/odhlasit/%s" % mail.token, body)
        self.assertEqual(mail.mail_id.recipient_ids, karel)
        self.assertEqual(mail.mail_id.email_from, "Elite Arena <no-reply@elite-arena.cz>")
        self.assertIn("List-Unsubscribe", mail.mail_id.headers)

        # nothing more until day 10, then the reminder with the same link
        self.assertEqual(self.run_cron(NOW + timedelta(days=5)), 0)
        self.assertEqual(self.run_cron(NOW + timedelta(days=10)), 1)
        reminder = enrollment.mail_ids.filtered(lambda m: m.step_id.skip_if_claimed)
        self.assertEqual(reminder.claim_id, claim)
        self.assertIn(claim.token, reminder.mail_id.body_html)
        self.assertEqual(enrollment.state, "done")
        self.assertEqual(len(self.lost.enrollment_ids), 1, "joins once")

    def test_only_new_ones_after_start(self):
        self.player("Karel Long", 50, 3)        # crossed 45 days five days ago
        self.player("Jana Earlier", 100, 3)     # was lost long before the start
        self.lost.action_start()
        self.assertEqual(self.run_cron(), 0, "started just now: nobody crossed the line since")
        self.lost.activated_at = NOW - timedelta(days=10)
        self.run_cron()
        self.assertEqual(self.lost.enrollment_ids.partner_id.mapped("name"), ["Karel Long"])

    def test_reminder_skipped_when_claimed_and_stop_when_back(self):
        karel = self.player("Karel Lost", 50, 3)
        jana = self.player("Jana Lost", 60, 2)
        self.lost.include_existing = True
        self.lost.action_start()
        self.run_cron()
        with patch.object(GgleapSync, "grant_gamepass", FakeGrant()):
            self.lost.enrollment_ids.filtered(lambda e: e.partner_id == karel).mail_ids.claim_id.claim()
        # Jana came back
        jana.ggleap_player_ids.write({"last_visit": NOW + timedelta(days=2), "visit_count": 3})
        self.run_cron(NOW + timedelta(days=10))
        by_partner = {e.partner_id: e for e in self.lost.enrollment_ids}
        self.assertEqual(by_partner[karel].mail_ids.sorted("id").mapped("state"), ["sent", "skipped"])
        self.assertTrue(by_partner[karel].claimed)
        self.assertEqual(by_partner[jana].state, "returned")
        self.assertEqual(len(by_partner[jana].mail_ids), 1)
        self.assertIn("1 vrátilo", self.lost.result)

    def test_new_players_gap_and_quiet_hours(self):
        petr = self.player("Petr New", 8, 1, first_days=8)
        self.player("Ola Old", 8, 4, first_days=90)
        self.new.include_existing = True
        self.new.action_start()
        night = NOW - timedelta(hours=14)      # 22:00 in Prague the evening before
        self.assertEqual(self.run_cron(night), 0, "no e-mails at night")
        self.assertEqual(self.new.enrollment_ids.partner_id, petr, "joined anyway")
        self.assertEqual(self.run_cron(), 1)
        # another series the same day has to wait for the gap
        other = self.new.copy({"name": "Jiná série"})
        other.include_existing = True
        other.action_start()
        self.assertEqual(self.run_cron(NOW + timedelta(hours=1)), 0)
        self.assertEqual(other.enrollment_ids.next_at, self.new.enrollment_ids.mail_ids.sent_at + timedelta(days=3))

    def test_unsubscribe_and_test_mail(self):
        karel = self.player("Karel Lost", 50, 3)
        self.lost.include_existing = True
        self.lost.action_start()
        self.run_cron()
        mail = self.lost.enrollment_ids.mail_ids
        page = self.url_open("/arena/odhlasit/%s" % mail.token)
        self.assertEqual(page.status_code, 200)
        self.assertFalse(karel.is_blacklisted, "opening the link does not unsubscribe")
        csrf = page.text.split('name="csrf_token" value="')[1].split('"')[0]
        done = self.url_open("/arena/odhlasit/%s" % mail.token, data={"csrf_token": csrf})
        self.assertIn("už ti nebudeme posílat", done.text)
        karel.invalidate_recordset()
        self.assertTrue(karel.is_blacklisted)
        self.assertEqual(self.lost.enrollment_ids.state, "unsubscribed")

        self.env.user.email = "obsluha@example.com"
        step = self.env.ref("elite_arena_mail_sequence.sequence_lost_step_offer")
        step.action_send_test()
        test_mail = self.Mail.search([("is_test", "=", True)])
        self.assertEqual(test_mail.mail_id.email_to, "obsluha@example.com")
        self.assertFalse(test_mail.mail_id.recipient_ids)
        self.assertTrue(test_mail.claim_id.is_test)
