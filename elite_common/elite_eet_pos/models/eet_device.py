from odoo import api, fields, models

from odoo.addons.elite_eet.eet import fields as eet_fields


class EliteEetDevice(models.Model):
    _inherit = "elite.eet.device"

    pos_config_id = fields.Many2one("pos.config", "Pokladna", ondelete="restrict", index=True, tracking=True)

    _sql_constraints = [
        ("pos_config_unique", "unique(pos_config_id)", "Pokladna smí mít jen jedno nastavení EET."),
    ]

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            config = self.env["pos.config"].browse(vals.get("pos_config_id"))
            if config:
                vals.setdefault("name", config.name)
                vals.setdefault("company_id", config.company_id.id)
                if not vals.get("id_pokl"):
                    vals["id_pokl"] = eet_fields.sanitize_text(config.name, 20)
        return super().create(vals_list)
