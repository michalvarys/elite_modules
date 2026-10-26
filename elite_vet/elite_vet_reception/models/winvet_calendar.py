"""WinVet calendar entries in Dnes (Přicházejí) and their check-in.

Entries of the WinVet calendar (elite_vet_winvet, contract v4) are read-only. Today's entries with
a pet matched in the card index are listed among the arriving clients (badge "WinVet") and can be
checked in like a reservation: the visit record is created (or today's open record of the pet is
reused), its room comes from the mapping of the WinVet calendar. The entry itself never changes.
"""
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
    def _winvet_arriving(self, day):
        """Rows of Přicházejí for the WinVet entries of `day` with a matched live pet, not marked
        done in WinVet and not checked in yet (no record of the entry that is not cancelled)."""
        if not calendar_enabled(self.env):
            return []
        Event = self.env["elite.vet.winvet.calendar.event"].sudo()
        events = Event.search([("date", "<=", day), ("end_date", ">=", day), ("pet_id", "!=", False),
                               ("done", "=", False)], order="start, id")
        events = events.filtered(lambda e: not e.pet_id.deceased)
        if not events:
            return []
        taken = set(self._records().search([("winvet_event_id", "in", events.ids),
                                             ("state", "!=", "cancelled")]).winvet_event_id.ids)
        rows = []
        for ev in events.filtered(lambda e: e.id not in taken):
            rows.append({
                "key": "w-%s" % ev.id, "winvet_event_id": ev.id, "reservation_id": None, "source": "winvet",
                "time": None if ev.all_day else local_time(ev.start),
                "pet_id": ev.pet_id.id, "pet_name": ev.pet_id.name,
                "owner": ev.partner_id.name or ev.pet_id.partner_id.name or None,
                "partner_id": (ev.partner_id or ev.pet_id.partner_id).id or None,
                "procedure": ev.activity_id.name or None, "doctor": None,
                "room": ev.room_ids[:1].name or None, "needs_match": False,
            })
        return rows

    @api.model
    def _winvet_room_booked(self, day):
        """Items of "Dnes ještě přijdou" on the screen Ordinace for today's timed WinVet entries:
        client appointments (a client, a pet or a WinVet activity – not "Oběd" and other notes),
        not marked done in WinVet, not checked in yet; in the first mapped room of the entry."""
        if not calendar_enabled(self.env):
            return {}
        Event = self.env["elite.vet.winvet.calendar.event"].sudo()
        events = Event.search([("date", "<=", day), ("end_date", ">=", day), ("all_day", "=", False),
                               ("done", "=", False), ("room_ids", "!=", False)], order="start, id")
        events = events.filtered(lambda e: (e.partner_id or e.pet_id or e.activity_id)
                                 and not (e.pet_id and e.pet_id.deceased))
        if not events:
            return {}
        taken = set(self._records().search([("winvet_event_id", "in", events.ids),
                                             ("state", "!=", "cancelled")]).winvet_event_id.ids)
        out = {}
        for ev in events.filtered(lambda e: e.id not in taken):
            pet, partner = ev.pet_id, ev.partner_id or ev.pet_id.partner_id
            time = local_time(ev.start)
            out.setdefault(ev.room_ids[:1].id, []).append({
                "key": "wv%d" % ev.id, "winvet_event_id": ev.id, "source": "winvet",
                "record_id": None, "reservation_id": None, "walk_in": False,
                "stage": "booked", "stage_label": None,
                "time": time, "reservation_time": time, "arrived_time": None, "called_time": None,
                "waiting_minutes": None,
                "pet_id": pet.id or None, "pet_name": pet.name or ev.title or None,
                "species_label": self._records()._species_label(pet) if pet else None,
                "owner": partner.name or None, "partner_id": partner.id or None,
                "procedure": ev.procedure_id.name or ev.activity_id.name or None,
                "doctor": None, "doctor_id": None, "room_id": ev.room_ids[:1].id,
                "alerts": pet.alert_summary or None if pet else None, "reception_note": None,
                "draggable": False, "sort": ev.start.strftime("%Y-%m-%d %H:%M:%S"),
            })
        return out

    @api.model
    def room_board(self, day=None):
        """WinVet appointments of the day join "Dnes ještě přijdou" of their room (read-only)."""
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
        if not event.pet_id:
            raise UserError(_("Záznam z WinVetu nemá zvíře z kartotéky – přijměte klienta jako „Bez objednání“."))
        self._check_bookable_pet(event.pet_id)
        Records = self._records()
        record = Records.search([("winvet_event_id", "=", event.id), ("state", "!=", "cancelled")], limit=1)
        if not record:
            candidate = Records.search([("pet_id", "=", event.pet_id.id), ("date", "=", today),
                                        ("state", "=", "draft"), ("reservation_id", "=", False),
                                        ("winvet_event_id", "=", False)], order="start desc, id desc", limit=1)
            if candidate:
                record = candidate
            else:
                record = Records.browse(Records.open_today_record(event.pet_id.id, force_new=True)["id"])
            record.winvet_event_id = event
        room = event.room_ids[:1]
        if room and not record.room_id and record.state == "draft":
            self._set_room(record, room)
        self._mark_arrived(record, employee_name)
        self._set_note(record, note)
        notify_board(self.env)
        return self._record_dict(record)
