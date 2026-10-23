from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

from .room import format_hour

# Context key of the roster sync (elite.vet.shift → assignment); only it may change a linked assignment.
ROSTER_SYNC = "elite_vet_roster_sync"
# What the roster decides on a linked assignment; the rest (Only these procedures, Note) stays editable here.
ROSTER_FIELDS = ("shift_id", "doctor_id", "room_id", "date", "hour_from", "hour_to")


class VetDoctorAssignment(models.Model):
    """Who works where and when.

    Two kinds of rows: linked ones (`shift_id` set) are created and kept up to date by
    the shift roster (elite.vet.shift with a room, see models/shift.py) and may be changed
    only there; manual ones (no shift) are entered here as before - custom hours, half
    shifts. The link lives here (shift_id, unique), the shift sees it via assignment_ids.
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
    shift_id = fields.Many2one("elite.vet.shift", string="Směna v rozpisu služeb", readonly=True, copy=False,
                               index=True, ondelete="cascade")
    from_roster = fields.Boolean(string="Z rozpisu služeb", compute="_compute_from_roster", store=True,
                                 help="Služba vznikla z Rozpisu služeb (směna s ordinací). Lékařku, ordinaci, "
                                      "datum a čas jde měnit jen tam.")

    _sql_constraints = [
        ("shift_unique", "unique(shift_id)", "Jedna směna z rozpisu služeb může mít jen jednu službu v ordinaci."),
    ]

    @api.depends("shift_id")
    def _compute_from_roster(self):
        for rec in self:
            rec.from_roster = bool(rec.shift_id)

    # ---------- linked assignments are owned by the roster ----------
    def _check_roster_owned(self, vals=None):
        if self.env.context.get(ROSTER_SYNC):
            return
        if vals is not None and not any(f in vals for f in ROSTER_FIELDS):
            return
        if self.filtered("shift_id"):
            raise UserError(_("Tato služba je z Rozpisu služeb – upravte ji tam."))

    @api.model_create_multi
    def create(self, vals_list):
        if not self.env.context.get(ROSTER_SYNC) and any(v.get("shift_id") for v in vals_list):
            raise UserError(_("Tato služba je z Rozpisu služeb – upravte ji tam."))
        return super().create(vals_list)

    def write(self, vals):
        self._check_roster_owned(vals)
        return super().write(vals)

    def unlink(self):
        self._check_roster_owned()
        return super().unlink()

    @api.depends("doctor_id", "room_id", "hour_from", "hour_to")
    def _compute_display_name(self):
        for rec in self:
            rec.display_name = "%s · %s · %s–%s" % (
                rec.doctor_id.name or "", rec.room_id.name or "",
                format_hour(rec.hour_from), format_hour(rec.hour_to))

    @api.constrains("doctor_id", "room_id", "date", "hour_from", "hour_to")
    def _check_overlap(self):
        """A doctor may serve two rooms at once (overlapping shifts in different rooms);
        two overlapping services of hers in the same room would only be a duplicate."""
        for rec in self:
            if rec.hour_from >= rec.hour_to:
                raise ValidationError(_("Čas „Od“ musí být dřív než „Do“."))
            clash = self.search([
                ("id", "!=", rec.id), ("doctor_id", "=", rec.doctor_id.id), ("room_id", "=", rec.room_id.id),
                ("date", "=", rec.date), ("hour_from", "<", rec.hour_to), ("hour_to", ">", rec.hour_from),
            ], limit=1)
            if clash:
                raise ValidationError(_("%(doctor)s už v tu dobu slouží v ordinaci %(room)s: %(clash)s.",
                                        doctor=rec.doctor_id.name, room=rec.room_id.name, clash=clash.display_name))

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
        copy). The same goes for a doctor who no longer accepts bookings.

        Only manual assignments are copied: the ones from the shift roster come from
        the roster's next week (a copy would be a manual duplicate the roster knows nothing about)."""
        roster = self.filtered("shift_id")
        copied, skipped = 0, 0
        for rec in (self - roster).sorted(lambda r: (r.date, r.hour_from)):
            if not rec.doctor_id.accepts_bookings:
                skipped += 1
                continue
            new_date = rec.date + timedelta(days=7)
            clash = self.search_count([
                ("doctor_id", "=", rec.doctor_id.id), ("room_id", "=", rec.room_id.id), ("date", "=", new_date),
                ("hour_from", "<", rec.hour_to), ("hour_to", ">", rec.hour_from),
            ])
            if clash:
                skipped += 1
                continue
            rec.copy({"date": new_date})
            copied += 1
        message = _("Zkopírováno %(ok)s, přeskočeno %(skip)s.", ok=copied, skip=skipped)
        if roster:
            message += " " + _("%(n)s služeb je z Rozpisu služeb – ty se nekopírují, zadávají se tam.",
                               n=len(roster))
        return {
            "type": "ir.actions.client", "tag": "display_notification",
            "params": {
                "title": _("Kopírování na další týden"),
                "message": message,
                "type": "success" if not skipped and not roster else "warning",
                "next": {"type": "ir.actions.client", "tag": "soft_reload"},
            },
        }
