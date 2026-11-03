"""Planning on top of the shift roster.

Every assignment made in Plánování is an elite.vet.shift with the slot it was planned in
(`planning_slot_id`). Rezervace (elite_vet_reservation/models/shift.py) turns a doctor's
shift with a room into one assignment in the reservation calendar; this module adds:

* free-text helpers (praktikanti, brigádníci) - a shift without a team member;
* merging (planned shifts only): the plan has a doctor in "Ranní 8–16" and "Odpolední 12–20" of the same room
  as two shifts, the reservation calendar gets one service 8–20 (two overlapping
  services in one room would break the assignment's overlap check);
* the public /rozpis-lekaru shows only doctors' planned shifts, not reception, nurses or helpers.
"""
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

from odoo.addons.elite_vet_reservation.models.shift import VetShift as ReservationShift, roster_hours


class VetShift(models.Model):
    _inherit = "elite.vet.shift"

    planning_slot_id = fields.Many2one("elite.vet.planning.slot", string="Směna v plánu", ondelete="set null",
                                       index="btree_not_null", copy=False)
    planning_row_id = fields.Many2one(related="planning_slot_id.row_id", string="Úsek", store=True)
    helper_name = fields.Char(string="Jméno (výpomoc)",
                              help="Praktikant nebo brigádník, který není v seznamu týmu.")
    web_visible = fields.Boolean(
        string="Na webu", compute="_compute_web_visible", store=True,
        help="Na /rozpis-lekaru jdou celodenní poznámky, směny zadané v rozpisu ručně a z plánu jen "
             "služby lékařek v úsecích (ne recepce, sestry ani výpomoc).")

    @api.depends("planning_slot_id.row_id.kind", "type_id.is_note", "doctor_id.accepts_bookings")
    def _compute_web_visible(self):
        for shift in self:
            if shift.type_id.is_note or not shift.planning_slot_id:
                shift.web_visible = True
            else:
                shift.web_visible = (shift.planning_row_id.kind == "room"
                                     and bool(shift.doctor_id.accepts_bookings))

    @api.depends("helper_name")
    def _compute_display_name(self):
        super()._compute_display_name()
        for shift in self.filtered(lambda s: s.helper_name and not s.doctor_id):
            shift.display_name = "%s — %s" % (shift.helper_name, shift.type_id.name or "")

    @api.constrains("doctor_id", "type_id")
    def _check_doctor(self):
        # A free-text helper is a shift without a team member.
        super(VetShift, self.filtered(lambda s: not s.helper_name))._check_doctor()

    # ---------- merging into one service per doctor, day and room ----------
    def _base_wants_assignment(self):
        return ReservationShift._wants_assignment(self)

    def _assignment_cluster(self):
        """(first shift, from, to) of the group of this doctor's shifts on the same day in the
        same room whose times overlap or touch this one. The first one carries the assignment."""
        self.ensure_one()
        siblings = self.search([("doctor_id", "=", self.doctor_id.id), ("date", "=", self.date),
                                ("room_id", "=", self.room_id.id), ("planning_slot_id", "!=", False)])
        spans = sorted(((*roster_hours(s.hour_from, s.hour_to), s.id), s)
                       for s in siblings | self if s._base_wants_assignment())
        clusters = []   # [from, [shifts], to]
        for (h_from, h_to, _id), shift in spans:
            if clusters and h_from <= clusters[-1][2]:
                clusters[-1][1].append(shift)
                clusters[-1][2] = max(clusters[-1][2], h_to)
            else:
                clusters.append([h_from, [shift], h_to])
        for h_from, members, h_to in clusters:
            if self in members:
                return members[0], h_from, h_to
        return self, *roster_hours(self.hour_from, self.hour_to)

    def _wants_assignment(self):
        # Only planned shifts merge; two overlapping shifts entered by hand stay a clash (as before).
        if not self.planning_slot_id:
            return self._base_wants_assignment()
        return self._base_wants_assignment() and self._assignment_cluster()[0] == self

    def _assignment_vals(self):
        vals = super()._assignment_vals()
        if self.planning_slot_id:
            _first, vals["hour_from"], vals["hour_to"] = self._assignment_cluster()
        return vals

    def _same_day_shifts(self):
        """This doctor's other shifts on the same days (the ones whose merge may change)."""
        if not self:
            return self
        domain = [("id", "not in", self.ids), ("doctor_id", "in", self.doctor_id.ids),
                  ("date", "in", list(set(self.mapped("date"))))]
        pairs = {(s.doctor_id.id, s.date) for s in self}
        return self.search(domain).filtered(lambda s: (s.doctor_id.id, s.date) in pairs)

    def _sync_assignments(self):
        shifts = (self | self._same_day_shifts()).exists()
        # Shifts merged into another one drop their assignment first, so the first shift of
        # the group can grow over its time without an overlap.
        ordered = shifts.sorted(lambda s: (s._wants_assignment(), s.id))
        return super(VetShift, ordered)._sync_assignments()

    def write(self, vals):
        before = self._same_day_shifts() if any(f in vals for f in ("doctor_id", "date", "room_id")) else self.browse()
        res = super().write(vals)
        (before - self).exists()._sync_assignments()
        return res

    def unlink(self):
        others = self._same_day_shifts()
        res = super().unlink()
        others.exists()._sync_assignments()
        return res

    @api.constrains("helper_name", "doctor_id")
    def _check_helper(self):
        for shift in self:
            if shift.helper_name and shift.doctor_id:
                raise ValidationError(_("Směna má buď člena týmu, nebo vepsané jméno výpomoci, ne obojí."))
