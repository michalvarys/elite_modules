"""Screen Ordinace (task 15): one account per consultation room, the visits of the day split by
room. API of `elite.vet.reception` (same role check as the rest of it); shapes in README.md.

- room_board(day=None): columns Nepřiřazení + one per room, each with the sections
  in_room / waiting / booked / done and the doctors on duty now (elite.vet.doctor.assignment).
- assign_room(record_id, room_id|False, doctor_id=False): moves today's draft visit to a room
  (False = back to Nepřiřazení). The reservation keeps its room.

Doctor of the visit (rule 3): a record without a doctor that gets a room (assigning, Zavolat)
takes the doctor on duty in that room now; two on duty -> `needs_doctor` (the client asks),
none -> stays empty. A doctor already on the record is kept.
"""
from datetime import datetime

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from odoo.addons.elite_vet_clinic.models.patient_card import clinic_today, date_str, local_time
from odoo.addons.elite_vet_reservation.models.live import notify_board
from odoo.addons.elite_vet_reservation.models.reservation import TZ
from odoo.addons.elite_vet_reservation.models.room import format_hour

from .booking import natural_key
from .clinical_record import VISIT_STAGES

NURSE_GROUP = "elite_vet_clinic.group_clinic_nurse"
ROOM_SECTIONS = ("in_room", "waiting", "booked", "done")
UNASSIGNED_LABEL = "Nepřiřazení"


class ReceptionRooms(models.AbstractModel):
    _inherit = "elite.vet.reception"

    # ------------------------------------------------------------------ helpers

    @api.model
    def _clinic_hour_now(self):
        """Current hour in the clinic as a float (8.5 = 8:30); patched in tests."""
        now = datetime.now(TZ)
        return now.hour + now.minute / 60.0

    @api.model
    def _get_room(self, room_id):
        if not room_id:
            return self.env["elite.vet.room"]
        room = self.env["elite.vet.room"].with_context(active_test=False).browse(int(room_id)).exists()
        if not room:
            raise UserError(_("Ordinace nebyla nalezena."))
        return room

    @api.model
    def _get_doctor(self, doctor_id):
        if not doctor_id:
            return self.env["elite.vet.doctor"]
        doctor = self.env["elite.vet.doctor"].browse(int(doctor_id)).exists()
        if not doctor:
            raise UserError(_("Lékařka nebyla nalezena."))
        return doctor

    @api.model
    def _room_shifts(self, rooms, day):
        """Doctor assignments of the day in the rooms, by start."""
        return self.env["elite.vet.doctor.assignment"].search(
            [("date", "=", day), ("room_id", "in", rooms.ids)], order="hour_from, id")

    @api.model
    def _on_duty_doctors(self, room, day=None, shifts=None):
        """Doctors on duty in the room now: today's assignments with hour_from <= now < hour_to.
        Another day than today has nobody "now"."""
        doctors = self.env["elite.vet.doctor"]
        day = day or clinic_today()
        if not room or day != clinic_today():
            return doctors
        hour = self._clinic_hour_now()
        if shifts is None:
            shifts = self._room_shifts(room, day)
        for shift in shifts:
            if shift.room_id == room and shift.hour_from <= hour < shift.hour_to:
                doctors |= shift.doctor_id
        return doctors

    @api.model
    def _set_room(self, record, room, doctor=None):
        """Room (and doctor) of a visit; returns the doctors to choose from ([] = nothing to ask).
        `doctor` given: it becomes the doctor. Otherwise a record without a doctor gets the one on
        duty in the room; with two on duty the user's own doctor (matched by name) is taken if she
        is one of them, else the client asks."""
        vals = {}
        if record.room_id != room:
            vals["room_id"] = room.id or False
        needs_doctor = []
        if doctor:
            if record.doctor_id != doctor:
                vals["doctor_id"] = doctor.id
        elif room and not record.doctor_id:
            on_duty = self._on_duty_doctors(room)
            if len(on_duty) > 1:
                own = record._doctor_for_user() & on_duty
                on_duty = own or on_duty
            if len(on_duty) == 1:
                vals["doctor_id"] = on_duty.id
            elif on_duty:
                needs_doctor = [{"id": d.id, "name": d.name} for d in on_duty]
        if vals:
            record.write(vals)
        return needs_doctor

    # ------------------------------------------------------------------ write API

    @api.model
    def assign_room(self, record_id, room_id=False, doctor_id=False):
        """Today's draft visit into a room (room_id False = Nepřiřazení)."""
        self._check_reception()
        record = self._records().browse(int(record_id)).exists()
        if not record:
            raise UserError(_("Záznam návštěvy nebyl nalezen."))
        if record.date != clinic_today() or record.state != "draft":
            raise UserError(_("Do ordinace jde přiřadit jen dnešní rozepsanou návštěvu."))
        needs_doctor = self._set_room(record, self._get_room(room_id), self._get_doctor(doctor_id))
        notify_board(self.env)
        return dict(self._record_dict(record), needs_doctor=needs_doctor)

    # ------------------------------------------------------------------ read API

    @api.model
    def room_board(self, day=None):
        """Data of the screen Ordinace (both views): see README.md."""
        self._check_reception()
        day = self._day(day)
        is_today = day == clinic_today()
        A = self.env["elite.vet.availability"]
        Reservation = self.env["elite.vet.reservation"].sudo()
        Records = self._records()
        lang = Reservation._clinic_lang()
        now = fields.Datetime.now()

        records = Records.search([("date", "=", day), ("state", "!=", "cancelled")])
        reservations = Reservation.search([
            ("kind", "=", "reservation"), ("state", "=", "confirmed"), ("is_second_room", "=", False),
            ("start", ">=", A.local_to_utc(day, 0)), ("start", "<", A.local_to_utc(day, 1440))],
            order="start, id")
        with_record = set(records.reservation_id.ids)
        rooms = self.env["elite.vet.room"].search([])
        rooms |= (records.room_id | reservations.room_id).filtered(lambda r: r not in rooms)
        rooms = rooms.sorted(lambda r: (r.sequence, natural_key(r.name), r.id))   # "Ordinace 9" before "10"
        shifts = self._room_shifts(rooms, day)

        sections = {room_id: {key: [] for key in ROOM_SECTIONS} for room_id in [False] + rooms.ids}
        for rec in records:
            if rec.state == "done":
                section = "done"
            elif rec.visit_stage:
                section = rec.visit_stage
            else:
                section = "booked"   # a draft opened before the client arrived
            sections[rec.room_id.id or False][section].append(
                self._room_item(rec, rec.reservation_id.sudo(), now, lang, is_today))
        for res in reservations.filtered(lambda r: r.id not in with_record):
            sections[res.room_id.id or False]["booked"].append(
                self._room_item(Records.browse(), res, now, lang, is_today))
        for parts in sections.values():
            for key, items in parts.items():
                items.sort(key=lambda i: (i["sort"] or "", i["key"]))

        hour = self._clinic_hour_now() if is_today else None
        columns = [self._room_column(None, sections[False], [], [])]
        for room in rooms:
            room_shifts = shifts.filtered(lambda s: s.room_id == room)
            on_duty = self._on_duty_doctors(room, day, room_shifts)
            columns.append(self._room_column(room, sections[room.id], room_shifts, on_duty, hour))
        user = self.env.user
        return {
            "date": date_str(day), "is_today": is_today, "time": local_time(now),
            "columns": columns,
            "rooms": [{"id": r.id, "name": r.name, "color": r.color_hex} for r in rooms],
            "perms": {"can_call": user.has_group(NURSE_GROUP),
                      "user_room_id": user.sudo().elite_vet_room_id.id or None},
        }

    @api.model
    def _room_column(self, room, sections, shifts, on_duty, hour=None):
        return {
            "key": "room-%d" % room.id if room else "unassigned",
            "room_id": room.id if room else None,
            "name": room.name if room else UNASSIGNED_LABEL,
            "color": room.color_hex if room else None,
            "on_duty": [{"id": d.id, "name": d.name} for d in on_duty],
            "shifts": [{
                "doctor": s.doctor_id.name, "label": "%s–%s" % (format_hour(s.hour_from), format_hour(s.hour_to)),
                "now": hour is not None and s.hour_from <= hour < s.hour_to,
            } for s in shifts],
            "sections": sections,
            "counts": {key: len(items) for key, items in sections.items()},
        }

    @api.model
    def _room_item(self, rec, res, now, lang, is_today):
        """Card of the screen Ordinace: a visit record and/or its reservation (either may be empty)."""
        pet = rec.pet_id or res.pet_id
        partner = rec.partner_id or res.partner_id
        if rec.state == "done":
            stage = "done"
        elif rec.visit_stage:
            stage = rec.visit_stage
        else:
            stage = "booked"
        since = rec.arrived_at
        until = rec.called_at if stage == "in_room" and rec.called_at else now
        sort_at = {"in_room": rec.called_at or since, "waiting": since}.get(stage) or res.start or rec.start
        return {
            "key": "r%d" % rec.id if rec else "b%d" % res.id,
            "record_id": rec.id or None, "reservation_id": res.id or None,
            "walk_in": not res, "stage": stage, "stage_label": dict(VISIT_STAGES).get(stage),
            "time": local_time(since or res.start or rec.start),
            "reservation_time": local_time(res.start),
            "arrived_time": local_time(since),
            "called_time": local_time(rec.called_at),
            "waiting_minutes": max(0, int((until - since).total_seconds() // 60))
            if since and stage in ("waiting", "in_room") else None,
            "pet_id": pet.id or None, "pet_name": pet.name or res.pet_name or None,
            "species_label": self._records()._species_label(pet) if pet else None,
            "owner": partner.name or res.contact_name or None, "partner_id": partner.id or None,
            "procedure": res.procedure_id.with_context(lang=lang).name or None,
            "doctor": (rec.doctor_id or res.doctor_id).name or None,
            "doctor_id": rec.doctor_id.id or None,
            "room_id": (rec.room_id or res.room_id).id or None,
            "alerts": pet.alert_summary or None,
            "reception_note": rec.reception_note or None,
            "draggable": bool(is_today and rec.state == "draft" and rec.visit_stage),
            "sort": sort_at.strftime("%Y-%m-%d %H:%M:%S") if sort_at else None,
        }
