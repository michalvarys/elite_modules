from odoo import api, fields, models
from odoo.exceptions import UserError


class MailSequenceStep(models.Model):
    _inherit = "elite.arena.mail.sequence.step"

    step_type = fields.Selection(selection_add=[("survey", "E-mail s dotazníkem")],
                                 ondelete={"survey": "set default"})
    survey_id = fields.Many2one("survey.survey", string="Dotazník",
                                help="E-mail obsahuje osobní odkaz na dotazník. Odměnu za vyplnění nastavíte u dotazníku.")

    def _check_ready(self):
        super()._check_ready()
        if self.step_type == "survey":
            if not self.survey_id:
                raise UserError("Krok „%s“ nemá vybraný dotazník." % self.name)
            if self.survey_id.arena_reward_id:
                self.survey_id.arena_reward_id._resolve_product()


class MailSequenceEnrollment(models.Model):
    _inherit = "elite.arena.mail.sequence.enrollment"

    def _mail_vals(self, step, now):
        vals = super()._mail_vals(step, now)
        if step.step_type == "survey" and step.survey_id:
            answer = step.survey_id.sudo()._create_answer(partner=self.partner_id, check_attempts=False)
            vals["survey_answer_id"] = answer.id
        return vals


class MailSequenceMail(models.Model):
    _inherit = "elite.arena.mail.sequence.mail"

    survey_answer_id = fields.Many2one("survey.user_input", string="Odpověď v dotazníku", readonly=True,
                                       ondelete="set null")
    survey_state = fields.Selection(related="survey_answer_id.state", string="Dotazník – stav")
    survey_url = fields.Char(compute="_compute_survey_texts")
    survey_reward_name = fields.Char(compute="_compute_survey_texts")

    @api.depends("survey_answer_id", "step_id.survey_id.arena_reward_id")
    def _compute_survey_texts(self):
        for rec in self:
            answer = rec.survey_answer_id
            rec.survey_url = (answer.survey_id.get_base_url() + answer.get_start_url()) if answer else False
            rec.survey_reward_name = rec.step_id.survey_id.arena_reward_id.name or ""

    def _send(self, email_to=None):
        for rec in self.filtered(lambda m: m.is_test and m.step_id.step_type == "survey" and not m.survey_answer_id):
            rec.survey_answer_id = rec.step_id.survey_id.sudo()._create_answer(
                partner=rec.partner_id, check_attempts=False, test_entry=True)
        return super()._send(email_to=email_to)
