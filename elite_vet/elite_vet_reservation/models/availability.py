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
from .holidays import holiday_name


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
        """Obsazené minuty po ordinacích; scope viz elite.vet.reservation._busy_domain."""
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
        """Proč web v tento den neobjednává (víkend / státní svátek dle nastavení), jinak None.

        Platí jen pro web; recepce v takový den objednává normálně. Nic se
        nezakládá - počítá se z data a nastavení.
        """
        s = self.env["elite.vet.setting"].nastaveni()
        nazev = holiday_name(day)
        if nazev and s.booking_block_holidays:
            return "Státní svátek: %s – web neobjednává" % nazev
        if day.weekday() >= 5 and s.booking_block_weekends:
            return "Víkend – web neobjednává"
        return None

    # ---------- vystup ----------
    @api.model
    def _window(self, now, min_hours=None, max_days=None):
        """Okno, ve kterém se dá objednat. min_hours / max_days = None bere nastavení
        pro web; recepce si předá vlastní (např. min_hours=0 = i na dnešek)."""
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
        """rooms=None = online ordinace pro web (rooms_for_booking); recepce předá vlastní.

        scope="web" (výchozí, veřejné API): obsazené jsou obě blokace a víkend /
        státní svátek (podle nastavení) nenabídne nic. scope="internal" (recepce):
        brání jen úplná blokace. Výchozí hodnota je schválně ta přísnější, aby
        veřejné API omylem nepoužilo pravidla recepce.

        duration (minuty) přebije délku úkonu pro kontrolu, že se návštěva vejde; předává
        ji jen průvodce recepce, veřejný kontroler ne.
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
        # Sluzby se nacitaji vzdy: doctor_ids ve slotu jsou informativni (kdo zrovna slouzi),
        # k omezeni ordinaci se ale pouziji jen pri aktivnim filtru / povinnem lekari.
        assignments = self.assignment_minutes(day, procedure, doctor, specialization)
        busy = self.busy_minutes(rooms.ids, day, scope=scope)
        if scope == "web":
            # Nepotvrzené žádosti z webu drží místo, aby se na stejný čas nepřihlásil
            # další klient (recepce je vidí v panelu a objednává dál bez omezení).
            for room_id, ivs in self.pending_holds(day).items():
                busy.setdefault(room_id, []).extend(ivs)
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
    def pending_holds(self, day, exclude_ids=()):
        """Ordinace, které na webu drží nepotvrzené žádosti z webu: {room_id: [(od, do)]}.

        Žádost ordinaci ještě nemá, proto se jí „v duchu“ přidělí ta, kam by ji šlo
        potvrdit: první online ordinace úkonu, kde je v tu dobu volno a (je-li
        potřeba) slouží lékařka, která úkon dělá. Starší žádost má přednost. Žádost,
        pro kterou místo nezbylo, nedrží nic (recepce ji vyřeší ručně).
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
        """Musí v ordinaci sloužit lékařka? Úkon se specializací jde objednat jen tam,
        kde slouží lékařka, která ho umí; stejně tak při zvolené lékařce / povinném lékaři."""
        s = self.env["elite.vet.setting"].nastaveni()
        return bool(doctor or specialization or s.booking_require_doctor or procedure.specialization_ids)

    @api.model
    def serving_doctors(self, procedure, day, room_id, minute, doctor=None, serving=None, duration=None):
        """Id lékařek, které v ordinaci po celou dobu úkonu od `minute` slouží a úkon
        dělají (jen zvolená, je-li `doctor`), seřazené podle začátku služby."""
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
        """Pro jeden slot ze slots(): [(room_id, doctor_id | False)] – v každé volné
        ordinaci lékařka, která tam v tu dobu slouží a úkon dělá (zvolená, jinak
        první podle začátku služby). Úkon bez nutné lékařky může být bez ní."""
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
