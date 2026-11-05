from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

from odoo.addons.elite_vet_reservation.models.room import format_hour

SLOT_DAYS = [("weekdays", "Mon–Fri"), ("weekend", "Sat–Sun"), ("all", "Every day")]


class PlanningRow(models.Model):
    """A block of the monthly plan (Recepce, Ordinace 1, Sál, Stáž / výpomoc) with its slots.

    A doctor's shift in a row with a room gets that room, so Rezervace (elite_vet_reservation)
    turns it into her service in the reservation calendar by itself."""

    _name = "elite.vet.planning.row"
    _description = "Planning section"
    _order = "sequence, id"

    name = fields.Char(string="Name", required=True)
    sequence = fields.Integer(string="Sequence", default=10)
    kind = fields.Selection([("room", "Section / room"), ("helpers", "Internship / helpers")], string="Kind",
                            required=True, default="room",
                            help="Internship / helpers: any name can be typed in; the shifts are not shown on the website.")
    room_id = fields.Many2one("elite.vet.room", string="Room in reservations", ondelete="set null",
                              help="A doctor's service in this section goes to the reservation calendar in this "
                                   "room. Empty (e.g. Recepce) = not written.")
    preferred_roles = fields.Char(string="Roles on top of the list", default="doctor,nurse",
                                  help="Comma separated roles (doctor, nurse, reception, helper) offered "
                                       "first when choosing a person.")
    slot_ids = fields.One2many("elite.vet.planning.slot", "row_id", string="Shifts")
    active = fields.Boolean(string="Active", default=True)


class PlanningSlot(models.Model):
    _name = "elite.vet.planning.slot"
    _description = "Section shift"
    _order = "row_id, sequence, id"

    row_id = fields.Many2one("elite.vet.planning.row", string="Section", required=True, ondelete="cascade")
    name = fields.Char(string="Name", required=True)
    sequence = fields.Integer(string="Sequence", default=10)
    type_id = fields.Many2one("elite.vet.shift.type", string="Shift type in the roster", required=True,
                              ondelete="restrict", domain=[("is_note", "=", False)],
                              help="Shift type used in the roster (color and legend on the website).")
    hour_from = fields.Float(string="From", required=True, default=8.0)
    hour_to = fields.Float(string="To", required=True, default=16.0)
    days = fields.Selection(SLOT_DAYS, string="Days", required=True, default="weekdays")
    time_display = fields.Char(string="Time", compute="_compute_time_display")

    @api.depends("hour_from", "hour_to")
    def _compute_time_display(self):
        for rec in self:
            rec.time_display = "%s–%s" % (format_hour(rec.hour_from), format_hour(rec.hour_to))

    @api.depends("row_id.name", "name")
    def _compute_display_name(self):
        for rec in self:
            rec.display_name = "%s · %s" % (rec.row_id.name or "", rec.name or "")

    @api.constrains("hour_from", "hour_to")
    def _check_hours(self):
        for rec in self:
            if not (0 <= rec.hour_from < 24 and 0 < rec.hour_to <= 24) or rec.hour_from == rec.hour_to:
                raise ValidationError(_("The shift times From and To must be between 0:00 and 24:00 and must differ."))

    def applies_to(self, day):
        """Is the slot offered on this date (weekday / weekend)?"""
        self.ensure_one()
        weekend = day.weekday() >= 5
        return self.days == "all" or (self.days == "weekend") == weekend
