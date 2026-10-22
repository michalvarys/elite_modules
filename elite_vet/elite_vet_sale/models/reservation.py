from odoo import api, models


class ReservationPayment(models.Model):
    _inherit = "elite.vet.reservation"

    @api.model
    def board_data(self, day_str):
        """Adds the payment state of the visit record to every reservation event (False without a
        record). One search of the records for the whole day, not one per event."""
        data = super().board_data(day_str)
        ids = [e["id"] for e in data["events"]]
        records = self.env["elite.vet.clinical.record"].search([("reservation_id", "in", ids)]) if ids else []
        state_by_reservation = {r.reservation_id.id: r.payment_state for r in records}
        for event in data["events"]:
            event["payment_state"] = state_by_reservation.get(event["id"], False)
        return data
