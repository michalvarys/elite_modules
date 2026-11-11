from odoo import fields, models


class EliteEetSale(models.Model):
    _inherit = "elite.eet.sale"

    pos_order_id = fields.Many2one("pos.order", "Objednávka pokladny", ondelete="restrict", index=True, readonly=True)

    _sql_constraints = [
        ("pos_order_unique", "unique(pos_order_id)", "Objednávka pokladny smí mít jen jednu tržbu EET."),
    ]
