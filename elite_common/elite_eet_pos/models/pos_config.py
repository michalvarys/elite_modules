from odoo import api, fields, models


class PosConfig(models.Model):
    _inherit = "pos.config"

    eet_device_ids = fields.One2many("elite.eet.device", "pos_config_id", "Nastavení EET")
    eet_device_id = fields.Many2one("elite.eet.device", "Nastavení EET", compute="_compute_eet_device_id")

    @api.depends("eet_device_ids")
    def _compute_eet_device_id(self):
        for config in self:
            config.eet_device_id = config.eet_device_ids[:1]
