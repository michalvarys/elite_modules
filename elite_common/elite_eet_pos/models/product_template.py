from odoo import fields, models


class ProductTemplate(models.Model):
    _inherit = "product.template"

    eet_prepaid_voucher = fields.Boolean(
        "Předplacený kredit/voucher na neurčené zboží",
        help="Prodej tohoto produktu se v EET uvádí i jako částka určená k pozdějšímu čerpání "
             "(urceno_cerp_zuct). Nezaškrtávejte u dárkového poukazu na konkrétní zboží nebo službu.",
    )
