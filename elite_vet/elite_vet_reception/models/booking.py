"""Booking tab of the reception in the POS: free times and a confirmed reservation.

Everything goes through the reservation wizard (`elite.vet.reservation.wizard`) so the
times are the same as on the board and the save follows the same rules (doctor on duty,
confirmation e-mail when the owner has an e-mail, overlap check). The wizard runs with the
caller's own rights - reception books reservations in the backend the same way.
"""
from datetime import timedelta

from odoo import _, api, models
from odoo.exceptions import UserError, ValidationError

from odoo.addons.elite_vet_clinic.models.patient_card import clinic_today
from odoo.addons.elite_vet_reservation.models.reservation import RECEPTION_HORIZON_DAYS, minutes_label


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
