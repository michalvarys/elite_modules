from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

from odoo.addons.elite_vet_reservation.models.room import format_hour

SLOT_DAYS = [("weekdays", "Po–Pá"), ("weekend", "So–Ne"), ("all", "Každý den")]


class PlanningRow(models.Model):
    """A block of the monthly plan (Recepce, Ordinace 1, Sál, Stáž / výpomoc) with its slots.

    A doctor's shift in a row with a room gets that room, so Rezervace (elite_vet_reservation)
    turns it into her service in the reservation calendar by itself."""

    _name = "elite.vet.planning.row"
    _description = "Úsek plánu služeb"
    _order = "sequence, id"

    name = fields.Char(string="Název", required=True)
    sequence = fields.Integer(string="Pořadí", default=10)
    kind = fields.Selection([("room", "Úsek / místnost"), ("helpers", "Stáž / výpomoc")], string="Druh",
                            required=True, default="room",
                            help="Stáž / výpomoc: jde vepsat i libovolné jméno; směny se nezobrazují na webu.")
    room_id = fields.Many2one("elite.vet.room", string="Ordinace v rezervacích", ondelete="set null",
                              help="Služba lékařky v tomto úseku se propíše do kalendáře rezervací v této "
                                   "ordinaci. Prázdné (např. Recepce) = nepropisuje se.")
    preferred_roles = fields.Char(string="Role nahoře v nabídce", default="doctor,nurse",
                                  help="Čárkou oddělené role (doctor, nurse, reception, helper), které se "
                                       "při výběru člověka nabízejí jako první.")
    slot_ids = fields.One2many("elite.vet.planning.slot", "row_id", string="Směny")
    active = fields.Boolean(string="Aktivní", default=True)


class PlanningSlot(models.Model):
    _name = "elite.vet.planning.slot"
    _description = "Směna úseku"
    _order = "row_id, sequence, id"

    row_id = fields.Many2one("elite.vet.planning.row", string="Úsek", required=True, ondelete="cascade")
    name = fields.Char(string="Název", required=True)
    sequence = fields.Integer(string="Pořadí", default=10)
    type_id = fields.Many2one("elite.vet.shift.type", string="Typ směny v rozpisu", required=True,
                              ondelete="restrict", domain=[("is_note", "=", False)],
                              help="Typ směny, pod kterým se zapíše do Rozpisu služeb (barva a legenda na webu).")
    hour_from = fields.Float(string="Od", required=True, default=8.0)
    hour_to = fields.Float(string="Do", required=True, default=16.0)
    days = fields.Selection(SLOT_DAYS, string="Dny", required=True, default="weekdays")
    time_display = fields.Char(string="Čas", compute="_compute_time_display")

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
                raise ValidationError(_("Čas směny „Od“ a „Do“ musí být mezi 0:00 a 24:00 a nesmí být stejný."))

    def applies_to(self, day):
        """Is the slot offered on this date (weekday / weekend)?"""
        self.ensure_one()
        weekend = day.weekday() >= 5
        return self.days == "all" or (self.days == "weekend") == weekend
