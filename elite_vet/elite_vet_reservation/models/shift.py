"""Shift roster (elite_vet_calendar) → doctor assignments for reservations.

The clinic enters a doctor's shift once, in Rozpis služeb. A shift with a room
(`room_id`) keeps exactly one linked elite.vet.doctor.assignment (assignment.shift_id):
date, doctor and hours (`hour_from` / `hour_to`, prefilled from the shift type, changeable
per shift) from the shift. Without a room (a nurse,
a doctor not working in a room that day, a full-day note) there is no assignment.

The sync runs on create / write / unlink of a shift and when a shift type's time
changes (only shifts of today and later that still have the type's old time). An existing manual assignment of the same
doctor on the same day that overlaps is taken over (linked and updated) instead of
creating a duplicate. elite_vet_calendar itself stays untouched.
"""
from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError

from .doctor_assignment import ROSTER_SYNC
from .live import notify_board


def roster_hours(h_from, h_to):
    """(hour_from, hour_to) of an assignment for a shift's time. A night shift ends the
    next morning (20:00–8:00); the assignment lives on one day, so it ends at midnight."""
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
    # The shift's own time: prefilled from the shift type (again when the type changes),
    # changeable per shift. The website keeps showing the type's time.
    hour_from = fields.Float(string="Od", compute="_compute_hours", store=True, readonly=False,
                             precompute=True, aggregator=None)
    hour_to = fields.Float(string="Do", compute="_compute_hours", store=True, readonly=False,
                           precompute=True, aggregator=None,
                           help="Noční služba může končit druhý den ráno (20:00–8:00).")
    assignment_ids = fields.One2many("elite.vet.doctor.assignment", "shift_id", string="Služba v rezervacích")

    # ---------- defaults and validation ----------
    @api.depends("type_id")
    def _compute_hours(self):
        for shift in self:
            shift.hour_from, shift.hour_to = shift.type_id.time_from, shift.type_id.time_to

    @api.constrains("hour_from", "hour_to", "type_id")
    def _check_hours(self):
        for shift in self.filtered(lambda s: not s.type_id.is_note):
            if not (0 <= shift.hour_from < 24 and 0 < shift.hour_to <= 24) or shift.hour_from == shift.hour_to:
                raise ValidationError(_("Čas služby „Od“ a „Do“ musí být mezi 0:00 a 24:00 a nesmí být stejný."))

    @api.onchange("doctor_id")
    def _onchange_doctor_room(self):
        """Another doctor = her default room (empty for a nurse / a doctor without one).
        A shift added from a room column of the board keeps that room (context ev_keep_room)."""
        if self.env.context.get("ev_keep_room") and self.room_id and not self.type_id.is_note:
            return
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
        if any(f in vals for f in ("room_id", "doctor_id", "date", "type_id", "hour_from", "hour_to")):
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
        h_from, h_to = roster_hours(self.hour_from, self.hour_to)
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
        old_hours = {t.id: (t.time_from, t.time_to) for t in self}
        res = super().write(vals)
        if any(f in vals for f in ("time_from", "time_to", "is_note")):
            today = fields.Date.context_today(self)
            shifts = self.env["elite.vet.shift"].search([("type_id", "in", self.ids), ("date", ">=", today)])
            if vals.get("is_note"):
                # A full-day note has no room (and so no assignment).
                shifts.filtered("room_id").write({"room_id": False})
            else:
                # The new time for shifts that kept the type's time; a time changed by hand stays.
                for shift_type in self:
                    same = shifts.filtered(lambda s: s.type_id == shift_type
                                           and (s.hour_from, s.hour_to) == old_hours[shift_type.id])
                    same.write({"hour_from": shift_type.time_from, "hour_to": shift_type.time_to})
        return res
