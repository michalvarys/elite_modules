from odoo import _, fields, models
from odoo.exceptions import UserError


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    # pos_* fields are written to the selected till by point_of_sale (see pos.config.write).
    pos_eet_enabled = fields.Boolean(related="pos_config_id.eet_enabled", readonly=False)
    pos_eet_eic = fields.Char(related="pos_config_id.eet_eic", readonly=False)
    pos_eet_id_jednotky = fields.Char(related="pos_config_id.eet_id_jednotky", readonly=False)
    pos_eet_start_datetime = fields.Datetime(related="pos_config_id.eet_start_datetime", readonly=False)
    pos_eet_environment = fields.Selection(related="pos_config_id.eet_environment")
    pos_eet_cert_valid_to = fields.Datetime(related="pos_config_id.eet_cert_valid_to")
    pos_eet_status = fields.Char(related="pos_config_id.eet_status")
    pos_eet_status_level = fields.Selection(related="pos_config_id.eet_status_level")
    pos_eet_certificate_file = fields.Binary(
        related="pos_config_id.eet_certificate_file", readonly=False, groups="base.group_system"
    )
    pos_eet_certificate_filename = fields.Char(
        related="pos_config_id.eet_certificate_filename", readonly=False, groups="base.group_system"
    )
    pos_eet_certificate_password = fields.Char(
        related="pos_config_id.eet_certificate_password", readonly=False, groups="base.group_system"
    )
    pos_eet_cert_source_config_id = fields.Many2one(
        related="pos_config_id.eet_cert_source_config_id", readonly=False, groups="base.group_system"
    )

    def action_pos_eet_check_connection(self):
        """Saved by the form before this runs; send a verification message for the selected till."""
        self.ensure_one()
        device = self.pos_config_id.eet_device_id
        if not device:
            raise UserError(_("Nejdřív vyplňte číslo evidenční jednotky, nahrajte certifikát a uložte."))
        action = device.action_check_connection()
        action["params"]["next"] = {"type": "ir.actions.client", "tag": "soft_reload"}
        return action
