from odoo import models

from odoo.addons.elite_vet_reservation.models.live import notify_board


class PosOrder(models.Model):
    _inherit = "pos.order"

    def action_pos_order_paid(self):
        res = super().action_pos_order_paid()
        # payment_state of a clinical record follows the POS order of its quotation:
        # refresh the board and the patient card.
        if self.lines.sale_order_origin_id.clinical_record_id:
            notify_board(self.env)
        return res
