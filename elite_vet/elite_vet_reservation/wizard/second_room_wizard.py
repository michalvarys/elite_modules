import pytz

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from ..models.reservation import TZ


class SecondRoomWizard(models.TransientModel):
    """Duplicate a reservation into a second room for a procedure that needs two doctors."""

    _name = "elite.vet.reservation.second.room.wizard"
    _description = "Přidat druhou ordinaci"

    reservation_id = fields.Many2one("elite.vet.reservation", required=True, readonly=True, ondelete="cascade")
    original_room_id = fields.Many2one(related="reservation_id.room_id", string="Původní ordinace")
    original_doctor_id = fields.Many2one(related="reservation_id.doctor_id", string="Původní lékařka")
    start = fields.Datetime(related="reservation_id.start", string="Začátek")
    stop = fields.Datetime(related="reservation_id.stop", string="Konec")
    room_id = fields.Many2one("elite.vet.room", string="Druhá ordinace", required=True,
                              domain="[('id', '!=', original_room_id)]")
    serving_doctor_ids = fields.Many2many("elite.vet.doctor", compute="_compute_serving_doctors",
                                             string="Ve službě")
    doctor_id = fields.Many2one("elite.vet.doctor", string="Druhá lékařka",
                                domain="[('accepts_bookings', '=', True), ('id', '!=', original_doctor_id)]",
                                help="Předvyplní se lékařka, která má v druhé ordinaci v tu dobu službu.")

    @api.depends("room_id", "reservation_id")
    def _compute_serving_doctors(self):
        for w in self:
            w.serving_doctor_ids = w._serving_doctors()

    def _serving_doctors(self):
        """Doctors on duty in the second room for the whole procedure (except the original one)."""
        Doctor = self.env["elite.vet.doctor"]
        r = self.reservation_id
        if not (self.room_id and r):
            return Doctor
        A = self.env["elite.vet.availability"]
        day = pytz.utc.localize(r.start).astimezone(TZ).date()
        start_min, stop_min = A.utc_to_local_minutes(r.start, day), A.utc_to_local_minutes(r.stop, day)
        out = Doctor
        for a in self.env["elite.vet.doctor.assignment"].search(
                [("date", "=", day), ("room_id", "=", self.room_id.id),
                 ("doctor_id.accepts_bookings", "=", True)], order="hour_from, id"):
            if a.hour_from * 60 <= start_min and stop_min <= a.hour_to * 60 and a.doctor_id != r.doctor_id:
                out |= a.doctor_id
        return out

    @api.onchange("room_id")
    def _onchange_room(self):
        serving = self._serving_doctors()
        if serving and self.doctor_id not in serving:
            self.doctor_id = serving[:1]

    def action_add(self):
        self.ensure_one()
        if not self.room_id:
            raise UserError(_("Vyberte druhou ordinaci."))
        self.reservation_id.add_second_room(self.room_id, self.doctor_id)
        return {
            "type": "ir.actions.client", "tag": "display_notification",
            "params": {"type": "success",
                       "message": _("Rezervace je teď i v ordinaci %s.") % self.room_id.name,
                       "next": {"type": "ir.actions.act_window_close"}},
        }
