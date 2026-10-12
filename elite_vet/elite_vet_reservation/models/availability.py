"""Free slot computation.

Everything is computed in minutes from midnight of the local (Prague) day.
Conversion to UTC happens only at the edges: when reading reservations from
the DB and when returning slots. Minutes instead of floats so that
8.25 + 0.25 does not become 8.4999.
"""
import calendar
from datetime import date, datetime, timedelta

import pytz

from odoo import api, fields, models

from .reservation import TZ
from .holidays import holiday_name


def to_min(hour_float):
    return int(round(hour_float * 60))


def intersect(a, b):
    """Intersection of two sorted lists of (from, to) intervals."""
    out = []
    for af, at in a:
        for bf, bt in b:
            f, t = max(af, bf), min(at, bt)
            if f < t:
                out.append((f, t))
    return sorted(out)


def subtract(a, busy):
    """Subtract busy intervals from free ones."""
    out = list(a)
    for bf, bt in busy:
        nxt = []
        for f, t in out:
            if bt <= f or bf >= t:
                nxt.append((f, t))
                continue
            if f < bf:
                nxt.append((f, bf))
            if bt < t:
                nxt.append((bt, t))
        out = nxt
    return sorted(out)


class VetAvailability(models.AbstractModel):
    _name = "elite.vet.availability"
    _description = "Výpočet volných termínů"

    # ---------- time ----------
    @api.model
    def local_to_utc(self, day, minute):
        local = TZ.localize(datetime(day.year, day.month, day.day) + timedelta(minutes=minute))
        return local.astimezone(pytz.utc).replace(tzinfo=None)

    @api.model
    def utc_to_local_minutes(self, dt, day):
        """Minutes from midnight of `day`; values outside the day are clamped to 0 / 1440."""
        local = pytz.utc.localize(dt).astimezone(TZ)
        # Wall-clock difference (not actually elapsed minutes), so this is the exact
        # inverse of local_to_utc even on daylight-saving transition days.
        midnight = datetime(day.year, day.month, day.day)
        delta = (local.replace(tzinfo=None) - midnight).total_seconds() / 60
        return max(0, min(1440, int(delta)))

    # ---------- inputs ----------
    @api.model
    def open_minutes(self, room, day):
        exc = self.env["elite.vet.room.exception"].search([("room_id", "=", room.id), ("date", "=", day)], limit=1)
        if exc:
            return [] if exc.closed else [(to_min(exc.hour_from), to_min(exc.hour_to))]
        lines = room.hours_ids.filtered(lambda h: int(h.weekday) == day.weekday() and h.applies_on(day))
        return sorted((to_min(h.hour_from), to_min(h.hour_to)) for h in lines)

    @api.model
    def assignment_minutes(self, day, procedure, doctor=None, specialization=None):
        domain = [("date", "=", day)]
        if doctor:
            domain.append(("doctor_id", "=", doctor.id))
        if specialization:
            domain.append(("doctor_id.specialization_ids", "in", specialization.ids))
        out = {}
        for a in self.env["elite.vet.doctor.assignment"].search(domain):
            if not a.serves(procedure):
                continue
            out.setdefault(a.room_id.id, []).append((to_min(a.hour_from), to_min(a.hour_to), a.doctor_id.id))
        return out

    @api.model
    def busy_minutes(self, room_ids, day, scope="web"):
        """Busy minutes per room; for `scope` see elite.vet.reservation._busy_domain."""
        Res = self.env["elite.vet.reservation"]
        start, stop = self.local_to_utc(day, 0), self.local_to_utc(day, 1440)
        out = {rid: [] for rid in room_ids}
        for r in Res.search(Res._busy_domain(room_ids, start, stop, scope=scope)):
            iv = (self.utc_to_local_minutes(r.start, day), self.utc_to_local_minutes(r.stop, day))
            targets = [r.room_id.id] if r.room_id else list(room_ids)
            for rid in targets:
                if rid in out:
                    out[rid].append(iv)
        return out

    @api.model
    def web_day_note(self, day):
        """Why the website does not book on this day (weekend / public holiday per settings), otherwise None.

        Applies to the website only; reception books normally on such days.
        Nothing is stored - it is derived from the date and the settings.
        """
        s = self.env["elite.vet.setting"].nastaveni()
        holiday = holiday_name(day)
        if holiday and s.booking_block_holidays:
            return "Státní svátek: %s – web neobjednává" % holiday
        if day.weekday() >= 5 and s.booking_block_weekends:
            return "Víkend – web neobjednává"
        return None

    # ---------- output ----------
    @api.model
    def _window(self, now, min_hours=None, max_days=None):
        """Booking window. min_hours / max_days = None use the website settings;
        reception passes its own (e.g. min_hours=0 = bookable for today too)."""
        s = self.env["elite.vet.setting"].nastaveni()
        now = now or fields.Datetime.now()
        hours = s.booking_min_hours_before if min_hours is None else min_hours
        days = s.booking_max_days_ahead if max_days is None else max_days
        earliest = now + timedelta(hours=hours)
        latest_day = pytz.utc.localize(now).astimezone(TZ).date() + timedelta(days=days)
        return s, earliest, latest_day

    @api.model
    def slots(self, procedure, day, doctor=None, specialization=None, now=None, min_hours=None, max_days=None,
              rooms=None, scope="web", duration=None):
        """rooms=None = online rooms for the website (rooms_for_booking); reception passes its own.

        scope="web" (default, public API): both block types count as busy and a
        weekend / public holiday (per settings) offers nothing. scope="internal"
        (reception): only full blocks prevent booking. The default is deliberately
        the stricter one so the public API never uses reception rules by mistake.

        duration (minutes) overrides the procedure duration when checking that the
        visit fits; only the reception wizard passes it, the public controller does not.
        """
        s, earliest, latest_day = self._window(now, min_hours, max_days)
        if day > latest_day:
            return []
        if scope == "web" and self.web_day_note(day):
            return []
        if rooms is None:
            rooms = procedure.rooms_for_booking()
        if not rooms:
            return []
        step, dur = s.booking_slot_step, duration or procedure.duration
        need_doctor = self.need_doctor(procedure, doctor, specialization)
        # Assignments are always loaded: doctor_ids in a slot are informative (who is on duty),
        # but they restrict rooms only with an active filter / when a doctor is required.
        assignments = self.assignment_minutes(day, procedure, doctor, specialization)
        busy = self.busy_minutes(rooms.ids, day, scope=scope)
        if scope == "web":
            # Unconfirmed web requests hold their spot so another client cannot book the
            # same time (reception sees them in the panel and books without restriction).
            for room_id, ivs in self.pending_holds(day).items():
                busy.setdefault(room_id, []).extend(ivs)
        # utc_to_local_minutes clamps to 0 / 1440, so a day before `earliest` yields 1440
        # (no slot) and a day after it 0 - no need to compare dates separately.
        earliest_min = self.utc_to_local_minutes(earliest, day)

        by_minute = {}
        for room in rooms:
            free = self.open_minutes(room, day)
            if need_doctor:
                free = intersect(free, [(f, t) for f, t, _d in assignments.get(room.id, [])])
            free = subtract(free, busy.get(room.id, []))
            for f, t in free:
                m = f if f % step == 0 else f + (step - f % step)
                while m + dur <= t:
                    if m >= earliest_min:
                        entry = by_minute.setdefault(m, {"minute": m, "room_ids": [], "doctor_ids": []})
                        # overlapping assignments of two doctors in one room must not duplicate the room
                        if room.id not in entry["room_ids"]:
                            entry["room_ids"].append(room.id)
                        for af, at, did in assignments.get(room.id, []):
                            if af <= m and m + dur <= at and did not in entry["doctor_ids"]:
                                entry["doctor_ids"].append(did)
                    m += step
        out = []
        for m in sorted(by_minute):
            e = by_minute[m]
            e["time"] = "%02d:%02d" % (m // 60, m % 60)
            out.append(e)
        return out

    @api.model
    def pending_holds(self, day, exclude_ids=()):
        """Rooms held on the website by unconfirmed web requests: {room_id: [(from, to)]}.

        A request has no room yet, so it is virtually assigned the room where it
        could be confirmed: the first online room of the procedure that is free at
        that time and (if required) has a doctor on duty who does the procedure.
        Older requests take precedence. A request with no room left holds nothing
        (reception resolves it manually).
        """
        Res = self.env["elite.vet.reservation"].sudo()
        start, stop = self.local_to_utc(day, 0), self.local_to_utc(day, 1440)
        pending = Res.search([("kind", "=", "reservation"), ("state", "=", "web_new"), ("procedure_id", "!=", False),
                              ("start", "<", stop), ("stop", ">", start),
                              ("stop", ">", fields.Datetime.now()), ("id", "not in", list(exclude_ids))],
                             order="create_date, id")
        holds = {}
        if not pending:
            return holds
        all_rooms = self.env["elite.vet.room"].sudo().search([])
        busy = self.busy_minutes(all_rooms.ids, day, scope="web")
        for req in pending:
            proc, doctor = req.procedure_id, req.doctor_id or None
            f, t = self.utc_to_local_minutes(req.start, day), self.utc_to_local_minutes(req.stop, day)
            need = self.need_doctor(proc, doctor)
            assignments = self.assignment_minutes(day, proc, doctor) if need else {}
            for room in proc.rooms_for_booking():
                free = self.open_minutes(room, day)
                if need:
                    free = intersect(free, [(af, at) for af, at, _d in assignments.get(room.id, [])])
                free = subtract(free, busy.get(room.id, []) + holds.get(room.id, []))
                if any(ff <= f and t <= ft for ff, ft in free):
                    holds.setdefault(room.id, []).append((f, t))
                    break
        return holds

    @api.model
    def need_doctor(self, procedure, doctor=None, specialization=None):
        """Must a doctor be on duty in the room? A procedure with a specialization can only
        be booked where a doctor who does it is on duty; likewise with a chosen doctor /
        when a doctor is required by settings."""
        s = self.env["elite.vet.setting"].nastaveni()
        return bool(doctor or specialization or s.booking_require_doctor or procedure.specialization_ids)

    @api.model
    def serving_doctors(self, procedure, day, room_id, minute, doctor=None, serving=None, duration=None):
        """Ids of doctors on duty in the room for the whole procedure starting at `minute`
        who do the procedure (only the chosen one if `doctor` is set), ordered by shift start."""
        if serving is None:
            serving = self.assignment_minutes(day, procedure, doctor)
        out = []
        for f, t, did in sorted(serving.get(room_id, [])):
            if f <= minute and minute + (duration or procedure.duration) <= t and did not in out \
                    and (not doctor or did == doctor.id):
                out.append(did)
        return out

    @api.model
    def room_doctors(self, procedure, day, slot, doctor=None, duration=None):
        """For one slot from slots(): [(room_id, doctor_id | False)] - for each free room
        the doctor on duty there at that time who does the procedure (the chosen one,
        otherwise the first by shift start). A procedure not requiring a doctor may have none."""
        serving = self.assignment_minutes(day, procedure, doctor)
        out = []
        for room_id in slot["room_ids"]:
            doc_ids = self.serving_doctors(procedure, day, room_id, slot["minute"], doctor, serving=serving,
                                           duration=duration)
            out.append((room_id, doc_ids[0] if doc_ids else False))
        return out

    @api.model
    def days(self, procedure, year, month, doctor=None, specialization=None, now=None):
        _s, earliest, latest_day = self._window(now)
        first_allowed = pytz.utc.localize(earliest).astimezone(TZ).date()
        out = []
        for d in range(1, calendar.monthrange(year, month)[1] + 1):
            day = date(year, month, d)
            if day < first_allowed or day > latest_day:
                continue
            if self.slots(procedure, day, doctor, specialization, now=now, scope="web"):
                out.append(day.isoformat())
        return out
