import pytz

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from ..models.reservation import TZ


class DruhaOrdinaceWizard(models.TransientModel):
    """Zduplikuje rezervaci do druhé ordinace pro zákrok, který potřebuje dvě lékařky."""

    _name = "elite.vet.reservation.druha.wizard"
    _description = "Přidat druhou ordinaci"

    reservation_id = fields.Many2one("elite.vet.reservation", required=True, readonly=True, ondelete="cascade")
    puvodni_room_id = fields.Many2one(related="reservation_id.room_id", string="Původní ordinace")
    puvodni_doctor_id = fields.Many2one(related="reservation_id.doctor_id", string="Původní lékařka")
    start = fields.Datetime(related="reservation_id.start", string="Začátek")
    stop = fields.Datetime(related="reservation_id.stop", string="Konec")
    room_id = fields.Many2one("elite.vet.room", string="Druhá ordinace", required=True,
                              domain="[('id', '!=', puvodni_room_id)]")
    lekarky_ve_sluzbe_ids = fields.Many2many("elite.vet.doctor", compute="_compute_lekarky_ve_sluzbe",
                                             string="Ve službě")
    doctor_id = fields.Many2one("elite.vet.doctor", string="Druhá lékařka",
                                domain="[('prijima_rezervace', '=', True), ('id', '!=', puvodni_doctor_id)]",
                                help="Předvyplní se lékařka, která má v druhé ordinaci v tu dobu službu.")

    @api.depends("room_id", "reservation_id")
    def _compute_lekarky_ve_sluzbe(self):
        for w in self:
            w.lekarky_ve_sluzbe_ids = w._lekarky_ve_sluzbe()

    def _lekarky_ve_sluzbe(self):
        """Lékařky se službou v druhé ordinaci po celou dobu zákroku (kromě té původní)."""
        Doctor = self.env["elite.vet.doctor"]
        r = self.reservation_id
        if not (self.room_id and r):
            return Doctor
        A = self.env["elite.vet.availability"]
        day = pytz.utc.localize(r.start).astimezone(TZ).date()
        od, do = A.utc_to_local_minutes(r.start, day), A.utc_to_local_minutes(r.stop, day)
        out = Doctor
        for a in self.env["elite.vet.doctor.assignment"].search(
                [("date", "=", day), ("room_id", "=", self.room_id.id),
                 ("doctor_id.prijima_rezervace", "=", True)], order="hour_from, id"):
            if a.hour_from * 60 <= od and do <= a.hour_to * 60 and a.doctor_id != r.doctor_id:
                out |= a.doctor_id
        return out

    @api.onchange("room_id")
    def _onchange_room(self):
        ve_sluzbe = self._lekarky_ve_sluzbe()
        if ve_sluzbe and self.doctor_id not in ve_sluzbe:
            self.doctor_id = ve_sluzbe[:1]

    def action_pridat(self):
        self.ensure_one()
        if not self.room_id:
            raise UserError(_("Vyberte druhou ordinaci."))
        self.reservation_id.pridat_druhou_ordinaci(self.room_id, self.doctor_id)
        return {
            "type": "ir.actions.client", "tag": "display_notification",
            "params": {"type": "success",
                       "message": _("Rezervace je teď i v ordinaci %s.") % self.room_id.name,
                       "next": {"type": "ir.actions.act_window_close"}},
        }
