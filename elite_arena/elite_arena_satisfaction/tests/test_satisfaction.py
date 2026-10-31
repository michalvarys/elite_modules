from datetime import datetime, timedelta

from odoo.tests import HttpCase, tagged

from odoo.addons.elite_arena_reward.tests.common import free_hour_product

NOW = datetime(2026, 11, 2, 11, 0, 0)


@tagged("post_install", "-at_install")
class TestSatisfaction(HttpCase):

    def setUp(self):
        super().setUp()
        self.env["elite.arena.ggleap.player"].search([]).write({"deleted": True})
        self.env.ref("elite_arena_reward.reward_free_hour").product_id = free_hour_product(self.env)
        self.survey = self.env.ref("elite_arena_satisfaction.survey_satisfaction")
        self.sequence = self.env.ref("elite_arena_satisfaction.sequence_satisfaction")
        self.partner = self.env["res.partner"].create({"name": "Ema Nová", "email": "ema@example.com"})
        self.env["elite.arena.ggleap.player"].create({
            "uuid": "sat-ema", "partner_id": self.partner.id, "visit_count": 1,
            "first_visit": NOW - timedelta(days=3), "last_visit": NOW - timedelta(days=3)})

    def test_survey_mail_and_reward(self):
        self.assertEqual(self.sequence.state, "draft")
        self.sequence.include_existing = True
        self.sequence.action_start()
        self.assertEqual(self.env["elite.arena.mail.sequence"]._cron_run(now=NOW), 1)
        mail = self.sequence.enrollment_ids.mail_ids
        answer = mail.survey_answer_id
        self.assertEqual((answer.survey_id, answer.partner_id), (self.survey, self.partner))
        self.assertFalse(mail.claim_id, "the reward comes only after the survey")
        self.assertIn(answer.access_token, mail.mail_id.body_html)
        self.assertEqual(mail.mail_id.email_from, "Elite Arena <no-reply@elite-arena.cz>")
        self.assertIn("Hodina hraní zdarma", mail.mail_id.body_html)

        page = self.url_open(answer.get_start_url())
        self.assertEqual(page.status_code, 200)

        answer._mark_done()
        claim = answer.arena_claim_id
        self.assertEqual((claim.partner_id, claim.state), (self.partner, "offered"))
        self.assertIn("Dotazník", claim.origin)
        done_html = self.env["ir.qweb"]._render("survey.survey_fill_form_done",
                                                 {"survey": self.survey, "answer": answer})
        self.assertIn("Pro vyzvednutí odměny klikni zde", str(done_html))
        self.assertIn("/odmena/%s" % claim.token, str(done_html))
        answer._mark_done()
        self.assertEqual(answer.arena_claim_id, claim, "one reward per answer")

    def test_no_reward_for_tests_and_strangers(self):
        test_answer = self.survey._create_answer(partner=self.partner, check_attempts=False, test_entry=True)
        test_answer._mark_done()
        self.assertFalse(test_answer.arena_claim_id)
        stranger = self.env["res.partner"].create({"name": "Bez účtu", "email": "x@example.com"})
        answer = self.survey._create_answer(partner=stranger, check_attempts=False)
        answer._mark_done()
        self.assertFalse(answer.arena_claim_id, "no ggLeap account, nothing to add the pass to")

    def test_test_mail_has_a_test_survey_link(self):
        self.env.user.email = "obsluha@example.com"
        self.env.ref("elite_arena_satisfaction.sequence_satisfaction_step").action_send_test()
        mail = self.env["elite.arena.mail.sequence.mail"].search([("is_test", "=", True)])
        self.assertTrue(mail.survey_answer_id.test_entry)
        self.assertIn(mail.survey_answer_id.access_token, mail.mail_id.body_html)
