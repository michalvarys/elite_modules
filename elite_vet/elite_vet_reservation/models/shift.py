"""Shift roster (elite_vet_calendar) → doctor assignments for reservations.

The clinic enters a doctor's shift once, in Rozpis služeb. A shift with a room
(`room_id`) keeps exactly one linked elite.vet.doctor.assignment (assignment.shift_id):
date and doctor from the shift, hours from the shift type. Without a room (a nurse,
a doctor not working in a room that day, a full-day note) there is no assignment.

The sync runs on create / write / unlink of a shift and when a shift type's time
changes (only shifts of today and later). An existing manual assignment of the same
doctor on the same day that overlaps is taken over (linked and updated) instead of
creating a duplicate. elite_vet_calendar itself stays untouched.
"""
from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError

from .doctor_assignment import ROSTER_SYNC
from .live import notify_board


def roster_hours(shift_type):
    """(hour_from, hour_to) of an assignment for a shift type. A night shift ends the
    next morning (20:00–8:00); the assignment lives on one day, so it ends at midnight."""
    h_from, h_to = shift_type.time_from, shift_type.time_to
    if h_to <= h_from:
        h_to = 24.0
    return h_from, h_to


class VetShift(models.Model):
    _inherit = "elite.vet.shift"

    room_id = fields.Many2one(
        "elite.vet.room", string="Ordinace", ondelete="restrict",
        help="Ve které ordinaci lékařka slouží. Směna s ordinací se sama propíše do rezervací "
             "(Rezervace → Rozpis lékařů, tabule, volné termíny). Prázdné = směna se do rezervací "
             "nepropíše (např. sestra). Předvyplní se výchozí ordinace lékařky.")
    accepts_bookings = fields.Boolean(related="doctor_id.accepts_bookings")
    assignment_ids = fields.One2many("elite.vet.doctor.assignment", "shift_id", string="Služba v rezervacích")

    # ---------- defaults and validation ----------
    @api.onchange("doctor_id")
    def _onchange_doctor_room(self):
        """Another doctor = her default room (empty for a nurse / a doctor without one)."""
        if self.type_id.is_note or not self.doctor_id.accepts_bookings:
            self.room_id = False
        else:
            self.room_id = self.doctor_id.default_room_id

    @api.onchange("type_id")
    def _onchange_type_room(self):
        """A full-day note has no room; a room chosen by hand survives a change of the shift type."""
        if self.type_id.is_note:
            self.room_id = False
        elif not self.room_id and self.doctor_id.accepts_bookings:
            self.room_id = self.doctor_id.default_room_id

    @api.constrains("room_id", "doctor_id", "type_id")
    def _check_room(self):
        for shift in self.filtered("room_id"):
            if shift.type_id.is_note:
                raise ValidationError(_(
                    "Ordinace patří jen ke službě lékařky. „%s“ je celodenní poznámka – ordinaci smažte.")
                    % shift.type_id.name)
            if not shift.doctor_id.accepts_bookings:
                raise ValidationError(_(
                    "%s nepřijímá rezervace, proto u její směny nemůže být ordinace – ordinaci smažte. "
                    "(Lékařky se označují v Rozpis služeb → Lékařky, „Lékařka – přijímá rezervace“.)")
                    % (shift.doctor_id.name or _("Lékařka")))

    @api.model_create_multi
    def create(self, vals_list):
        Doctor = self.env["elite.vet.doctor"]
        Type = self.env["elite.vet.shift.type"]
        for vals in vals_list:
            # Default room also for shifts created without the form (import, API, copy of a row).
            if "room_id" not in vals and vals.get("doctor_id"):
                doctor = Doctor.browse(vals["doctor_id"])
                type_id = vals.get("type_id") or self.default_get(["type_id"]).get("type_id")
                if doctor.accepts_bookings and doctor.default_room_id and not Type.browse(type_id).is_note:
                    vals["room_id"] = doctor.default_room_id.id
        shifts = super().create(vals_list)
        shifts._sync_assignments()
        return shifts

    def write(self, vals):
        res = super().write(vals)
        if any(f in vals for f in ("room_id", "doctor_id", "date", "type_id")):
            self._sync_assignments()
        return res

    def unlink(self):
        self.env["elite.vet.doctor.assignment"].sudo().with_context(**{ROSTER_SYNC: True}).search(
            [("shift_id", "in", self.ids)]).unlink()
        return super().unlink()

    # ---------- sync ----------
    def _wants_assignment(self):
        self.ensure_one()
        return bool(self.room_id and self.doctor_id and self.doctor_id.accepts_bookings
                    and not self.type_id.is_note)

    def _assignment_vals(self):
        self.ensure_one()
        h_from, h_to = roster_hours(self.type_id)
        return {"doctor_id": self.doctor_id.id, "room_id": self.room_id.id, "date": self.date,
                "hour_from": h_from, "hour_to": h_to}

    def _sync_assignments(self):
        """Create / update / delete the linked assignment of each shift.

        Sudo: whoever manages the roster need not have rights to Rezervace; the sync is
        the roster's own bookkeeping. Constraint errors (a doctor already on duty)
        are turned into a message naming the shift."""
        Assignment = self.env["elite.vet.doctor.assignment"].sudo().with_context(**{ROSTER_SYNC: True})
        for shift in self:
            linked = Assignment.search([("shift_id", "=", shift.id)])
            if not shift._wants_assignment():
                linked.unlink()
                continue
            vals = shift._assignment_vals()
            try:
                if linked:
                    current = {"doctor_id": linked.doctor_id.id, "room_id": linked.room_id.id, "date": linked.date,
                               "hour_from": linked.hour_from, "hour_to": linked.hour_to}
                    changed = {k: v for k, v in vals.items() if current[k] != v}
                    if changed:
                        linked.write(changed)
                    continue
                manual = Assignment.search([
                    ("shift_id", "=", False), ("doctor_id", "=", vals["doctor_id"]), ("date", "=", vals["date"]),
                    ("hour_from", "<", vals["hour_to"]), ("hour_to", ">", vals["hour_from"]),
                ], order="hour_from, id", limit=1)
                if manual:
                    manual.write(dict(vals, shift_id=shift.id))
                else:
                    Assignment.create(dict(vals, shift_id=shift.id))
            except (ValidationError, UserError) as e:
                raise ValidationError(_(
                    "Směnu „%(shift)s“ (%(date)s) nejde propsat do rezervací: %(reason)s",
                    shift=shift.display_name, date=shift.date.strftime("%d. %m. %Y"),
                    reason=e.args[0])) from e

    # ---------- import of the existing roster ----------
    def action_roster_to_reservations(self):
        """"Převzít rozpis do rezervací": shifts from today on without a room get the
        doctor's default room (which creates the assignment). Not run automatically."""
        if not self.env.user.has_group("elite_vet_reservation.group_reservation_manager"):
            raise AccessError(_("Převzít rozpis do rezervací smí jen Správce rezervací."))
        today = fields.Date.context_today(self)
        shifts = self.search([("date", ">=", today), ("room_id", "=", False), ("type_id.is_note", "=", False),
                              ("doctor_id.accepts_bookings", "=", True)], order="date, id")
        done, no_room, clash = 0, 0, 0
        for shift in shifts:
            room = shift.doctor_id.default_room_id
            if not room:
                no_room += 1
                continue
            try:
                with self.env.cr.savepoint():
                    shift.room_id = room
                done += 1
            except ValidationError:
                # The savepoint rolled back the database and cleared the cache (and precommit hooks).
                clash += 1
        if done:
            notify_board(self.env)   # the rollback of a clash dropped the queued board refresh
        message = _("Propsáno %(done)s. Přeskočeno: bez výchozí ordinace %(no_room)s, kolize %(clash)s.",
                    done=done, no_room=no_room, clash=clash)
        return {
            "type": "ir.actions.client", "tag": "display_notification",
            "params": {
                "title": _("Převzít rozpis do rezervací"),
                "message": message,
                "type": "success" if not (no_room or clash) else "warning",
                "sticky": bool(no_room or clash),
                "next": {"type": "ir.actions.client", "tag": "soft_reload"},
            },
        }


class VetShiftType(models.Model):
    _inherit = "elite.vet.shift.type"

    def write(self, vals):
        res = super().write(vals)
        if any(f in vals for f in ("time_from", "time_to", "is_note")):
            today = fields.Date.context_today(self)
            shifts = self.env["elite.vet.shift"].search([("type_id", "in", self.ids), ("date", ">=", today)])
            if vals.get("is_note"):
                # A full-day note has no room (and so no assignment).
                shifts.filtered("room_id").write({"room_id": False})
            else:
                shifts.filtered("room_id")._sync_assignments()
        return res
