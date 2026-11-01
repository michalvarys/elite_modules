"""Read-only mode for production while the clinic still works in WinVet.

Ordinace, the cards (clients, pets, visit records, alerts) and Pokladna may only be read by
everyone but Správce rezervací; the data comes from WinVet. Switched in Nastavení → Elite Vet.
Not affected: the WinVet sync and other code running as superuser / sudo, and new reservations,
which still create their client and pet (only existing cards cannot be changed).
"""
from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.tools import str2bool

PARAM = "elite_vet_clinic.readonly_mode"
MANAGER_GROUP = "elite_vet_reservation.group_reservation_manager"


def clinic_readonly(env):
    """May the current user only read Ordinace, the cards and Pokladna?"""
    if env.su or not str2bool(env["ir.config_parameter"].sudo().get_param(PARAM) or "0"):
        return False
    return not env.user.has_group(MANAGER_GROUP)


def check_clinic_writable(env):
    if clinic_readonly(env):
        raise UserError(env._("Ordinace, karty a pokladna jsou zatím jen pro čtení – pracuje se ve WinVetu, "
                              "odkud se data přenášejí. Změny může dělat jen správce rezervací."))


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    elite_vet_readonly_mode = fields.Boolean(
        string="Ordinace, karty a pokladna jen pro čtení", config_parameter=PARAM,
        help="Na produkci, dokud se pracuje ve WinVetu: lékařky, sestry a recepce data jen čtou. "
             "Měnit je může jen správce rezervací; přenos z WinVetu a nové rezervace běží dál.")


class VetPet(models.Model):
    _inherit = "elite.vet.pet"

    # create stays open: a new reservation creates its pet
    def write(self, vals):
        check_clinic_writable(self.env)
        return super().write(vals)

    def unlink(self):
        check_clinic_writable(self.env)
        return super().unlink()


class ResPartner(models.Model):
    _inherit = "res.partner"

    def _elite_vet_check_card_writable(self):
        # clients of the clinic only; staff keep editing their own contact (user preferences)
        if clinic_readonly(self.env) and self.filtered(lambda p: p.is_vet_client and not p.user_ids):
            check_clinic_writable(self.env)

    def write(self, vals):
        self._elite_vet_check_card_writable()
        return super().write(vals)

    def unlink(self):
        self._elite_vet_check_card_writable()
        return super().unlink()


class VetPetAlert(models.Model):
    _inherit = "elite.vet.pet.alert"

    @api.model_create_multi
    def create(self, vals_list):
        check_clinic_writable(self.env)
        return super().create(vals_list)

    def write(self, vals):
        check_clinic_writable(self.env)
        return super().write(vals)

    def unlink(self):
        check_clinic_writable(self.env)
        return super().unlink()


class VetClinicalRecord(models.Model):
    _inherit = "elite.vet.clinical.record"

    @api.model_create_multi
    def create(self, vals_list):
        check_clinic_writable(self.env)
        return super().create(vals_list)

    def write(self, vals):
        check_clinic_writable(self.env)
        return super().write(vals)

    def unlink(self):
        check_clinic_writable(self.env)
        return super().unlink()


class VetClinicalRecordLine(models.Model):
    _inherit = "elite.vet.clinical.record.line"

    @api.model_create_multi
    def create(self, vals_list):
        check_clinic_writable(self.env)
        return super().create(vals_list)

    def write(self, vals):
        check_clinic_writable(self.env)
        return super().write(vals)

    def unlink(self):
        check_clinic_writable(self.env)
        return super().unlink()
