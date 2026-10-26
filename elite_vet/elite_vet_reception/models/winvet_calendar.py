"""WinVet calendar entries in Dnes (Přicházejí) and their check-in.

Entries of the WinVet calendar (elite_vet_winvet, contract v4) are read-only. Today's client
appointments are listed among the arriving clients (badge "WinVet") and can be checked in like a
reservation: the visit record is created (or today's open record of the pet is reused), its room
comes from the mapping of the WinVet calendar. An appointment without a WinVet patient (title only,
badge "bez karty") is paired with a pet of the card index first (task 30, `pair_winvet`); the
pairing lives only in Odoo (`manual_pet_id`), everything else of the entry never changes.
"""
import re

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from odoo.addons.elite_vet_clinic.models.patient_card import clinic_today, local_time
from odoo.addons.elite_vet_reservation.models.live import notify_board
from odoo.addons.elite_vet_winvet.models.winvet_calendar import calendar_enabled


class ClinicalRecordWinvetEvent(models.Model):
    _inherit = "elite.vet.clinical.record"

    winvet_event_id = fields.Many2one("elite.vet.winvet.calendar.event", string="Záznam z WinVetu",
                                      ondelete="set null", index=True, copy=False, readonly=True,
                                      help="Záznam kalendáře WinVetu, ze kterého recepce klienta přijala.")


class ReceptionWinvetCalendar(models.AbstractModel):
    _inherit = "elite.vet.reception"

    @api.model
    def _winvet_client_events(self, day):
        """Today's timed client appointments of the WinVet calendar (task 30): a client, a pet or a
        WinVet activity – an entry without any of them ("Oběd", "Příjmy", empty) is a staff note –,
        not marked done in WinVet, without a deceased pet, not checked in yet (no record of the
        entry that is not cancelled). Returns (events, ids of the checked-in ones)."""
        Event = self.env["elite.vet.winvet.calendar.event"].sudo()
        events = Event.search([("date", "<=", day), ("end_date", ">=", day), ("all_day", "=", False),
                               ("done", "=", False)], order="start, id")
        events = events.filtered(lambda e: (e.effective_partner_id or e.effective_pet_id or e.activity_id)
                                 and not e.effective_pet_id.deceased)
        taken = set(self._records().search([("winvet_event_id", "in", events.ids),
                                             ("state", "!=", "cancelled")]).winvet_event_id.ids) if events else set()
        return events.filtered(lambda e: e.id not in taken)

    @api.model
    def _winvet_search_hint(self, title):
        """Kartotéka search prefilled from a WinVet text: the part before the first separator
        ("," " - " "/" "(" ";"), at most two words – the clinic writes "Příjmení Jméno, …"."""
        part = re.split(r",|;|/|\(|\s-\s|\s–\s", (title or "").strip())[0]
        return " ".join(part.split()[:2])

    @api.model
    def _winvet_pairing_info(self, event):
        """Fields of a WinVet row about the card index pairing (Dnes, room screen)."""
        return {
            "needs_pairing": not event.effective_pet_id,
            "paired_manually": bool(event.manual_pet_id and not event.pet_id),
            "winvet_title": event.title or event.activity_id.name or None,
            "search_hint": self._winvet_search_hint(event.title) or None,
        }

    @api.model
    def _winvet_arriving(self, day):
        """Rows of Přicházejí for the WinVet client appointments of `day` (see
        `_winvet_client_events`). Without a pet (title only) the row says so ("bez karty") and is
        paired first (Spárovat… → pair_winvet), then it is checked in like the others."""
        if not calendar_enabled(self.env):
            return []
        rows = []
        for ev in self._winvet_client_events(day):
            pet, partner = ev.effective_pet_id, ev.effective_partner_id
            rows.append(dict({
                "key": "w-%s" % ev.id, "winvet_event_id": ev.id, "reservation_id": None, "source": "winvet",
                "time": local_time(ev.start),
                "pet_id": pet.id or None, "pet_name": pet.name or None,
                "owner": partner.name or None, "partner_id": partner.id or None,
                "procedure": ev.activity_id.name or None, "doctor": None,
                "room": ev.room_ids[:1].name or None, "needs_match": False,
            }, **self._winvet_pairing_info(ev)))
        return rows

    @api.model
    def _winvet_room_booked(self, day):
        """Items of "Dnes jsou objednaní" on the screen Ordinace for today's WinVet client
        appointments (`_winvet_client_events`) in the first mapped room of the entry; a pet paired
        at the reception counts like a WinVet match (Otevřít kartu), without one: Spárovat…."""
        if not calendar_enabled(self.env):
            return {}
        out = {}
        for ev in self._winvet_client_events(day).filtered("room_ids"):
            pet, partner = ev.effective_pet_id, ev.effective_partner_id
            time = local_time(ev.start)
            item = {
                "key": "wv%d" % ev.id, "winvet_event_id": ev.id, "source": "winvet",
                "record_id": None, "reservation_id": None, "walk_in": False,
                "stage": "booked", "stage_label": None,
                "time": time, "reservation_time": time, "arrived_time": None, "called_time": None,
                "waiting_minutes": None,
                "pet_id": pet.id or None, "pet_name": pet.name or ev.title or ev.activity_id.name or None,
                "species_label": self._records()._species_label(pet) if pet else None,
                "owner": partner.name or None, "partner_id": partner.id or None,
                "procedure": ev.procedure_id.name or ev.activity_id.name or None,
                "doctor": None, "doctor_id": None, "room_id": ev.room_ids[:1].id,
                "alerts": pet.alert_summary or None if pet else None, "reception_note": None,
                "draggable": False, "sort": ev.start.strftime("%Y-%m-%d %H:%M:%S"),
            }
            item.update(self._winvet_pairing_info(ev))
            out.setdefault(ev.room_ids[:1].id, []).append(item)
        return out

    @api.model
    def room_board(self, day=None):
        """WinVet appointments of the day join "Dnes jsou objednaní" of their room (read-only)."""
        data = super().room_board(day)
        extra = self._winvet_room_booked(self._day(day))
        for column in data["columns"]:
            items = extra.get(column["room_id"])
            if not items:
                continue
            booked = column["sections"]["booked"] + items
            booked.sort(key=lambda i: (i["sort"] or "", i["key"]))
            column["sections"]["booked"] = booked
            column["counts"]["booked"] = len(booked)
        return data

    @api.model
    def today_data(self, day=None):
        data = super().today_data(day)
        for row in data["arriving"]:
            row.setdefault("key", "r-%s" % row["reservation_id"])
            row.setdefault("source", "odoo")
        extra = self._winvet_arriving(self._day(day))
        if extra:
            data["arriving"] = sorted(data["arriving"] + extra, key=lambda r: (r["time"] or "", r["key"]))
        return data

    @api.model
    def check_in_winvet(self, event_id, employee_name=None, note=None):
        """The client of today's WinVet entry arrived: today's open record of the pet (or a new one)
        is linked to the entry and waits; the room comes from the WinVet calendar mapping."""
        self._check_reception()
        if not calendar_enabled(self.env):
            raise UserError(_("Kalendář z WinVetu je vypnutý."))
        event = self.env["elite.vet.winvet.calendar.event"].sudo().browse(int(event_id)).exists()
        if not event:
            raise UserError(_("Záznam z WinVetu nebyl nalezen (mezitím ho ve WinVetu smazali?)."))
        today = clinic_today()
        if not (event.date <= today <= event.end_date):
            raise UserError(_("Záznam z WinVetu není na dnešek – přijmout jde jen dnešní návštěvu."))
        pet = event.effective_pet_id
        if not pet:
            raise UserError(_("Záznam z WinVetu nemá zvíře z kartotéky – nejdřív ho spárujte (Spárovat…)."))
        self._check_bookable_pet(pet)
        Records = self._records()
        record = Records.search([("winvet_event_id", "=", event.id), ("state", "!=", "cancelled")], limit=1)
        if not record:
            candidate = Records.search([("pet_id", "=", pet.id), ("date", "=", today),
                                        ("state", "=", "draft"), ("reservation_id", "=", False),
                                        ("winvet_event_id", "=", False)], order="start desc, id desc", limit=1)
            if candidate:
                record = candidate
            else:
                record = Records.browse(Records.open_today_record(pet.id, force_new=True)["id"])
            record.winvet_event_id = event
        room = event.room_ids[:1]
        if room and not record.room_id and record.state == "draft":
            self._set_room(record, room)
        self._mark_arrived(record, employee_name)
        self._set_note(record, note)
        notify_board(self.env)
        return self._record_dict(record)

    # ------------------------------------------------------------------ task 30: pairing

    @api.model
    def _winvet_event_for_pairing(self, event_id):
        self._check_reception()
        if not calendar_enabled(self.env):
            raise UserError(_("Kalendář z WinVetu je vypnutý."))
        event = self.env["elite.vet.winvet.calendar.event"].sudo().browse(self._to_id(event_id)).exists()
        if not event:
            raise UserError(_("Záznam z WinVetu nebyl nalezen (mezitím ho ve WinVetu smazali?)."))
        if self._records().search_count([("winvet_event_id", "=", event.id), ("state", "!=", "cancelled")]):
            raise UserError(_("Klient z této objednávky už je přijatý – spárování teď nejde změnit."))
        return event

    @api.model
    def pair_winvet(self, event_id, partner_id, pet_id):
        """Spárovat…: a WinVet appointment without a WinVet patient (title only) belongs to a pet
        of the card index. Stored in Odoo only (`manual_pet_id` of the entry, never overwritten by
        the sync); when WinVet later sends its own patient, that one wins."""
        event = self._winvet_event_for_pairing(event_id)
        if event.done:
            raise UserError(_("Objednávka je ve WinVetu už vyřízená."))
        if event.pet_id:
            raise UserError(_("Objednávka už má zvíře z WinVetu – spárování není potřeba."))
        partner = self._get_owner(partner_id)
        pet = self._get_owner_pet(partner, pet_id)
        self._check_bookable_pet(pet)
        event._set_manual_match(pet)
        notify_board(self.env)
        return {"winvet_event_id": event.id, "time": local_time(event.start),
                "pet_id": pet.id, "pet_name": pet.name, "partner_id": partner.id, "owner": partner.name}

    @api.model
    def unpair_winvet(self, event_id):
        """Zrušit spárování: the WinVet appointment is without a pet again (before the check-in)."""
        event = self._winvet_event_for_pairing(event_id)
        if not event.manual_pet_id:
            raise UserError(_("Objednávka není spárovaná v Odoo."))
        event._clear_manual_match()
        notify_board(self.env)
        return {"winvet_event_id": event.id, "winvet_title": event.title or event.activity_id.name or None}
