from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

from .room import format_hour


class VetDoctorAssignment(models.Model):
    """Who works where and when. Deliberately separate from the shift roster
    (elite.vet.shift): that one is for the website and only knows the shift type;
    here we need the room and the exact time.
    """

    _name = "elite.vet.doctor.assignment"
    _description = "Služba lékaře v ordinaci"
    _order = "date, room_id, hour_from"

    doctor_id = fields.Many2one("elite.vet.doctor", string="Lékařka", required=True, ondelete="restrict",
                                domain=[("accepts_bookings", "=", True)])
    room_id = fields.Many2one("elite.vet.room", string="Ordinace", required=True, ondelete="restrict")
    date = fields.Date(string="Datum", required=True, default=fields.Date.context_today)
    # Summing hours in a group (e.g. "From 32:00" per day) makes no sense.
    hour_from = fields.Float(string="Od", required=True, default=8.0, aggregator=None)
    hour_to = fields.Float(string="Do", required=True, default=14.0, aggregator=None)
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

    @api.constrains("doctor_id")
    def _check_doctor_accepts_bookings(self):
        for rec in self:
            if not rec.doctor_id.accepts_bookings:
                raise ValidationError(_(
                    "%s nemá zaškrtnuto „Lékařka – přijímá rezervace“. Do rozpisu lékařů "
                    "patří jen lékařky; nastavuje se v Rozpis služeb → Lékařky."
                ) % rec.doctor_id.name)

    def serves(self, procedure):
        """May the doctor perform the procedure in this assignment? She must be able
        to (specialization) and the assignment must not exclude it via "Only these procedures"."""
        self.ensure_one()
        if self.doctor_id not in procedure.doctors_for_booking():
            return False
        return not self.procedure_ids or procedure in self.procedure_ids

    def action_copy_week(self):
        """Copy the selected assignments one week ahead. A copy that would overlap
        another assignment of the same doctor is skipped (instead of failing the whole
        copy). The same goes for a doctor who no longer accepts bookings."""
        copied, skipped = 0, 0
        for rec in self.sorted(lambda r: (r.date, r.hour_from)):
            if not rec.doctor_id.accepts_bookings:
                skipped += 1
                continue
            new_date = rec.date + timedelta(days=7)
            clash = self.search_count([
                ("doctor_id", "=", rec.doctor_id.id), ("date", "=", new_date),
                ("hour_from", "<", rec.hour_to), ("hour_to", ">", rec.hour_from),
            ])
            if clash:
                skipped += 1
                continue
            rec.copy({"date": new_date})
            copied += 1
        return {
            "type": "ir.actions.client", "tag": "display_notification",
            "params": {
                "title": _("Kopírování na další týden"),
                "message": _("Zkopírováno %(ok)s, přeskočeno %(skip)s.", ok=copied, skip=skipped),
                "type": "success" if not skipped else "warning",
                "next": {"type": "ir.actions.client", "tag": "soft_reload"},
            },
        }
