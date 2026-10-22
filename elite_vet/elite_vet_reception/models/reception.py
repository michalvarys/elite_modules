"""JSON API of the reception in the POS (`orm.call("elite.vet.reception", "<method>", [args])`).

Every method checks that the caller has the reception group (nurse, doctor and manager pass
through implied groups) and only then works under sudo: reception may create a visit record,
but has no write access to the record itself. Shapes are documented in README.md.
"""
from datetime import date as date_type

import psycopg2

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError

from odoo.addons.elite_vet_clinic.models.clinical_record import local_date
from odoo.addons.elite_vet_clinic.models.patient_card import clinic_today, date_str, local_time
from odoo.addons.elite_vet_reservation.models.live import notify_board
from odoo.addons.elite_vet_sale.models.clinical_record import PAYMENT_STATES

from .clinical_record import RECEPTION_CONTEXT, VISIT_STAGES

RECEPTION_GROUP = "elite_vet_reservation.group_reservation_reception"
NURSE_GROUP = "elite_vet_clinic.group_clinic_nurse"
TO_PAY_STATES = ("waiting", "partial")


class Reception(models.AbstractModel):
    _name = "elite.vet.reception"
    _description = "Recepce – API pokladny"

    # ------------------------------------------------------------------ helpers

    @api.model
    def _check_reception(self):
        if not self.env.user.has_group(RECEPTION_GROUP):
            raise AccessError(_("Tuto akci může provést jen recepce, sestra, lékařka nebo vedení."))

    @api.model
    def _check_bookable_pet(self, pet):
        """Ruling R8: no booking and no walk-in for a deceased pet."""
        if pet.deceased:
            raise UserError(_("Zvíře je vedené jako uhynulé."))

    @api.model
    def _records(self):
        """Clinical records under sudo, with the reception API flag for the clinic write check."""
        return self.env["elite.vet.clinical.record"].sudo().with_context(**{RECEPTION_CONTEXT: True})

    @api.model
    def _day(self, day):
        if not day:
            return clinic_today()
        if isinstance(day, date_type):
            return day
        try:
            return fields.Date.to_date(day)
        except ValueError as err:
            raise UserError(_("Neplatné datum: %s") % day) from err

    @api.model
    def _record_dict(self, record):
        return {
            "record_id": record.id, "stage": record.visit_stage or None,
            "stage_label": dict(VISIT_STAGES).get(record.visit_stage), "state": record.state,
            "pet_id": record.pet_id.id, "pet_name": record.pet_id.name,
            "reservation_id": record.reservation_id.id or None,
            "doctor": record.doctor_id.name or None, "arrived_time": local_time(record.arrived_at),
            "received_by": record.received_by or None,
        }

    @api.model
    def _mark_arrived(self, record, employee_name):
        """A record without a stage becomes waiting; an in_room record keeps its stage."""
        vals = {}
        if not record.visit_stage and record.state == "draft":
            vals["visit_stage"] = "waiting"
        if not record.arrived_at:
            vals["arrived_at"] = fields.Datetime.now()
        if employee_name and not record.received_by:
            vals["received_by"] = employee_name
        if vals:
            record.write(vals)

    @api.model
    def _amount_to_pay(self, record):
        order = record.sale_order_id.sudo()
        if record.payment_state == "partial":
            unlinked = record._paid_pos_lines().filtered(lambda l: not l.sale_order_line_id)
            return order.amount_unpaid - sum(unlinked.mapped("price_subtotal_incl"))
        return order.amount_total

    # ------------------------------------------------------------------ read API

    @api.model
    def today_data(self, day=None):
        self._check_reception()
        day = self._day(day)
        A = self.env["elite.vet.availability"]
        Reservation = self.env["elite.vet.reservation"].sudo()
        Records = self._records()
        lang = Reservation._clinic_lang()
        now = fields.Datetime.now()

        reservations = Reservation.search([
            ("kind", "=", "reservation"), ("state", "=", "confirmed"), ("is_second_room", "=", False),
            ("start", ">=", A.local_to_utc(day, 0)), ("start", "<", A.local_to_utc(day, 1440))],
            order="start, id")
        with_record = set(Records.search([("reservation_id", "in", reservations.ids),
                                          ("state", "!=", "cancelled")]).reservation_id.ids)
        arriving = []
        for res in reservations.filtered(lambda r: r.id not in with_record):
            arriving.append({
                "reservation_id": res.id, "time": local_time(res.start), "pet_id": res.pet_id.id or None,
                "pet_name": res.pet_id.name or res.pet_name or None,
                "owner": res.partner_id.name or res.contact_name or None, "partner_id": res.partner_id.id or None,
                "procedure": res.procedure_id.with_context(lang=lang).name or None,
                "doctor": res.doctor_id.name or None, "room": res.room_id.name or None,
                "needs_match": not res.pet_id,
            })

        records = Records.search([("date", "=", day), ("state", "!=", "cancelled")])
        waiting = []
        stage_records = records.filtered(lambda r: r.state == "draft" and r.visit_stage)
        for rec in stage_records.sorted(lambda r: (r.arrived_at or r.start, r.id)):
            res = rec.reservation_id
            since = rec.arrived_at
            until = rec.called_at if rec.visit_stage == "in_room" and rec.called_at else now
            waiting.append({
                "record_id": rec.id, "pet_name": rec.pet_id.name, "owner": rec.partner_id.name or None,
                "doctor": (rec.doctor_id or res.doctor_id).name or None, "room": res.room_id.name or None,
                "stage": rec.visit_stage, "stage_label": dict(VISIT_STAGES)[rec.visit_stage],
                "arrived_time": local_time(since),
                "waiting_minutes": max(0, int((until - since).total_seconds() // 60)) if since else None,
            })

        paid_count = len(records.filtered(lambda r: r.state == "done" and r.payment_state == "paid"))
        return {"date": date_str(day), "arriving": arriving, "waiting": waiting, "to_pay": self._to_pay(),
                "paid_count": paid_count}

    @api.model
    def _to_pay(self, partner=None):
        """Unpaid visit bills of any day (waiting / partially paid), oldest first;
        with `partner` only the bills of that owner."""
        today = clinic_today()
        labels = dict(PAYMENT_STATES)
        domain = [("state", "=", "done"), ("sale_order_id", "!=", False), ("sale_order_id.state", "!=", "cancel")]
        if partner is not None:
            domain.append(("partner_id", "=", partner.id))
        candidates = self._records().search(domain, order="start, id")
        to_pay = []
        for rec in candidates:
            state = rec.payment_state
            if state not in TO_PAY_STATES:
                continue
            to_pay.append({
                "record_id": rec.id, "sale_order_id": rec.sale_order_id.id, "pet_name": rec.pet_id.name,
                "owner": rec.partner_id.name or None, "partner_id": rec.partner_id.id or None,
                "amount": self._amount_to_pay(rec), "payment_state": state,
                "payment_state_label": labels[state], "date": date_str(rec.date),
                "date_label": "dnes" if rec.date == today else "%d. %d." % (rec.date.day, rec.date.month),
            })
        return to_pay

    # ------------------------------------------------------------------ write API

    @api.model
    def check_in(self, reservation_id, employee_name=None):
        """The client of a reservation arrived: its record (existing or new) is waiting."""
        self._check_reception()
        reservation = self.env["elite.vet.reservation"].sudo().browse(int(reservation_id)).exists()
        if not reservation or reservation.kind != "reservation":
            raise UserError(_("Rezervace nebyla nalezena."))
        if reservation.state == "done":
            raise UserError(_("Proběhlou rezervaci nelze znovu přijmout."))
        if reservation.state != "confirmed":
            raise UserError(_("Přijmout lze jen potvrzenou rezervaci."))
        if local_date(reservation.start) != clinic_today():
            raise UserError(_("Rezervace není na dnešek – přijmout jde jen dnešní návštěvu."))
        if not reservation.pet_id:
            raise UserError(_("Rezervace z webu ještě není spárovaná s klientem a zvířetem – otevřete Kartotéku."))
        Records = self._records()
        own = Records.search([("reservation_id", "=", reservation.id)], limit=1)
        if own and own.state == "cancelled":
            own.reservation_id = False  # a cancelled visit must not block a new one (unique reservation)
            own = Records.browse()
        if own:
            record = own
        else:
            candidate = Records._today_record(reservation.pet_id, reservation)
            force_new = not candidate or candidate.state != "draft"
            try:
                with self.env.cr.savepoint():
                    data = Records.open_today_record(reservation.pet_id.id, reservation.id, force_new=force_new)
            except psycopg2.IntegrityError:
                # Concurrent check-in (two tills): the other one created the reservation's record.
                self.env.invalidate_all()
                record = Records.search([("reservation_id", "=", reservation.id)], limit=1)
                if not record:
                    raise
            else:
                record = Records.browse(data["id"])
                if force_new:
                    record.doctor_id = reservation.doctor_id
        self._mark_arrived(record, employee_name)
        notify_board(self.env)
        return self._record_dict(record)

    @api.model
    def walk_in(self, pet_id, doctor_id=False, employee_name=None):
        """A client without a reservation: today's open record of the pet, else a new draft."""
        self._check_reception()
        Records = self._records()
        pet = Records._get_pet(pet_id)
        self._check_bookable_pet(pet)
        doctor = self.env["elite.vet.doctor"].sudo().browse(int(doctor_id)).exists() if doctor_id \
            else self.env["elite.vet.doctor"]
        record = Records.search([("pet_id", "=", pet.id), ("date", "=", clinic_today()), ("state", "=", "draft")],
                                order="start desc, id desc", limit=1)
        if record:
            if doctor and not record.doctor_id:
                record.doctor_id = doctor
        else:
            data = Records.open_today_record(pet.id, force_new=True)
            record = Records.browse(data["id"])
            record.doctor_id = doctor
        self._mark_arrived(record, employee_name)
        notify_board(self.env)
        return self._record_dict(record)

    @api.model
    def call_patient(self, record_id):
        """Doctor or nurse calls the patient from the waiting room into the room."""
        self._check_reception()
        if not self.env.user.has_group(NURSE_GROUP):
            raise AccessError(_("Pacienta může zavolat jen sestra nebo lékařka."))
        record = self.env["elite.vet.clinical.record"].browse(int(record_id)).exists()
        if not record:
            raise UserError(_("Záznam návštěvy nebyl nalezen."))
        if record.state != "draft":
            raise UserError(_("Návštěva je už uzavřená."))
        if not record.doctor_id:
            # Ruling R17: an unassigned walk-in is taken by the doctor who calls it in
            doctor = record._doctor_for_user()
            if doctor:
                record.doctor_id = doctor
        if record.visit_stage != "in_room":
            record.write({"visit_stage": "in_room", "called_at": fields.Datetime.now()})
        notify_board(self.env)
        return self._record_dict(record)
