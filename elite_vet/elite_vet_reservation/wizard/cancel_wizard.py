from odoo import api, fields, models


class CancelWizard(models.TransientModel):
    """Request 1. 11.: "Zrušit" on the reservation form asks first and, when the client gets the
    cancellation e-mail, takes the clinic's message for it (like the board's cancel dialog)."""

    _name = "elite.vet.reservation.cancel.wizard"
    _description = "Zrušit rezervaci"

    reservation_id = fields.Many2one("elite.vet.reservation", required=True, readonly=True, ondelete="cascade")
    contact_email = fields.Char(related="reservation_id.contact_email")
    message = fields.Text(string="Zpráva klientovi",
                          help="Nepovinné – vloží se do e-mailu o zrušení, který klient dostane.")

    def action_cancel(self):
        self.ensure_one()
        self.reservation_id.action_cancel("clinic", self.message if self.contact_email else None)
        return {"type": "ir.actions.act_window_close"}
