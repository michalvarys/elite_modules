"""Server side of Plánování (client action elite_vet_planning.planner) and Moje dostupnost.

Every change returns the whole month again: the month is small (a few hundred shifts) and
the screen then never shows anything the server does not have."""
import calendar
from collections import defaultdict
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError

from odoo.addons.elite_vet_calendar.models.holidays import holidays_between
from odoo.addons.elite_vet_reservation.models.live import notify_board
from odoo.addons.elite_vet_reservation.models.shift import roster_hours

from .doctor import STAFF_ROLES
from .staff_request import ABSENCE_CODES, CREDITED_CODES, REQUEST_CODES, SELF_CODES, SHORT

ROLE_ORDER = {key: i for i, (key, _label) in enumerate(STAFF_ROLES)}
MANAGER_GROUP = "elite_vet_calendar.group_calendar_manager"


def month_bounds(month):
    """'2026-11-15' / date -> (1st day, last day)."""
    first = fields.Date.to_date(month).replace(day=1)
    return first, first.replace(day=calendar.monthrange(first.year, first.month)[1])


def working_days(first, last):
    """Mon–Fri of the range that are not public holidays (the fond counts only these)."""
    holidays = holidays_between(first, last)
    return [first + timedelta(days=i) for i in range((last - first).days + 1)
            if (first + timedelta(days=i)).weekday() < 5 and (first + timedelta(days=i)) not in holidays]


def day_hours(spans):
    """Union of [(from, to)] in hours: 8–16 + 12–20 = 12 h, not 16 h (the overlap counts once)."""
    total, end = 0.0, None
    for h_from, h_to in sorted(spans):
        if end is None or h_from > end:
            total += h_to - h_from
            end = h_to
        elif h_to > end:
            total += h_to - end
            end = h_to
    return total


def month_balance(members, shifts, requests, first, last, assignments=()):
    """{member id: balance row} for the month.

    fond        = working days (Mon–Fri without holidays) × weekly hours / 5
    worked      = shift hours (overlaps on a day counted once) + D / L / Š on working days × daily fond
    morning / afternoon / full_day = weekday counts (full day = 12 h and more), weekend = Sat + Sun
    NV and PN add nothing; saldo = worked − fond. `assignments`: manual services of Rozpis lékařů
    (without a shift) count like shifts.
    """
    workdays = set(working_days(first, last))
    spans = defaultdict(list)
    for shift in shifts:
        if shift.doctor_id and not shift.type_id.is_note:
            spans[(shift.doctor_id.id, shift.date)].append(roster_hours(shift.hour_from, shift.hour_to))
    for a in assignments:   # services entered straight in Rozpis lékařů (no shift)
        spans[(a.doctor_id.id, a.date)].append((a.hour_from, a.hour_to))
    absences = defaultdict(list)
    for req in requests:
        if req.code in ABSENCE_CODES:
            absences[req.member_id.id].append(req)
    out = {}
    for member in members:
        daily = (member.weekly_hours or 0.0) / 5.0
        row = {"fond": len(workdays) * daily, "shift_hours": 0.0, "credited": 0.0, "morning": 0, "afternoon": 0,
               "full_day": 0, "weekend": 0, "weekend_hours": 0.0, "absences": dict.fromkeys(ABSENCE_CODES, 0)}
        for (member_id, day), day_spans in spans.items():
            if member_id != member.id:
                continue
            hours = day_hours(day_spans)
            row["shift_hours"] += hours
            if day.weekday() >= 5:
                row["weekend"] += 1
                row["weekend_hours"] += hours
            elif hours >= 12:
                row["full_day"] += 1
            elif min(f for f, _t in day_spans) < 12:
                row["morning"] += 1
            else:
                row["afternoon"] += 1
        for req in absences[member.id]:
            row["absences"][req.code] += 1
            if req.code in CREDITED_CODES and req.date in workdays:
                row["credited"] += daily
        row["worked"] = row["shift_hours"] + row["credited"]
        row["saldo"] = row["worked"] - row["fond"]
        out[member.id] = row
    return out


class Planner(models.AbstractModel):
    _name = "elite.vet.planner"
    _description = "Plánování služeb"

    # ---------- helpers ----------
    @api.model
    def _check_manager(self):
        if not self.env.user.has_group(MANAGER_GROUP):
            raise AccessError(_("Plánovat služby smí jen Správce rozpisu."))

    @api.model
    def _members(self):
        members = self.env["elite.vet.doctor"].sudo().search([("in_planning", "=", True)])
        return members.sorted(lambda m: (ROLE_ORDER.get(m.staff_role, 9), m.planning_sequence, m.name))

    @api.model
    def _member_vals(self, member):
        return {"id": member.id, "name": member.name, "initials": member.initials or "?",
                "role": member.staff_role, "color": member.planning_color,
                "weekly_hours": member.weekly_hours, "accepts_bookings": member.accepts_bookings,
                "vacation_left": member.vacation_left}

    @api.model
    def _shift_vals(self, shift, slot=None):
        slot = slot if slot is not None else shift.planning_slot_id
        return {"id": shift.id, "date": fields.Date.to_string(shift.date), "slot_id": slot.id or 0,
                "row_id": slot.row_id.id or 0, "member_id": shift.doctor_id.id,
                "helper_name": shift.helper_name or "", "hour_from": shift.hour_from, "hour_to": shift.hour_to,
                "room": shift.room_id.name or "", "type": shift.type_id.name or "",
                "from_roster": not shift.planning_slot_id, "booking": self._booking_status(shift, slot)}

    @api.model
    def _booking_status(self, shift, slot):
        """Does the shift reach the reservation calendar, and if not, why (shown in the cell dialog).
        ok = True / False, or None for people who never go there (nurses, reception, helpers)."""
        doctor = shift.doctor_id
        if not doctor or (doctor.staff_role != "doctor" and not doctor.accepts_bookings):
            return {"ok": None, "text": ""}
        if not doctor.accepts_bookings:
            return {"ok": False, "text": _("Nepropisuje se do rezervací: %s nemá v Lékařkách zaškrtnuto "
                                           "„Lékařka – přijímá rezervace“.") % doctor.name}
        if not shift.room_id:
            if slot and not slot.row_id.room_id:
                return {"ok": False, "text": _("Nepropisuje se do rezervací: úsek %s nemá v Úsecích plánu "
                                               "vyplněnou ordinaci.") % slot.row_id.name}
            return {"ok": False, "text": _("Nepropisuje se do rezervací: směna nemá ordinaci.")}
        assignment = self.env["elite.vet.doctor.assignment"].sudo().search([
            ("doctor_id", "=", doctor.id), ("date", "=", shift.date), ("room_id", "=", shift.room_id.id),
            ("hour_from", "<=", shift.hour_from), ("hour_to", ">", shift.hour_from)], limit=1)
        if not assignment:
            return {"ok": False, "text": _("V kalendáři rezervací chybí. Uložte směnu znovu (změňte a vraťte čas).")}
        return {"ok": True, "text": _("V kalendáři rezervací: %s") % assignment.display_name}

    @api.model
    def _roster_slot(self, shift, rows):
        return self._slot_for(rows, shift.date, shift.room_id or shift.doctor_id.default_room_id,
                              shift.doctor_id.staff_role if shift.doctor_id else "helper",
                              shift.type_id, shift.hour_from)

    @api.model
    def _slot_for(self, rows, day, room, role, shift_type, hour_from):
        """Slot of the plan where a shift entered in Rozpis služeb (no planning_slot_id) is shown.
        Only for display, the shift itself is not changed. Row: the one with the shift's room,
        else the one with the doctor's default room, else by role (reception / helpers).
        Slot in the row: among the slots of the same shift type on that day (else all of that day,
        else the same type, else all) the one with the nearest start. No row -> empty slot (the
        "Z rozpisu – bez úseku" row of the screen)."""
        Slot = self.env["elite.vet.planning.slot"]
        row = rows.filtered(lambda r: room and r.room_id == room)[:1]
        if not row:
            if role == "helper":
                row = rows.filtered(lambda r: r.kind == "helpers")[:1]
            elif role == "reception":
                row = rows.filtered(lambda r: r.kind == "room" and not r.room_id
                                    and "reception" in (r.preferred_roles or ""))[:1]
        if not row or not row.slot_ids:
            return Slot
        slots = row.slot_ids
        on_day = slots.filtered(lambda sl: sl.applies_to(day))
        same_type = slots.filtered(lambda sl: shift_type and sl.type_id == shift_type)
        candidates = (same_type & on_day) or on_day or same_type or slots
        return candidates.sorted(lambda sl: (abs(sl.hour_from - hour_from), sl.sequence, sl.id))[:1]

    @api.model
    def _days(self, first, last, notes=None):
        """Days of the month; `notes` = full-day notes of the roster (Zavřeno …) by date."""
        holidays = holidays_between(first, last)
        today = fields.Date.context_today(self)
        notes = notes or {}
        return [{"date": fields.Date.to_string(d), "day": d.day, "weekday": d.weekday(),
                 "weekend": d.weekday() >= 5, "holiday": holidays.get(d) or "", "today": d == today,
                 "note": notes.get(d, "")}
                for d in (first + timedelta(days=i) for i in range((last - first).days + 1))]

    # ---------- management ----------
    @api.model
    def load_month(self, month):
        self._check_manager()
        first, last = month_bounds(month)
        members = self._members()
        Shift = self.env["elite.vet.shift"].sudo()
        shifts = Shift.search([("date", ">=", first), ("date", "<=", last)])
        day_notes = {}
        for note in shifts.filtered("type_id.is_note"):
            day_notes[note.date] = ", ".join(filter(None, [day_notes.get(note.date), note.display_name]))
        requests = self.env["elite.vet.staff.request"].sudo().search([("date", ">=", first), ("date", "<=", last)])
        notes = self.env["elite.vet.staff.month.note"].sudo().search([("month", "=", first)])
        rows = self.env["elite.vet.planning.row"].sudo().search([])
        manual = self._manual_assignments(first, last)
        balance = month_balance(members, shifts.filtered(lambda s: s.doctor_id in members), requests, first, last,
                                manual.filtered(lambda a: a.doctor_id in members))
        shift_vals = []
        for shift in shifts.filtered(lambda x: not x.type_id.is_note and (x.doctor_id or x.helper_name)):
            slot = shift.planning_slot_id or self._roster_slot(shift, rows)
            shift_vals.append(self._shift_vals(shift, slot))
        # Services entered straight in Rezervace › Rozpis lékařů (no shift): shown with a negative id.
        Slot = self.env["elite.vet.planning.slot"]
        for a in manual:
            slot = self._slot_for(rows, a.date, a.room_id, "doctor", False, a.hour_from)
            shift_vals.append({"id": -a.id, "date": fields.Date.to_string(a.date), "slot_id": slot.id or 0,
                               "row_id": slot.row_id.id or 0, "member_id": a.doctor_id.id, "helper_name": "",
                               "hour_from": a.hour_from, "hour_to": a.hour_to, "room": a.room_id.name or "",
                               "type": _("Rozpis lékařů"), "from_roster": True, "assignment": True,
                               "booking": {"ok": True, "text": _("V kalendáři rezervací (zadáno v Rozpisu lékařů)")}})
        row_vals = [{"id": r.id, "name": r.name, "kind": r.kind, "room": r.room_id.name or "",
                     "preferred_roles": [x.strip() for x in (r.preferred_roles or "").split(",") if x.strip()],
                     "slots": [{"id": sl.id, "name": sl.name, "hour_from": sl.hour_from, "hour_to": sl.hour_to,
                                "days": sl.days, "time": sl.time_display} for sl in r.slot_ids]}
                    for r in rows]
        if any(not v["slot_id"] for v in shift_vals):
            # shifts no row fits (e.g. a room without a row): one read-only row, so nothing is hidden
            row_vals.append({"id": 0, "name": _("Z rozpisu – bez úseku"), "kind": "roster", "room": "",
                             "preferred_roles": [], "slots": [{"id": 0, "name": _("Ostatní"), "hour_from": 0,
                                                               "hour_to": 0, "days": "all", "time": ""}]})
        return {
            "month": fields.Date.to_string(first),
            "days": self._days(first, last, day_notes),
            "rows": row_vals,
            "staff": [self._member_vals(m) for m in members],
            "roles": [{"key": k, "label": label} for k, label in STAFF_ROLES],
            # planned shifts and the ones entered in Rozpis služeb (shown in their slot, from_roster)
            "shifts": shift_vals,
            "requests": [{"member_id": r.member_id.id, "date": fields.Date.to_string(r.date), "code": r.code,
                          "short": SHORT[r.code], "note": r.note or "", "self": r.entered_by_member}
                         for r in requests],
            "codes": [{"key": k, "label": label, "short": SHORT[k], "absence": k in ABSENCE_CODES}
                      for k, label in REQUEST_CODES],
            "notes": {n.member_id.id: n.note or "" for n in notes},
            "balance": balance,
        }

    @api.model
    def add_shift(self, month, slot_id, day, member_id=False, helper_name=False, hour_from=None, hour_to=None):
        self._check_manager()
        slot = self.env["elite.vet.planning.slot"].browse(slot_id).exists()
        if not slot:
            raise UserError(_("Tato směna v plánu už neexistuje. Načtěte stránku znovu."))
        vals = {"date": day, "type_id": slot.type_id.id, "planning_slot_id": slot.id,
                "hour_from": slot.hour_from if hour_from is None else hour_from,
                "hour_to": slot.hour_to if hour_to is None else hour_to, "room_id": False}
        if member_id:
            member = self.env["elite.vet.doctor"].browse(member_id)
            vals["doctor_id"] = member.id
            if slot.row_id.room_id and member.accepts_bookings:
                vals["room_id"] = slot.row_id.room_id.id
        else:
            helper_name = (helper_name or "").strip()
            if not helper_name:
                raise UserError(_("Vyberte člověka nebo vepište jméno."))
            if slot.row_id.kind != "helpers":
                raise UserError(_("Vepsat jméno jde jen v úseku Stáž / výpomoc."))
            vals["helper_name"] = helper_name
        self.env["elite.vet.shift"].create(vals)
        return self.load_month(month)

    @api.model
    def update_shift(self, month, shift_id, hour_from, hour_to):
        self._check_manager()
        self._record(shift_id).write({"hour_from": hour_from, "hour_to": hour_to})
        return self.load_month(month)

    @api.model
    def remove_shift(self, month, shift_id):
        self._check_manager()
        self._record(shift_id).unlink()
        return self.load_month(month)

    @api.model
    def _record(self, shift_id):
        """Positive id = shift, negative = manual service of Rozpis lékařů (see load_month).
        Sudo for the service: Správce rozpisu need not have rights to Rezervace."""
        if shift_id < 0:
            return self.env["elite.vet.doctor.assignment"].sudo().browse(-shift_id).exists().filtered(
                lambda a: not a.shift_id)
        return self.env["elite.vet.shift"].browse(shift_id).exists()

    @api.model
    def _manual_assignments(self, first, last):
        return self.env["elite.vet.doctor.assignment"].sudo().search(
            [("date", ">=", first), ("date", "<=", last), ("shift_id", "=", False)])

    @api.model
    def adopt_assignments(self, month):
        """"Převzít služby z Rozpisu lékařů": each manual service of the month becomes a planned
        shift with the same doctor, room, day and time. The roster sync then takes the service over
        (links it, procedures and note stay), so nothing is entered twice. A service whose room
        has no row of the plan is skipped."""
        self._check_manager()
        first, last = month_bounds(month)
        rows = self.env["elite.vet.planning.row"].search([])
        Shift = self.env["elite.vet.shift"]
        done = skipped = 0
        for a in self._manual_assignments(first, last).sorted(lambda x: (x.date, x.hour_from)):
            if not a.exists() or a.shift_id:
                continue   # already taken over by a shift created a moment ago
            slot = self._slot_for(rows, a.date, a.room_id, "doctor", False, a.hour_from)
            if not slot or slot.row_id.room_id != a.room_id:
                skipped += 1
                continue
            try:
                with self.env.cr.savepoint():
                    Shift.create({"date": a.date, "doctor_id": a.doctor_id.id, "type_id": slot.type_id.id,
                                  "planning_slot_id": slot.id, "room_id": a.room_id.id,
                                  "hour_from": a.hour_from, "hour_to": a.hour_to})
                done += 1
            except (UserError, ValueError):
                skipped += 1
        if done:
            notify_board(self.env)
        result = self.load_month(month)
        result["message"] = _("Převzato %(ok)s služeb, přeskočeno %(skip)s (ordinace bez úseku nebo kolize).",
                              ok=done, skip=skipped)
        return result

    @api.model
    def copy_previous_week(self, month, monday):
        """Shifts of the week before `monday` (planned or entered in Rozpis služeb) are copied 7 days ahead (within `month`).
        Skipped: a person who already has that slot that day, or has an absence / "Nemůžu"."""
        self._check_manager()
        first, last = month_bounds(month)
        start = fields.Date.to_date(monday)
        Shift = self.env["elite.vet.shift"]
        rows = self.env["elite.vet.planning.row"].search([])
        source = Shift.search([("date", ">=", start - timedelta(days=7)), ("date", "<", start),
                               ("type_id.is_note", "=", False)])
        blocked = {(r.member_id.id, r.date) for r in self.env["elite.vet.staff.request"].search(
            [("date", ">=", start), ("date", "<", start + timedelta(days=7)),
             ("code", "in", list(ABSENCE_CODES) + ["off"])])}
        copied = skipped = 0
        for shift in source:
            day = shift.date + timedelta(days=7)
            if not (first <= day <= last):
                continue
            slot = shift.planning_slot_id or self._roster_slot(shift, rows)
            if not slot:
                skipped += 1
                continue
            taken = Shift.search_count([("planning_slot_id", "=", slot.id), ("date", "=", day),
                                        ("doctor_id", "=", shift.doctor_id.id),
                                        ("helper_name", "=", shift.helper_name or False)])
            if taken or (shift.doctor_id.id, day) in blocked:
                skipped += 1
                continue
            try:
                with self.env.cr.savepoint():
                    shift.copy({"date": day, "planning_slot_id": slot.id})
                copied += 1
            except (UserError, ValueError):
                skipped += 1
        if copied:
            notify_board(self.env)   # a rolled-back savepoint drops the queued board refresh
        result = self.load_month(month)
        result["message"] = _("Zkopírováno %(ok)s směn, přeskočeno %(skip)s.", ok=copied, skip=skipped)
        return result

    @api.model
    def set_request(self, month, member_id, day, code=False, note=None):
        self._check_manager()
        self._write_request(self.env["elite.vet.doctor"].browse(member_id), day, code, note, by_member=False)
        return self.load_month(month)

    @api.model
    def set_month_note(self, month, member_id, note):
        self._check_manager()
        first, _last = month_bounds(month)
        Note = self.env["elite.vet.staff.month.note"]
        rec = Note.search([("member_id", "=", member_id), ("month", "=", first)])
        if rec:
            rec.note = note
        elif note:
            Note.create({"member_id": member_id, "month": first, "note": note})
        return True

    @api.model
    def move_member(self, month, member_id, direction):
        """Arrow up / down in Požadavky na směny: swaps with the neighbour of the same role."""
        self._check_manager()
        members = self._members()
        member = members.filtered(lambda m: m.id == member_id)
        same = members.filtered(lambda m: m.staff_role == member.staff_role)
        ordered = list(same)
        i = ordered.index(member)
        j = i + (1 if direction > 0 else -1)
        if 0 <= j < len(ordered):
            ordered[i], ordered[j] = ordered[j], ordered[i]
            for seq, rec in enumerate(ordered, start=1):
                rec.planning_sequence = seq * 10
        return self.load_month(month)

    @api.model
    def _write_request(self, member, day, code, note, by_member):
        Request = self.env["elite.vet.staff.request"].sudo()
        day = fields.Date.to_date(day)
        rec = Request.search([("member_id", "=", member.id), ("date", "=", day)])
        if not code:
            rec.unlink()
            return
        vals = {"code": code, "entered_by_member": by_member}
        if note is not None:
            vals["note"] = note
        if rec:
            rec.write(vals)
        else:
            Request.create(dict(vals, member_id=member.id, date=day))

    # ---------- Moje dostupnost (the logged-in team member) ----------
    @api.model
    def _my_member(self):
        member = self.env.user.sudo().elite_vet_doctor_id
        if not member:
            raise UserError(_("Váš účet není propojený s členem týmu. Požádejte vedení, ať vás propojí "
                              "v Rozpis služeb › Lékařky › Účet."))
        return member

    @api.model
    def my_month(self, month):
        member = self.env.user.sudo().elite_vet_doctor_id
        first, last = month_bounds(month)
        result = {"month": fields.Date.to_string(first), "days": self._days(first, last), "member": False,
                  "codes": [{"key": k, "label": label, "short": SHORT[k]} for k, label in REQUEST_CODES
                            if k in SELF_CODES]}
        if not member:
            return result
        shifts = self.env["elite.vet.shift"].sudo().search(
            [("doctor_id", "=", member.id), ("date", ">=", first), ("date", "<=", last)])
        requests = self.env["elite.vet.staff.request"].sudo().search(
            [("member_id", "=", member.id), ("date", ">=", first), ("date", "<=", last)])
        labels = dict(REQUEST_CODES)
        result.update({
            "member": self._member_vals(member),
            "shifts": [dict(self._shift_vals(s), row=s.planning_slot_id.display_name or s.type_id.name or "") for s in shifts],
            "requests": {fields.Date.to_string(r.date): {"code": r.code, "short": SHORT[r.code],
                                                         "label": labels[r.code], "note": r.note or "",
                                                         "locked": r.code not in SELF_CODES}
                         for r in requests},
            "balance": month_balance(member, shifts, requests, first, last, self.env["elite.vet.doctor.assignment"].sudo().search(
                [("doctor_id", "=", member.id), ("date", ">=", first), ("date", "<=", last),
                 ("shift_id", "=", False)]))[member.id],
        })
        return result

    @api.model
    def set_my_request(self, month, day, code=False, note=None):
        """A team member's own availability: only the codes Můžu / Jen ráno / Jen odpoledne /
        Nemůžu, only from today on, and never over an absence entered by the management."""
        member = self._my_member()
        day = fields.Date.to_date(day)
        if day < fields.Date.context_today(self):
            raise UserError(_("Minulé dny už měnit nejde."))
        if code and code not in SELF_CODES:
            raise UserError(_("Dovolenou, NV, lékaře, nemoc a školení zapisuje vedení."))
        current = self.env["elite.vet.staff.request"].sudo().search([("member_id", "=", member.id),
                                                                     ("date", "=", day)])
        if current and current.code not in SELF_CODES:
            raise UserError(_("Na tento den má vedení zapsanou absenci (%s). Změnu domluvte s vedením.")
                            % dict(REQUEST_CODES)[current.code])
        self._write_request(member, day, code, note, by_member=True)
        return self.my_month(month)

    @api.model
    def fill_my_month(self, month, code):
        """"Zbytek měsíce: Můžu" - every day from today on without a record gets the code."""
        member = self._my_member()
        if code not in SELF_CODES:
            raise UserError(_("Tento záznam si zadat nejde."))
        first, last = month_bounds(month)
        start = max(first, fields.Date.context_today(self))
        Request = self.env["elite.vet.staff.request"].sudo()
        taken = set(Request.search([("member_id", "=", member.id), ("date", ">=", start),
                                    ("date", "<=", last)]).mapped("date"))
        Request.create([{"member_id": member.id, "date": start + timedelta(days=i), "code": code,
                         "entered_by_member": True}
                        for i in range((last - start).days + 1) if start + timedelta(days=i) not in taken])
        return self.my_month(month)
