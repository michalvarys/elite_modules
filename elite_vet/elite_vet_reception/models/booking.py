"""Booking tab of the reception in the POS: free times and a confirmed reservation.

Everything goes through the reservation wizard (`elite.vet.reservation.wizard`) so the
times are the same as on the board and the save follows the same rules (doctor on duty,
confirmation e-mail when the owner has an e-mail, overlap check). The wizard runs with the
caller's own rights - reception books reservations in the backend the same way.
"""
import re
from datetime import timedelta

from odoo import _, api, models
from odoo.exceptions import UserError, ValidationError

from odoo.addons.elite_vet_clinic.models.patient_card import clinic_today
from odoo.addons.elite_vet_reservation.models.availability import intersect, subtract
from odoo.addons.elite_vet_reservation.models.reservation import RECEPTION_HORIZON_DAYS, minutes_label

FREQUENT_COUNT = 6
FREQUENT_DAYS = 30


def natural_key(name):
    """Sort key for names with numbers ("Ordinace 2" before "Ordinace 10"), like the screen's
    `localeCompare(..., {numeric: true})`."""
    return [(0, int(part), "") if part.isdigit() else (1, 0, part.casefold())
            for part in re.split(r"(\d+)", name or "") if part]


class ReceptionBooking(models.AbstractModel):
    _inherit = "elite.vet.reception"

    # ------------------------------------------------------------------ helpers

    @api.model
    def _get_procedure(self, procedure_id):
        procedure = self.env["elite.vet.procedure"].browse(self._to_id(procedure_id)).exists()
        if not procedure:
            raise UserError(_("Úkon nebyl nalezen."))
        return procedure

    @api.model
    def _booking_wizard(self, procedure, day, doctor_id=False, **vals):
        doctor = self.env["elite.vet.doctor"].browse(self._to_id(doctor_id)).exists() if doctor_id else False
        if doctor_id and not doctor:
            raise UserError(_("Lékařka nebyla nalezena."))
        values = {"procedure_id": procedure.id, "date": day, "doctor_id": doctor.id if doctor else False}
        values.update(vals)
        return self.env["elite.vet.reservation.wizard"].create(values)

    @api.model
    def _horizon(self):
        """Last day the wizard offers times for (same window as `availability.slots`)."""
        return clinic_today() + timedelta(days=RECEPTION_HORIZON_DAYS)

    @api.model
    def _next_free_day(self, wizard, day):
        """The wizard's "next free day" search after `day`, up to the horizon; None when
        nothing is free."""
        horizon = self._horizon()
        while day < horizon:
            day += timedelta(days=1)
            if wizard._free_slots(day):
                return day.isoformat()
        return None

    @api.model
    def _frequent_procedures(self, procedures):
        """Up to FREQUENT_COUNT of `procedures` with the most reservations (not cancelled, second
        room copies not counted) of the last FREQUENT_DAYS days up to today; without any such
        reservation the first procedures in their normal order."""
        A = self.env["elite.vet.availability"]
        today = clinic_today()
        groups = self.env["elite.vet.reservation"]._read_group([
            ("kind", "=", "reservation"), ("state", "!=", "cancelled"), ("is_second_room", "=", False),
            ("procedure_id", "in", procedures.ids),
            ("start", ">=", A.local_to_utc(today - timedelta(days=FREQUENT_DAYS), 0)),
            ("start", "<", A.local_to_utc(today + timedelta(days=1), 0)),
        ], ["procedure_id"], ["__count"])
        if not groups:
            return procedures[:FREQUENT_COUNT].ids
        order = {p.id: index for index, p in enumerate(procedures)}
        ranked = sorted(groups, key=lambda g: (-g[1], order[g[0].id]))
        return [procedure.id for procedure, _count in ranked[:FREQUENT_COUNT]]

    @api.model
    def _day_closed(self, wizard, day):
        """The day cannot have any free time for the wizard's procedure whatever is booked: no
        opening hours in its reception rooms, a full block over them, or - when a doctor is
        needed (setting, specialization, the doctor filter) - no shift of a doctor doing it.
        Same inputs as `availability.slots` without the reservations."""
        A = self.env["elite.vet.availability"]
        Res = self.env["elite.vet.reservation"]
        procedure, doctor = wizard.procedure_id, wizard.doctor_id or None
        rooms = procedure.rooms_for_reception()
        if not rooms:
            return True
        settings = self.env["elite.vet.setting"].nastaveni()
        step, duration = settings.booking_slot_step, wizard._effective_duration()
        need_doctor = A.need_doctor(procedure, doctor)
        assignments = A.assignment_minutes(day, procedure, doctor) if need_doctor else {}
        start, stop = A.local_to_utc(day, 0), A.local_to_utc(day, 1440)
        blocks = Res.search(Res._busy_domain(rooms.ids, start, stop, scope="internal") + [("kind", "=", "block")])
        for room in rooms:
            free = A.open_minutes(room, day)
            if need_doctor:
                free = intersect(free, [(f, t) for f, t, _d in assignments.get(room.id, [])])
            busy = [(A.utc_to_local_minutes(b.start, day), A.utc_to_local_minutes(b.stop, day))
                    for b in blocks if not b.room_id or b.room_id == room]
            for f, t in subtract(free, busy):
                first = f if f % step == 0 else f + (step - f % step)
                if first + duration <= t:
                    return False
        return True

    @api.model
    def _taken_error(self, minute):
        return UserError(_("Termín %s už mezitím někdo obsadil – vyberte jiný.") % minutes_label(minute))

    # ------------------------------------------------------------------ API

    @api.model
    def booking_options(self):
        self._check_reception()
        lang = self.env["elite.vet.reservation"]._clinic_lang()
        procedures = self.env["elite.vet.procedure"].with_context(lang=lang).search([])
        doctors = self.env["elite.vet.doctor"].search([("accepts_bookings", "=", True)])
        return {
            "procedures": [{"id": p.id, "name": p.name, "duration": p.duration} for p in procedures],
            "doctors": [{"id": d.id, "name": d.name} for d in doctors],
            # rooms of the walk-in check-in (optional, task 15)
            "rooms": [{"id": r.id, "name": r.name} for r in self.env["elite.vet.room"].search([])],
            # ids of the frequent procedures (big buttons of step Úkon), most booked first
            "frequent": self._frequent_procedures(procedures),
        }

    @api.model
    def free_slots(self, procedure_id, day, doctor_id=False):
        self._check_reception()
        procedure = self._get_procedure(procedure_id)
        day = self._day(day)
        if day > self._horizon():
            return {"day": day.isoformat(), "slots": [], "next_free_day": None}
        wizard = self._booking_wizard(procedure, day, doctor_id)
        wizard._load_slots()
        slots = [{
            "time": line.time_label, "minute": line.minute,
            "room_id": line.room_id.id, "room": line.room_id.name,
            "doctor_id": line.doctor_id.id or False, "doctor": line.doctor_id.name or None,
        } for line in wizard.slot_ids]
        # the next free day is searched only when the day itself has nothing (it is costly)
        next_free_day = None if slots else self._next_free_day(wizard, day)
        return {"day": day.isoformat(), "slots": slots, "next_free_day": next_free_day}

    @api.model
    def nearest_free(self, procedure_id, doctor_id=False):
        """The earliest free time from now within the reception horizon (the wizard's lines, as
        `free_slots`): {day, time, minute, room_id, room, doctor_id, doctor}; None when nothing
        is free. Of several rooms free at that minute the first in natural name order (as the
        screen lists them)."""
        self._check_reception()
        procedure = self._get_procedure(procedure_id)
        day, horizon = clinic_today(), self._horizon()
        wizard = self._booking_wizard(procedure, day, doctor_id)
        while day <= horizon:
            if wizard._free_slots(day):
                wizard.date = day
                wizard._load_slots()
                lines = wizard.slot_ids
                if lines:
                    first = min(lines.mapped("minute"))
                    line = sorted(lines.filtered(lambda ln: ln.minute == first),
                                  key=lambda ln: natural_key(ln.room_id.name))[0]
                    return {
                        "day": day.isoformat(), "time": line.time_label, "minute": line.minute,
                        "room_id": line.room_id.id, "room": line.room_id.name,
                        "doctor_id": line.doctor_id.id or False, "doctor": line.doctor_id.name or None,
                    }
            day += timedelta(days=1)
        return None

    @api.model
    def free_days(self, procedure_id, day, doctor_id=False, days=7):
        """Number of free times on `days` days from `day` (the day strip of Objednat).

        `count` is the number of distinct free times of the day (as the wizard offers them);
        None for a past day or a day beyond the horizon (nothing can be booked there).
        `closed` is True for a bookable day that cannot have a free time whatever is booked
        (no opening hours, a full block, no doctor's shift when one is needed): "zavřeno" on the
        screen, "nic volného" is an open but fully booked day.
        """
        self._check_reception()
        procedure = self._get_procedure(procedure_id)
        start = self._day(day)
        today, horizon = clinic_today(), self._horizon()
        wizard = self._booking_wizard(procedure, start, doctor_id)
        result = []
        for offset in range(max(1, min(int(days), 14))):
            current = start + timedelta(days=offset)
            bookable = today <= current <= horizon
            count = len(wizard._free_slots(current)) if bookable else None
            result.append({"day": current.isoformat(), "count": count,
                           "closed": bool(bookable and not count and self._day_closed(wizard, current))})
        return result

    @api.model
    def book(self, pet_id, procedure_id, day, minute, room_id, doctor_id=False, note=None):
        self._check_reception()
        pet = self.env["elite.vet.pet"].browse(self._to_id(pet_id)).exists()
        if not pet:
            raise UserError(_("Zvíře nebylo nalezeno."))
        self._check_bookable_pet(pet)
        partner = self._get_owner(pet.partner_id.id)  # the card index owner rule (no staff / company)
        procedure = self._get_procedure(procedure_id)
        day = self._day(day)
        minute = self._to_id(minute)
        room = self.env["elite.vet.room"].browse(self._to_id(room_id)).exists()
        if not room:
            raise UserError(_("Ordinace nebyla nalezena."))
        wizard = self._booking_wizard(procedure, day, doctor_id, minute=minute, room_id=room.id,
                                      partner_mode="existing", partner_id=partner.id, pet_id=pet.id,
                                      note=(note or "").strip() or False)
        # Still free? (another till may have booked it since the list was loaded)
        room_doctor = wizard._free_room_doctor()
        if not room_doctor:
            raise self._taken_error(minute)
        wizard.slot_doctor_id = room_doctor[1] or wizard.doctor_id.id
        try:
            with self.env.cr.savepoint():
                wizard.action_save()
        except ValidationError:
            # The reservation's overlap check has the final say.
            if wizard._collision(room, minute):
                raise self._taken_error(minute) from None
            raise
        A = self.env["elite.vet.availability"]
        reservation = self.env["elite.vet.reservation"].search([
            ("kind", "=", "reservation"), ("state", "=", "confirmed"), ("room_id", "=", room.id),
            ("start", "=", A.local_to_utc(day, minute)), ("partner_id", "=", partner.id)],
            order="id desc", limit=1)
        if not reservation:
            raise UserError(_("Rezervaci se nepodařilo uložit – zkuste to prosím znovu."))
        return {
            "reservation_id": reservation.id,
            "label": "%s %s, %s" % (wizard.day_label, minutes_label(minute), room.name),
        }
