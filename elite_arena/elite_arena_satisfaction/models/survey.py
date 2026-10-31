from odoo import fields, models


class SurveySurvey(models.Model):
    _inherit = "survey.survey"

    arena_reward_id = fields.Many2one(
        "elite.arena.reward", string="Odměna za vyplnění",
        help="Kdo dotazník dokončí, uvidí na konci odkaz na tuto odměnu (jen hráči s účtem v ggLeapu).")


class SurveyUserInput(models.Model):
    _inherit = "survey.user_input"

    arena_claim_id = fields.Many2one("elite.arena.reward.claim", string="Odměna", readonly=True, copy=False)

    def _mark_done(self):
        res = super()._mark_done()
        for answer in self.sudo():
            reward = answer.survey_id.arena_reward_id
            partner = answer.partner_id
            if (not reward or answer.arena_claim_id or answer.test_entry or not partner
                    or not partner.ggleap_player_ids.filtered(lambda p: not p.deleted)):
                continue
            answer.arena_claim_id = reward.create_claim(partner, "Dotazník: %s" % answer.survey_id.title)
        return res
