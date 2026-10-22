from odoo import fields, models


class SaleOrder(models.Model):
    _inherit = "sale.order"

    clinical_record_id = fields.Many2one("elite.vet.clinical.record", string="Záznam návštěvy", readonly=True,
                                         copy=False, index="btree_not_null", ondelete="set null",
                                         help="Nabídka vznikla z uzavřeného záznamu návštěvy (k pokladně).")
    pet_id = fields.Many2one(related="clinical_record_id.pet_id", string="Pacient", store=True, index="btree_not_null")
    doctor_id = fields.Many2one(related="clinical_record_id.doctor_id", string="Lékařka", store=True)
    reservation_id = fields.Many2one(related="clinical_record_id.reservation_id", string="Rezervace", store=True)
