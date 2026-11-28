from odoo import fields, models


class PosConfig(models.Model):
    _inherit = "pos.config"

    payment_buttons_spread = fields.Boolean(
        "Rozložit tlačítka plateb",
        default=False,
        help="Zapnuto: tlačítka plateb se rozloží s mezerami po celé výšce panelu. "
             "Vypnuto: tlačítka jsou seřazená za sebou od shora (jako v Odoo). "
             "Platí pro tablet a počítač, na mobilu jsou tlačítka vždy ve dvou sloupcích.",
    )


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    pos_payment_buttons_spread = fields.Boolean(related="pos_config_id.payment_buttons_spread", readonly=False)
