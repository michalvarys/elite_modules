"""Account of a team member (task 23): linking or unlinking an account in Rozpis služeb ›
Lékařky › Účet updates the home screen of the account (res_users.py: a linked Sestra /
Lékařka gets the screen Ordinace)."""
from odoo import api, models


class VetDoctorAccount(models.Model):
    _inherit = "elite.vet.doctor"

    @api.model_create_multi
    def create(self, vals_list):
        doctors = super().create(vals_list)
        doctors.user_id._elite_vet_apply_home_action()
        return doctors

    def write(self, vals):
        before = self.user_id if "user_id" in vals or "active" in vals else self.env["res.users"]
        res = super().write(vals)
        if "user_id" in vals or "active" in vals:
            (before | self.user_id)._elite_vet_apply_home_action()
        return res

    def unlink(self):
        users = self.user_id
        res = super().unlink()
        users._elite_vet_apply_home_action()
        return res
