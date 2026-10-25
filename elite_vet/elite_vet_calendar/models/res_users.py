from odoo import api, fields, models


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
