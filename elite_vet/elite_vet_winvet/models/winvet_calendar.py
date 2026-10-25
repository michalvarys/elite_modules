"""WinVet calendar in Odoo (contract v4): resources, activities and events.

The bridge pushes the calendar of a window (yesterday .. +60 days by default) on every run. Odoo
keeps it read-only: an event with a mapped room is shown on the boards as "z WinVetu" and - when it
has a time (not all-day) - occupies the room for every Odoo booking path through
`elite.vet.reservation._busy_external` (the second half of the single busy rule).
The events are a separate model on purpose: no mail.thread, no e-mails, reminders, crons,
no-show counts, reservation history or reservation reports ever see them.

Switch "Kalendář z WinVetu" (Vedení): off = the events are hidden, block nothing and new pushes are
ignored (for switching over to Odoo bookings later); "Smazat přenesené záznamy" removes them.
"""
import re
from datetime import datetime, time, timedelta

import pytz

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError

from .winvet_tools import PRAGUE, strip_accents, to_bool, to_date, to_int, to_str, to_utc_datetime

PARAM_ENABLED = "elite_vet_winvet.calendar_enabled"
MANAGER_GROUP = "elite_vet_reservation.group_reservation_manager"
CALENDAR_ENTITIES = ["calendar_resources", "calendar_activities", "calendar_events"]
CALENDAR_LABELS = {
    "calendar_resources": "Kalendáře WinVetu",
    "calendar_activities": "Činnosti kalendáře",
    "calendar_events": "Záznamy kalendáře",
}
CALENDAR_MODELS = {
    "calendar_resources": "elite.vet.winvet.calendar.resource",
    "calendar_activities": "elite.vet.winvet.calendar.activity",
}
EVENT_GREY = "#94a3b8"
COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")


def name_key(text):
    """'ORDINACE 1' == 'Ordinace 1', 'Sál' == 'sal' (case, accents and spaces ignored)."""
    return " ".join(strip_accents(text or "").lower().split())


def calendar_enabled(env):
    return env["ir.config_parameter"].sudo().get_param(PARAM_ENABLED, "1") not in ("0", "False", "false", "")


def local_day_bounds(day):
    """Local day -> [UTC start, UTC end)."""
    start = PRAGUE.localize(datetime.combine(day, time())).astimezone(pytz.utc).replace(tzinfo=None)
    stop = PRAGUE.localize(datetime.combine(day + timedelta(days=1), time())).astimezone(pytz.utc)
    return start, stop.replace(tzinfo=None)


def _color(value):
    value = to_str(value)
    return value.lower() if value and COLOR_RE.match(value) else False


class WinvetCalendarResource(models.Model):
    """KALENDAR_NEW_KALENDAR: one column of the WinVet calendar, mapped to an Odoo room."""

    _name = "elite.vet.winvet.calendar.resource"
    _description = "Kalendář WinVetu (ordinace)"
    _order = "sequence, id"

    winvet_ref = fields.Integer(string="ID ve WinVetu", required=True, index=True, readonly=True)
    name = fields.Char(string="Kalendář ve WinVetu", readonly=True)
    color = fields.Char(string="Barva", readonly=True)
    visible = fields.Boolean(string="Zobrazený ve WinVetu", readonly=True)
    work_from = fields.Char(string="Pracovní doba od", readonly=True)
    work_to = fields.Char(string="Pracovní doba do", readonly=True)
    sequence = fields.Integer(string="Pořadí", readonly=True)
    room_id = fields.Many2one("elite.vet.room", string="Ordinace v Odoo", ondelete="set null",
                              help="Záznamy tohoto kalendáře se ukážou v této ordinaci a obsadí ji. "
                                   "Prázdné = záznamy se v Odoo nikde neukážou.")
    room_manual = fields.Boolean(string="Nastaveno ručně", readonly=True,
                                 help="Ordinaci vybral člověk – synchronizace ji už nemění.")
    active = fields.Boolean(default=True)
    event_count = fields.Integer(string="Záznamů", compute="_compute_event_count")

    _sql_constraints = [("winvet_ref_uniq", "unique(winvet_ref)", "Kalendář WinVetu už existuje.")]

    def _compute_event_count(self):
        groups = self.env["elite.vet.winvet.calendar.event"]._read_group(
            [("resource_ids", "in", self.ids)], ["resource_ids"], ["__count"])
        counts = {resource.id: count for resource, count in groups}
        for rec in self:
            rec.event_count = counts.get(rec.id, 0)

    def write(self, vals):
        if "room_id" in vals and not self.env.context.get("winvet_sync"):
            vals = dict(vals, room_manual=bool(vals.get("room_id")))
        return super().write(vals)

    def _auto_map(self):
        """Visible calendars without a manual mapping get the room of the same name."""
        rooms = {name_key(r.name): r for r in self.env["elite.vet.room"].with_context(active_test=True).search([])}
        for rec in self.filtered(lambda r: not r.room_manual):
            room = rooms.get(name_key(rec.name)) if rec.visible and rec.active else False
            if rec.room_id != (room or self.env["elite.vet.room"]):
                rec.with_context(winvet_sync=True).room_id = room.id if room else False


class WinvetCalendarActivity(models.Model):
    """ORD_CINNOST: activity (type) of a WinVet calendar entry, mapped to an Odoo procedure."""

    _name = "elite.vet.winvet.calendar.activity"
    _description = "Činnost kalendáře WinVetu"
    _order = "name, id"

    winvet_ref = fields.Integer(string="ID ve WinVetu", required=True, index=True, readonly=True)
    name = fields.Char(string="Činnost ve WinVetu", readonly=True)
    duration = fields.Integer(string="Doba (min)", readonly=True)
    color = fields.Char(string="Barva", readonly=True)
    symbol = fields.Char(string="Symbol", readonly=True)
    web = fields.Boolean(string="Na webu WinVetu", readonly=True)
    procedure_id = fields.Many2one("elite.vet.procedure", string="Úkon v Odoo", ondelete="set null")
    procedure_manual = fields.Boolean(string="Nastaveno ručně", readonly=True)
    active = fields.Boolean(default=True)

    _sql_constraints = [("winvet_ref_uniq", "unique(winvet_ref)", "Činnost WinVetu už existuje.")]

    def write(self, vals):
        if "procedure_id" in vals and not self.env.context.get("winvet_sync"):
            vals = dict(vals, procedure_manual=bool(vals.get("procedure_id")))
        return super().write(vals)

    def _auto_map(self):
        """Activities without a manual mapping get the active procedure of the same name (cs or en)."""
        Procedure = self.env["elite.vet.procedure"].with_context(active_test=True)
        by_name = {}
        for lang in ("en_US", "cs_CZ"):
            for proc in Procedure.with_context(lang=lang).search([]):
                by_name.setdefault(name_key(proc.name), proc)
        for rec in self.filtered(lambda r: not r.procedure_manual):
            proc = by_name.get(name_key(rec.name)) if rec.active else False
            if rec.procedure_id != (proc or Procedure.browse()):
                rec.with_context(winvet_sync=True).procedure_id = proc.id if proc else False


class WinvetCalendarEvent(models.Model):
    """One occurrence of a WinVet calendar entry (recurrences are expanded by the bridge)."""

    _name = "elite.vet.winvet.calendar.event"
    _description = "Záznam kalendáře WinVetu"
    _order = "start, id"

    key = fields.Char(string="Klíč", required=True, index=True, readonly=True,
                      help="ID_KALENDAR, u opakování ID vzoru a datum výskytu (např. 49-20260926).")
    winvet_ref = fields.Integer(string="ID řádku ve WinVetu", readonly=True)
    pattern_ref = fields.Integer(string="ID opakování", readonly=True)
    recurring = fields.Boolean(string="Opakovaný", readonly=True)
    occurrence_date = fields.Date(string="Původní den výskytu", readonly=True)
    start = fields.Datetime(string="Začátek", required=True, index=True, readonly=True)
    stop = fields.Datetime(string="Konec", required=True, readonly=True)
    all_day = fields.Boolean(string="Celý den", readonly=True)
    date = fields.Date(string="Den", compute="_compute_dates", store=True, index=True)
    end_date = fields.Date(string="Poslední den", compute="_compute_dates", store=True)
    resource_ids = fields.Many2many("elite.vet.winvet.calendar.resource", "elite_vet_winvet_cal_event_resource_rel",
                                    "event_id", "resource_id", string="Kalendáře WinVetu", readonly=True)
    resource_refs = fields.Char(string="ID kalendářů", readonly=True)
    room_ids = fields.Many2many("elite.vet.room", "elite_vet_winvet_cal_event_room_rel", "event_id", "room_id",
                                string="Ordinace", compute="_compute_room_ids", store=True)
    activity_id = fields.Many2one("elite.vet.winvet.calendar.activity", string="Činnost", readonly=True,
                                  ondelete="set null")
    activity_ref = fields.Integer(readonly=True)
    procedure_id = fields.Many2one(related="activity_id.procedure_id", string="Úkon")
    partner_id = fields.Many2one("res.partner", string="Klient", readonly=True, ondelete="set null")
    owner_ref = fields.Integer(string="ID majitele ve WinVetu", readonly=True)
    pet_id = fields.Many2one("elite.vet.pet", string="Zvíře", readonly=True, ondelete="set null")
    patient_ref = fields.Integer(string="ID pacienta ve WinVetu", readonly=True)
    title = fields.Char(string="Text ve WinVetu", readonly=True)
    busy_status = fields.Integer(string="Stav (WinVet)", readonly=True)
    done = fields.Boolean(string="Vyřízeno", readonly=True)
    winvet_modified = fields.Datetime(string="Změněno ve WinVetu", readonly=True)
    name = fields.Char(string="Název", compute="_compute_name", store=True)
    color_hex = fields.Char(string="Barva", compute="_compute_color_hex")

    _sql_constraints = [("key_uniq", "unique(key)", "Záznam kalendáře WinVetu už existuje.")]

    @api.depends("start", "stop", "all_day")
    def _compute_dates(self):
        for rec in self:
            if not rec.start:
                rec.date = rec.end_date = False
                continue
            start = pytz.utc.localize(rec.start).astimezone(PRAGUE)
            stop = pytz.utc.localize(rec.stop or rec.start).astimezone(PRAGUE)
            rec.date = start.date()
            last = stop - timedelta(seconds=1) if stop > start else stop
            rec.end_date = max(start.date(), last.date())

    @api.depends("resource_ids.room_id")
    def _compute_room_ids(self):
        for rec in self:
            rec.room_ids = rec.resource_ids.room_id

    @api.depends("pet_id.name", "partner_id.name", "title", "activity_id.name")
    def _compute_name(self):
        for rec in self:
            if rec.pet_id or rec.partner_id:
                rec.name = " / ".join(p for p in (rec.pet_id.name, rec.partner_id.name) if p)
            else:
                rec.name = rec.title or rec.activity_id.name or "WinVet"

    def _compute_color_hex(self):
        for rec in self:
            rec.color_hex = rec.activity_id.color or rec.resource_ids[:1].color or EVENT_GREY

    # ------------------------------------------------------------------ read-only

    def write(self, vals):
        if not self.env.context.get("winvet_sync"):
            raise UserError(_("Záznamy z WinVetu nejde v Odoo měnit – změňte je ve WinVetu."))
        return super().write(vals)

    def unlink(self):
        if not self.env.context.get("winvet_sync"):
            raise UserError(_("Záznamy z WinVetu se mažou jen synchronizací nebo tlačítkem "
                              "„Smazat přenesené záznamy“ (WinVet data → Kalendář z WinVetu)."))
        return super().unlink()

    # ------------------------------------------------------------------ queries

    @api.model
    def _timed_domain(self, start, stop, room_ids=None):
        domain = [("all_day", "=", False), ("start", "<", stop), ("stop", ">", start), ("room_ids", "!=", False)]
        if room_ids is not None:
            domain.append(("room_ids", "in", list(room_ids)))
        return domain

    @api.model
    def _busy_events(self, room_ids, start, stop):
        """Timed events with a mapped room in `room_ids` overlapping [start, stop) (sudo, any caller)."""
        if not room_ids or not calendar_enabled(self.env):
            return self.sudo().browse()
        return self.sudo().search(self._timed_domain(start, stop, room_ids))

    @api.model
    def _day_events(self, day):
        """(timed events, all-day events) touching the local `day` - empty when switched off."""
        if not calendar_enabled(self.env):
            return self.browse(), self.browse()
        start, stop = local_day_bounds(day)
        timed = self.search(self._timed_domain(start, stop))
        all_day = self.search([("all_day", "=", True), ("date", "<=", day), ("end_date", ">=", day)])
        return timed, all_day

    def _label(self):
        """'Rex (Jana Nováková)' / the WinVet text."""
        self.ensure_one()
        if self.pet_id and self.partner_id:
            return "%s (%s)" % (self.pet_id.name, self.partner_id.name)
        return self.pet_id.name or self.partner_id.name or self.title or self.activity_id.name or "WinVet"


class WinvetCalendarSettings(models.TransientModel):
    """Vedení: switch the WinVet calendar off (switch-over to Odoo) and purge the transferred rows."""

    _name = "elite.vet.winvet.calendar.settings"
    _description = "Kalendář z WinVetu – nastavení"

    enabled = fields.Boolean(string="Kalendář z WinVetu zapnutý", compute="_compute_info")
    event_count = fields.Integer(string="Přenesených záznamů", compute="_compute_info")
    timed_count = fields.Integer(string="Z toho s časem v namapované ordinaci", compute="_compute_info")
    unmapped_count = fields.Integer(string="Bez ordinace v Odoo", compute="_compute_info")
    first_date = fields.Date(string="Od", compute="_compute_info")
    last_date = fields.Date(string="Do", compute="_compute_info")

    def _compute_info(self):
        Event = self.env["elite.vet.winvet.calendar.event"].sudo()
        enabled = calendar_enabled(self.env)
        first = Event.search([], order="date", limit=1)
        last = Event.search([], order="date desc", limit=1)
        for rec in self:
            rec.enabled = enabled
            rec.event_count = Event.search_count([])
            rec.timed_count = Event.search_count([("all_day", "=", False), ("room_ids", "!=", False)])
            rec.unmapped_count = Event.search_count([("room_ids", "=", False)])
            rec.first_date = first.date
            rec.last_date = last.end_date

    @api.model
    def _check_manager(self):
        if not (self.env.su or self.env.user.has_group(MANAGER_GROUP)):
            raise AccessError(_("Kalendář z WinVetu nastavuje jen vedení (správce rezervací)."))

    def _reopen(self):
        return {"type": "ir.actions.act_window", "res_model": self._name, "view_mode": "form",
                "target": "current", "res_id": self.create({}).id,
                "name": _("Kalendář z WinVetu")}

    def _set_enabled(self, value):
        self._check_manager()
        self.env["ir.config_parameter"].sudo().set_param(PARAM_ENABLED, "1" if value else "0")
        from odoo.addons.elite_vet_reservation.models.live import notify_board
        notify_board(self.env)

    def action_disable(self):
        self._set_enabled(False)
        return self._reopen()

    def action_enable(self):
        self._set_enabled(True)
        return self._reopen()

    def action_purge(self):
        self._check_manager()
        self.env["elite.vet.winvet.calendar.event"].sudo().with_context(winvet_sync=True).search([]).unlink()
        from odoo.addons.elite_vet_reservation.models.live import notify_board
        notify_board(self.env)
        return self._reopen()


class WinvetCalendarSync(models.AbstractModel):
    """Receiving the calendar entities of contract v4."""

    _inherit = "elite.vet.winvet.sync"

    @api.model
    def _winvet_entities(self):
        entities = super()._winvet_entities()
        return entities + [e for e in CALENDAR_ENTITIES if e not in entities]

    @api.model
    def _winvet_entity_models(self):
        return dict(super()._winvet_entity_models(), **CALENDAR_MODELS,
                    calendar_events="elite.vet.winvet.calendar.event")

    @api.model
    def _winvet_entity_labels(self):
        return dict(super()._winvet_entity_labels(), **CALENDAR_LABELS)

    @api.model
    def _winvet_master_entities(self):
        return super()._winvet_master_entities() | {"calendar_resources", "calendar_activities"}

    def _push_calendar_resources(self, records, stats, errors, batch, batches):
        vals = {ref: {"name": to_str(r.get("name")) or "Kalendář %s" % ref, "color": _color(r.get("color")),
                      "visible": to_bool(r.get("visible")), "work_from": to_str(r.get("work_from")),
                      "work_to": to_str(r.get("work_to")), "sequence": to_int(r.get("sequence")) or 0,
                      "active": True}
                for ref, r in records.items()}
        resources = self._upsert("elite.vet.winvet.calendar.resource", vals, stats, errors)
        self.env["elite.vet.winvet.calendar.resource"].concat(*resources.values())._auto_map()

    def _push_calendar_activities(self, records, stats, errors, batch, batches):
        vals = {ref: {"name": to_str(r.get("name")) or "Činnost %s" % ref, "duration": to_int(r.get("duration")),
                      "color": _color(r.get("color")), "symbol": to_str(r.get("symbol")),
                      "web": to_bool(r.get("web")), "active": True}
                for ref, r in records.items()}
        activities = self._upsert("elite.vet.winvet.calendar.activity", vals, stats, errors)
        self.env["elite.vet.winvet.calendar.activity"].concat(*activities.values())._auto_map()

    @api.model
    def push(self, payload):
        if (payload or {}).get("entity") == "calendar_events":
            return self._sync_env()._receive_calendar_events(payload)
        return super().push(payload)

    @api.model
    def _receive_calendar_events(self, payload):
        """calendar_events: upsert by `key`; the last batch of a run removes the events of the
        pushed window that WinVet no longer has. Switched off = accepted and ignored."""
        Event = self.env["elite.vet.winvet.calendar.event"]
        mode = payload.get("mode") or "full"
        run_id = to_str(payload.get("run_id"))
        batch, batches = to_int(payload.get("batch")) or 1, to_int(payload.get("batches")) or 1
        stats = {"created": 0, "updated": 0, "deleted": 0, "skipped": 0}
        errors = []
        records = {}
        for rec in payload.get("records") or []:
            key = to_str(rec.get("key")) if isinstance(rec, dict) else False
            start, stop = (to_utc_datetime(rec.get("start")), to_utc_datetime(rec.get("end"))) if key else (0, 0)
            if not key or not start or not stop:
                stats["skipped"] += 1
                continue
            records[key] = dict(rec, _start=start, _stop=max(stop, start + timedelta(minutes=1)))
        if not calendar_enabled(self.env):
            stats["skipped"] += len(records)
            self.env["elite.vet.winvet.status"].get_status().record_push(
                "calendar_events", mode, run_id, stats, "kalendář z WinVetu je vypnutý – záznamy se neukládají")
            return dict(stats, ok=True)

        recs = list(records.values())
        resources = self._ref_map("elite.vet.winvet.calendar.resource",
                                  {to_int(x) for r in recs for x in (r.get("resource_ids") or [])})
        activities = self._ref_map("elite.vet.winvet.calendar.activity", {to_int(r.get("activity_id")) for r in recs})
        partners = self._ref_map("res.partner", {to_int(r.get("owner_id")) for r in recs})
        pets = self._ref_map("elite.vet.pet", {to_int(r.get("patient_id")) for r in recs})
        existing = {e.key: e for e in Event.search([("key", "in", list(records))])}
        to_create = []
        changed = False
        for key, r in records.items():
            refs = [to_int(x) for x in (r.get("resource_ids") or []) if to_int(x)]
            owner, patient, activity = to_int(r.get("owner_id")), to_int(r.get("patient_id")), to_int(r.get("activity_id"))
            vals = {
                "winvet_ref": to_int(r.get("id")) or False, "pattern_ref": to_int(r.get("pattern_id")) or False,
                "recurring": to_bool(r.get("recurring")), "occurrence_date": to_date(r.get("occurrence_date")),
                "start": r["_start"], "stop": r["_stop"], "all_day": to_bool(r.get("all_day")),
                "resource_refs": ",".join(str(x) for x in refs) or False,
                "activity_id": activities.get(activity, False), "activity_ref": activity or False,
                "partner_id": partners.get(owner, False), "owner_ref": owner or False,
                "pet_id": pets.get(patient, False), "patient_ref": patient or False,
                "title": to_str(r.get("title")), "busy_status": to_int(r.get("busy_status")) or 0,
                "done": to_bool(r.get("done")), "winvet_modified": to_utc_datetime(r.get("modified")),
            }
            resource_ids = sorted({resources[x] for x in refs if x in resources})
            rec = existing.get(key)
            if rec:
                diff = self._diff(rec, vals)
                if sorted(rec.resource_ids.ids) != resource_ids:
                    diff["resource_ids"] = [(6, 0, resource_ids)]
                if diff:
                    rec.write(diff)
                    stats["updated"] += 1
                    changed = True
            else:
                to_create.append(dict(vals, key=key, resource_ids=[(6, 0, resource_ids)]))
        if to_create:
            created = self._safe_create(Event, to_create, stats, errors)
            changed = changed or bool(created)

        window = payload.get("window") or {}
        w_from, w_to = to_date(window.get("from")), to_date(window.get("to"))
        Run = self.env["elite.vet.winvet.run"]
        if not run_id or not (w_from and w_to) or w_to < w_from:
            errors.append("záznamy kalendáře bez okna nebo run_id – mazání chybějících přeskočeno")
        else:
            Run.store_batch(run_id, "calendar_events", batch, batches, list(records))
            if batch >= batches:
                seen = Run.collect(run_id, "calendar_events", batches)
                if seen is None:
                    errors.append("běh %s nemá všechny dávky – mazání chybějících přeskočeno" % run_id)
                else:
                    start, _x = local_day_bounds(w_from)
                    _y, stop = local_day_bounds(w_to)
                    gone = Event.search([("start", "<", stop), ("stop", ">", start), ("key", "not in", list(seen))])
                    stats["deleted"] += len(gone)
                    changed = changed or bool(gone)
                    gone.unlink()
                Run.cleanup(run_id, "calendar_events")
        if changed:
            from odoo.addons.elite_vet_reservation.models.live import notify_board
            notify_board(self.env)
        self.env["elite.vet.winvet.status"].get_status().record_push(
            "calendar_events", mode, run_id, stats, "; ".join(errors[:5]) if errors else None)
        return dict(stats, ok=True)


class ReservationWinvetCalendar(models.Model):
    """The WinVet calendar in the single busy rule and on the backend / till board."""

    _inherit = "elite.vet.reservation"

    @api.model
    def _busy_external(self, room_ids, start, stop):
        own = super()._busy_external(room_ids, start, stop)
        events = self.env["elite.vet.winvet.calendar.event"]._busy_events(list(room_ids), start, stop)
        return events if not own else own  # another source first; the callers only need one clash

    @api.model
    def board_data(self, day_str):
        data = super().board_data(day_str)
        day = fields.Date.from_string(day_str)
        A = self.env["elite.vet.availability"]
        Event = self.env["elite.vet.winvet.calendar.event"]
        timed, all_day = Event._day_events(day)
        shown = {r["id"] for r in data["rooms"]}
        events = []
        for ev in timed:
            ev_start, ev_end = A.utc_to_local_minutes(ev.start, day), A.utc_to_local_minutes(ev.stop, day)
            if ev_end <= ev_start:
                continue
            label = ev._label()
            for room in ev.room_ids.filtered(lambda r: r.id in shown):
                events.append({
                    # negative id: never mistaken for a reservation id by the board extensions
                    "id": -ev.id, "winvet_event_id": ev.id, "kind": "winvet", "state": "winvet",
                    "block_scope": False, "room_id": room.id, "start": ev_start, "end": ev_end,
                    "time_label": "%d:%02d–%d:%02d" % (ev_start // 60, ev_start % 60, ev_end // 60, ev_end % 60),
                    "name": label, "pet": ev.pet_id.name or "", "owner": ev.partner_id.name or "",
                    "winvet_title": ev.title or "",
                    "color_hex": "#e2e8f0", "winvet_color": ev.color_hex, "symbol": ev.activity_id.symbol or "",
                    "phone": "", "email": "", "problem": "", "procedure": ev.activity_id.name or "",
                    "doctor": "", "doctor_initials": "", "doctor_color": False, "linked": "",
                    "source": "winvet", "mail_on_move": False, "done": ev.done,
                })
        data["events"] = data["events"] + events
        notes = {}
        for ev in all_day:
            for room in ev.room_ids.filtered(lambda r: r.id in shown):
                notes.setdefault(room.id, []).append({
                    "id": ev.id, "label": ev._label(), "activity": ev.activity_id.name or "",
                    "color": ev.color_hex,
                })
        for room in data["rooms"]:
            room["winvet_notes"] = notes.get(room["id"], [])
        data["winvet_calendar"] = bool(timed or all_day)
        return data
