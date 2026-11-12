from odoo import fields, models


class ConfirmWizard(models.TransientModel):
    """Request 11. 11. (Lucie): confirm a web request over a taken time after a yes.
    Only Recepce and up may (_check_overlap); never over a block."""

    _name = "elite.vet.reservation.confirm.wizard"
    _description = "Potvrdit do obsazeného termínu"

    reservation_id = fields.Many2one("elite.vet.reservation", required=True, readonly=True, ondelete="cascade")
    overlap_warning = fields.Char(string="Upozornění na obsazený termín", readonly=True)

    def action_confirm(self):
        self.ensure_one()
        self.reservation_id.with_context(ev_allow_overlap=True).action_confirm()
        return {"type": "ir.actions.act_window_close"}
