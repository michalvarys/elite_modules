from odoo import fields, models


class VetExpense(models.Model):
    _inherit = "elite.vet.expense"

    picking_id = fields.Many2one("stock.picking", string="Příjemka", index=True, readonly=True,
                                 ondelete="set null", copy=False,
                                 help="Příjem zboží, ze kterého výdaj vznikl.")
