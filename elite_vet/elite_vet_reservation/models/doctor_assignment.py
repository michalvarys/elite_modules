from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

from .room import format_hour


class VetDoctorAssignment(models.Model):
    """Kdo kde kdy slouzi. Zamerne zvlast od rozpisu sluzeb (elite.vet.shift):
    ten je pro web a zna jen typ smeny, tady je potreba ordinace a presny cas.
    """

    _name = "elite.vet.doctor.assignment"
    _description = "Služba lékaře v ordinaci"
    _order = "date, room_id, hour_from"

    doctor_id = fields.Many2one("elite.vet.doctor", string="Lékařka", required=True, ondelete="restrict")
    room_id = fields.Many2one("elite.vet.room", string="Ordinace", required=True, ondelete="restrict")
    date = fields.Date(string="Datum", required=True, default=fields.Date.context_today)
    hour_from = fields.Float(string="Od", required=True, default=8.0)
    hour_to = fields.Float(string="Do", required=True, default=14.0)
    procedure_ids = fields.Many2many(
        "elite.vet.procedure", "elite_vet_assignment_procedure_rel", "assignment_id", "procedure_id",
        string="Jen tyto úkony", help="Prázdné = všechny úkony, které se v ordinaci dělají.")
    specialization_ids = fields.Many2many(related="doctor_id.specialization_ids", readonly=True)
    note = fields.Char(string="Poznámka")

    @api.depends("doctor_id", "room_id", "hour_from", "hour_to")
    def _compute_display_name(self):
        for rec in self:
            rec.display_name = "%s · %s · %s–%s" % (
                rec.doctor_id.name or "", rec.room_id.name or "",
                format_hour(rec.hour_from), format_hour(rec.hour_to))

    @api.constrains("doctor_id", "date", "hour_from", "hour_to")
    def _check_overlap(self):
        for rec in self:
            if rec.hour_from >= rec.hour_to:
                raise ValidationError(_("Čas „Od“ musí být dřív než „Do“."))
            clash = self.search([
                ("id", "!=", rec.id), ("doctor_id", "=", rec.doctor_id.id), ("date", "=", rec.date),
                ("hour_from", "<", rec.hour_to), ("hour_to", ">", rec.hour_from),
            ], limit=1)
            if clash:
                raise ValidationError(_("%s už v tu dobu slouží: %s.") % (rec.doctor_id.name, clash.display_name))

    def serves(self, procedure):
        self.ensure_one()
        return not self.procedure_ids or procedure in self.procedure_ids
