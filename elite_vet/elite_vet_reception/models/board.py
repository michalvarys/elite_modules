"""Reservation board inside the POS ("Tabule"): detail of a board event and its actions.

The day itself is read with `elite.vet.reservation.board_data` (same data as the backend board,
with the payment state from elite_vet_sale). These methods add what the till needs on top of it:
the client / pet ids and the visit of one reservation, and the move, cancel and Nedorazil actions
with the role check. Moving goes through the board's own `board_move` (same doctor and room rules, overlap
check on write) and cancelling through `action_cancel` (same e-mail rule as in the backend) - both
with the caller's own rights, reception edits reservations in the backend the same way.
"""
from odoo import _, api, models
from odoo.exceptions import UserError

from odoo.addons.elite_vet_clinic.models.clinical_record import local_date
from odoo.addons.elite_vet_clinic.models.patient_card import clinic_today, date_str, local_time
from odoo.addons.elite_vet_reservation.models.reservation import STATES, WEEKDAY_ABBR
from odoo.addons.elite_vet_sale.models.clinical_record import PAYMENT_STATES

from .clinical_record import VISIT_STAGES

MOVABLE_STATES = ("confirmed",)
CANCELLABLE_STATES = ("web_new", "confirmed")


class ReceptionBoard(models.AbstractModel):
    _inherit = "elite.vet.reception"

    # ------------------------------------------------------------------ helpers

    @api.model
    def _board_reservation(self, reservation_id):
        reservation = self.env["elite.vet.reservation"].browse(self._to_id(reservation_id)).exists()
        if not reservation or reservation.kind != "reservation":
            raise UserError(_("Rezervace nebyla nalezena."))
        return reservation

    @api.model
    def _main_reservation(self, reservation):
        """The client, the visit and the cancellation belong to the main reservation, not to the
        second-room copy of a two-doctor procedure."""
        if reservation.is_second_room and reservation.linked_reservation_id:
            return reservation.linked_reservation_id
        return reservation

    @api.model
    def _reservation_visit(self, reservation):
        return self._records().search([("reservation_id", "=", reservation.id), ("state", "!=", "cancelled")],
                                      limit=1)

    @api.model
    def _can_no_show(self, reservation, visit, day, today):
        """Nedorazil only for the main reservation (the copy follows it), confirmed, of today or
        earlier, and without a visit record."""
        return (reservation.state == "confirmed" and not reservation.is_second_room and not visit
                and day <= today)

    # ------------------------------------------------------------------ API

    @api.model
    def board_reservation(self, reservation_id):
        """Detail of a reservation on the board with the actions the till may offer."""
        self._check_reception()
        reservation = self._board_reservation(reservation_id)
        main = self._main_reservation(reservation)
        visit = self._reservation_visit(main)
        lang = reservation._clinic_lang()
        day = local_date(reservation.start)
        today = clinic_today()
        state = reservation.state
        payment_state = visit.payment_state if visit else False
        return {
            "reservation_id": reservation.id,
            "main_id": main.id,
            "state": state,
            "state_label": dict(STATES)[state],
            # Task 24: WEB / Klinika and who booked it (the copy shows its main reservation)
            **reservation._board_origin(),
            "date": date_str(day),
            "date_label": "%s %d. %d. %d" % (WEEKDAY_ABBR[day.weekday()], day.day, day.month, day.year),
            "is_today": day == today,
            "time": local_time(reservation.start),
            "time_label": "%s–%s" % (local_time(reservation.start), local_time(reservation.stop)),
            "room_id": reservation.room_id.id or None,
            "room": reservation.room_id.name or None,
            "procedure_id": reservation.procedure_id.id or None,
            "procedure": reservation.procedure_id.with_context(lang=lang).name or None,
            "doctor_id": reservation.doctor_id.id or None,
            "doctor": reservation.doctor_id.name or None,
            "partner_id": main.partner_id.id or None,
            "owner": main.partner_id.name or main.contact_name or None,
            "pet_id": main.pet_id.id or None,
            "pet_name": main.pet_id.name or main.pet_name or None,
            "phone": main.contact_phone or main.partner_id.mobile or main.partner_id.phone or None,
            "email": main.contact_email or None,
            "problem": main.problem or None,
            "note": main.note or None,
            "linked": reservation._linked_label() or None,
            "is_second_room": bool(reservation.is_second_room),
            "needs_match": not main.pet_id,
            "has_record": bool(visit),
            "visit_label": (dict(VISIT_STAGES).get(visit.visit_stage) if visit.visit_stage else None)
            if visit else None,
            "payment_state": payment_state or False,
            "payment_state_label": dict(PAYMENT_STATES).get(payment_state) if payment_state else None,
            "can_check_in": day == today and state == "confirmed" and not visit and bool(main.pet_id),
            # the second-room copy follows the main reservation (time sync main -> copy only)
            "can_move": state in MOVABLE_STATES and not visit and not reservation.is_second_room,
            "can_cancel": main.state in CANCELLABLE_STATES and not visit,
            # Nedorazil: a confirmed reservation of today or earlier nobody has checked in
            "can_no_show": self._can_no_show(reservation, visit, day, today),
            # the backend sends the client an e-mail about the cancellation when it has one
            "cancel_sends_email": bool(main.contact_email),
        }

    @api.model
    def move_reservation(self, reservation_id, day, minute, room_id=False, notify=True, end_minute=None,
                         force=False):
        """Move a reservation to `day` ("YYYY-MM-DD"), `minute` (from midnight) and `room_id`
        with the board's `board_move` -> board_reservation(). notify=False: the client gets no
        e-mail about the new time (the move dialog's checkbox, task 25). end_minute (task 28):
        the new end on that day; without it the duration is kept. force=True: "Přesto přesunout"
        after the doctor / room rule refused the move."""
        self._check_reception()
        reservation = self._board_reservation(reservation_id)
        if reservation.state not in MOVABLE_STATES:
            raise UserError(_("Přesunout jde jen potvrzenou rezervaci."))
        if reservation.is_second_room:
            raise UserError(_("Druhá ordinace se přesouvá s hlavní rezervací – přesuňte hlavní rezervaci."))
        if self._reservation_visit(self._main_reservation(reservation)):
            raise UserError(_("Klient už je přijatý (návštěva je založená) – rezervaci nejde přesunout."))
        day = self._day(day)
        try:
            minute = int(minute)
        except (TypeError, ValueError):
            raise UserError(_("Neplatný čas: %s") % minute) from None
        if not 0 <= minute < 1440:
            raise UserError(_("Neplatný čas: %s") % minute)
        room_id = self._to_id(room_id) or False
        if room_id and not self.env["elite.vet.room"].browse(room_id).exists():
            raise UserError(_("Ordinace nebyla nalezena."))
        self.env["elite.vet.reservation"].board_move(reservation.id, date_str(day), minute, room_id,
                                                     notify=bool(notify), end_minute=end_minute,
                                                     force=bool(force))
        return self.board_reservation(reservation.id)

    @api.model
    def cancel_reservation(self, reservation_id):
        """Cancel the (main) reservation as the clinic with `action_cancel` - the client gets the
        cancellation e-mail when the reservation has one, as in the backend."""
        self._check_reception()
        main = self._main_reservation(self._board_reservation(reservation_id))
        if main.state not in CANCELLABLE_STATES:
            raise UserError(_("Zrušit jde jen potvrzenou nebo čekající rezervaci."))
        if self._reservation_visit(main):
            raise UserError(_("Klient už je přijatý (návštěva je založená) – rezervaci nejde zrušit."))
        main.action_cancel("clinic")
        return {"reservation_id": main.id, "state": main.state, "email_sent": bool(main.contact_email)}


    @api.model
    def no_show_reservation(self, reservation_id):
        """Mark a reservation as Nedorazil with the backend's `action_no_show` (the form button):
        no e-mail to the client, the second-room copy follows, the board refreshes itself (bus)
        and the no-show counts in the client's "Nedorazil N×"."""
        self._check_reception()
        reservation = self._board_reservation(reservation_id)
        if reservation.is_second_room:
            raise UserError(_("Druhá ordinace se označuje s hlavní rezervací – otevřete hlavní rezervaci."))
        if reservation.state != "confirmed":
            raise UserError(_("Jako nedorazil jde označit jen potvrzenou rezervaci."))
        if local_date(reservation.start) > clinic_today():
            raise UserError(_("Rezervace je teprve v budoucnu – jako nedorazil ji jde označit nejdřív v její den."))
        if self._reservation_visit(reservation):
            raise UserError(_("Klient už je přijatý (návštěva je založená) – nejde označit jako nedorazil."))
        reservation.action_no_show()
        return {"reservation_id": reservation.id, "state": reservation.state}


class ReservationBoardSecondRoom(models.Model):
    _inherit = "elite.vet.reservation"

    @api.model
    def board_data(self, day_str):
        """Marks the second-room copies of two-doctor procedures (`is_second_room`): the till's
        board offers dragging only for the main reservation."""
        data = super().board_data(day_str)
        # reservations only: blocks and WinVet calendar entries (negative ids) are not records here
        ids = [e["id"] for e in data["events"] if e.get("kind") == "reservation"]
        second = set(self.browse(ids).filtered("is_second_room").ids) if ids else set()
        for event in data["events"]:
            event["is_second_room"] = event["id"] in second
        return data
