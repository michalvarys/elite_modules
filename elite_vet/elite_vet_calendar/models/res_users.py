from odoo import api, fields, models
from odoo.http import request
from odoo.tools import frozendict


class ResUsers(models.Model):
    """Reverse of elite.vet.doctor.user_id (task 23): the team member of the account."""

    _inherit = "res.users"

    elite_vet_doctor_ids = fields.One2many("elite.vet.doctor", "user_id", string="Členové týmu")
    elite_vet_doctor_id = fields.Many2one(
        "elite.vet.doctor", string="Člen týmu", compute="_compute_elite_vet_doctor_id", compute_sudo=True,
        help="Člen týmu z Rozpisu služeb › Lékařky, ke kterému tento účet patří. Mění se tam ve sloupci Účet.")

    @api.depends("elite_vet_doctor_ids")
    def _compute_elite_vet_doctor_id(self):
        for user in self:
            user.elite_vet_doctor_id = user.elite_vet_doctor_ids[:1]

    @api.model
    def context_get(self):
        """Accounts on English (US) get the interface of English (UK).

        The source of our code terms is Czech and Odoo never translates to en_US, so the
        interface would stay Czech. The account keeps en_US, en_GB only applies to the session.
        Odoo also calls this for texts written without a language, so crons and other work
        outside a request must keep the source language.
        """
        context = super().context_get()
        if (request and context.get("lang") == "en_US" and self.env.user._is_internal()
                and self.env["res.lang"]._lang_get("en_GB")):
            return frozendict(context, lang="en_GB")
        return context
