from odoo import fields, models


class PosConfig(models.Model):
    _inherit = "pos.config"

    is_elite_vet_reception = fields.Boolean(
        string="Pokladna recepce", compute="_compute_is_elite_vet_reception",
        help="Pokladna „Recepce“: v pokladně jsou záložky Dnes, Objednat, Kartotéka a Tabule "
             "a po přihlášení se otevře záložka Dnes.")

    def _compute_is_elite_vet_reception(self):
        reception = self.env.ref("elite_vet_sale.pos_config_reception", raise_if_not_found=False)
        for config in self:
            config.is_elite_vet_reception = bool(reception) and config == reception
