"""Vypocet volnych terminu.

Vsechno se pocita v minutach od pulnoci mistniho (prazskeho) dne. Do UTC se
prevadi az na krajich: pri cteni rezervaci z DB a pri vraceni slotu ven.
Minuty misto floatu, aby 8.25 + 0.25 nedelalo 8.4999.
"""
import calendar
from datetime import date, datetime, timedelta

import pytz

from odoo import api, fields, models

from .reservation import TZ



def to_min(hour_float):
    return int(round(hour_float * 60))


def intersect(a, b):
    """Prunik dvou seznamu intervalu (from, to), oba serazene."""
    out = []
    for af, at in a:
        for bf, bt in b:
            f, t = max(af, bf), min(at, bt)
            if f < t:
                out.append((f, t))
    return sorted(out)


def subtract(a, busy):
    """Odecte obsazene intervaly od volnych."""
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

    # ---------- cas ----------
    @api.model
    def local_to_utc(self, day, minute):
        local = TZ.localize(datetime(day.year, day.month, day.day) + timedelta(minutes=minute))
        return local.astimezone(pytz.utc).replace(tzinfo=None)

    @api.model
    def utc_to_local_minutes(self, dt, day):
        """Minuty od pulnoci `day`; hodnoty mimo den se oriznou na 0 / 1440."""
        local = pytz.utc.localize(dt).astimezone(TZ)
        # Rozdil nastenych hodin (ne skutecne uplynulych minut), aby to bylo
        # presne inverzni k local_to_utc i v dnech s prechodem letni/zimni cas.
        midnight = datetime(day.year, day.month, day.day)
        delta = (local.replace(tzinfo=None) - midnight).total_seconds() / 60
        return max(0, min(1440, int(delta)))

    # ---------- vstupy ----------
    @api.model
    def open_minutes(self, room, day):
        exc = self.env["elite.vet.room.exception"].search([("room_id", "=", room.id), ("date", "=", day)], limit=1)
        if exc:
            return [] if exc.closed else [(to_min(exc.hour_from), to_min(exc.hour_to))]
        lines = room.hours_ids.filtered(lambda h: int(h.weekday) == day.weekday() and h.plati_v_den(day))
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
    def busy_minutes(self, room_ids, day):
        Res = self.env["elite.vet.reservation"]
        start, stop = self.local_to_utc(day, 0), self.local_to_utc(day, 1440)
        out = {rid: [] for rid in room_ids}
        for r in Res.search(Res._busy_domain(room_ids, start, stop)):
            iv = (self.utc_to_local_minutes(r.start, day), self.utc_to_local_minutes(r.stop, day))
            targets = [r.room_id.id] if r.room_id else list(room_ids)
            for rid in targets:
                if rid in out:
                    out[rid].append(iv)
        return out

    # ---------- vystup ----------
    @api.model
    def _window(self, now):
        s = self.env["elite.vet.setting"].nastaveni()
        now = now or fields.Datetime.now()
        earliest = now + timedelta(hours=s.booking_min_hours_before)
        latest_day = pytz.utc.localize(now).astimezone(TZ).date() + timedelta(days=s.booking_max_days_ahead)
        return s, earliest, latest_day

    @api.model
    def slots(self, procedure, day, doctor=None, specialization=None, now=None):
        s, earliest, latest_day = self._window(now)
        if day > latest_day:
            return []
        rooms = procedure.rooms_for_booking()
        if not rooms:
            return []
        step, dur = s.booking_slot_step, procedure.duration
        # Úkon se specializací jde objednat jen tam, kde slouží lékařka, která ho umí.
        need_doctor = bool(doctor or specialization or s.booking_require_doctor or procedure.specialization_ids)
        # Sluzby se nacitaji vzdy: doctor_ids ve slotu jsou informativni (kdo zrovna slouzi),
        # k omezeni ordinaci se ale pouziji jen pri aktivnim filtru / povinnem lekari.
        assignments = self.assignment_minutes(day, procedure, doctor, specialization)
        busy = self.busy_minutes(rooms.ids, day)
        # utc_to_local_minutes orizne na 0 / 1440, takze den pred earliest dava 1440
        # (zadny slot) a den po nem 0 - netreba rozlisovat data zvlast.
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
                        # prekryvajici se sluzby dvou lekaru v jedne ordinaci nesmi ordinaci zdvojit
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
    def days(self, procedure, year, month, doctor=None, specialization=None, now=None):
        _s, earliest, latest_day = self._window(now)
        first_allowed = pytz.utc.localize(earliest).astimezone(TZ).date()
        out = []
        for d in range(1, calendar.monthrange(year, month)[1] + 1):
            day = date(year, month, d)
            if day < first_allowed or day > latest_day:
                continue
            if self.slots(procedure, day, doctor, specialization, now=now):
                out.append(day.isoformat())
        return out
