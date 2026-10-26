import uuid
from datetime import timedelta

import pytz

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError

from .holidays import holiday_name
from .pet import SPECIES

STATES = [
    ("web_new", "Čekající z webu"), ("confirmed", "Potvrzená"), ("done", "Proběhla"),
    ("cancelled", "Zrušená"), ("no_show", "Nedorazil"),
]
BUSY_STATES = ("confirmed", "done")
INACTIVE_STATES = ("cancelled", "no_show")
# Clinic opening hours timezone; must not depend on the acting user's timezone (cron, sudo, web).
TZ = pytz.timezone("Europe/Prague")
# Czech day names hard-coded: must not depend on the user or browser language.
WEEKDAY_ABBR = ["po", "út", "st", "čt", "pá", "so", "ne"]
# Reception books far ahead (vaccination in a year); the website has its own horizon in settings.
RECEPTION_HORIZON_DAYS = 400
# Block scope: "web" closes the time for online booking only, "full" for everyone.
BLOCK_SCOPES = [("web", "Jen web"), ("full", "Úplná")]
# Stable doctor colors on the board (by id), readable with white text.
DOCTOR_COLORS = ["#7c3aed", "#db2777", "#ea580c", "#0891b2", "#4d7c0f", "#b45309", "#2563eb", "#be123c"]
# Blocks (kind "block") are created, moved, edited and deleted by Správce rezervací only (task 16);
# reception and everyone above it (nurse, doctor, room accounts) only see them.
BLOCK_MANAGER_GROUP = "elite_vet_reservation.group_reservation_manager"
TITLES = {"mvdr.", "mudr.", "dr.", "ing.", "bc.", "mgr.", "phd.", "dipl.", "ph.d."}


def name_initials(full_name):
    """'MVDr. Dana Pokorná' -> 'DP' (titles and dotted abbreviations are skipped)."""
    words = [w for w in (full_name or "").replace(",", " ").split()
             if w.lower() not in TITLES and not w.endswith(".")]
    if not words:
        return ""
    picked = [words[0], words[-1]] if len(words) > 1 else words[:1]
    return "".join(w[0].upper() for w in picked)


def minutes_label(minute):
    return "%d:%02d" % (minute // 60, minute % 60)


def doctor_color(doctor):
    """Doctor color on the board: the one chosen on her form, otherwise a stable color by id.

    Accepts a record or a bare id (id = automatic color) so it can be called from anywhere."""
    if hasattr(doctor, "calendar_color"):
        if doctor.calendar_color:
            return doctor.calendar_color
        doctor = doctor.id
    return DOCTOR_COLORS[(doctor or 0) % len(DOCTOR_COLORS)]


def shift_bands(shifts):
    """Shifts in one room -> (shifts with `lane`, number of lanes, overlaps).

    `shifts` = [{"id", "from", "to", ...}]. Overlapping shifts get different
    lanes (side by side); overlaps = periods when several different doctors
    are on duty: [{"from", "to", "count", "label": "2 lékařky 10:00–14:00"}].
    """
    lane_ends = []   # end of the last shift in each lane
    for s in sorted(shifts, key=lambda x: (x["from"], x["to"])):
        lane = next((i for i, end in enumerate(lane_ends) if end <= s["from"]), None)
        if lane is None:
            lane = len(lane_ends)
            lane_ends.append(0)
        lane_ends[lane] = s["to"]
        s["lane"] = lane
    points = sorted({s["from"] for s in shifts} | {s["to"] for s in shifts})
    overlaps = []
    for f, t in zip(points, points[1:]):
        count = len({s["id"] for s in shifts if s["from"] <= f and t <= s["to"]})
        if count >= 2:
            if overlaps and overlaps[-1]["to"] == f and overlaps[-1]["count"] == count:
                overlaps[-1]["to"] = t
            else:
                overlaps.append({"from": f, "to": t, "count": count})
    for x in overlaps:
        x["label"] = "%d lékařky %s–%s" % (x["count"], minutes_label(x["from"]), minutes_label(x["to"]))
    return shifts, len(lane_ends), overlaps


class VetReservation(models.Model):
    """Reservations and blocks in one table so the board reads a single source.

    Overlaps are enforced here, not only in the availability engine: the engine
    suggests what to offer, but the write under the room lock has the final say.
    """

    _name = "elite.vet.reservation"
    _description = "Rezervace"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "start, id"

    name = fields.Char(compute="_compute_name", store=True)
    kind = fields.Selection([("reservation", "Rezervace"), ("block", "Blokace")], required=True, default="reservation")
    state = fields.Selection(STATES, string="Stav", required=True, default="confirmed", tracking=True, index=True)
    # Task 24: "Klinika" (was "Interně") - the word of the board legend and the list filters.
    source = fields.Selection([("web", "Web"), ("internal", "Klinika")], string="Zdroj", required=True,
                              default="internal")
    # Who booked it at the clinic: create_uid of internal users only. A web request is created by the
    # website's public user - shown as nobody, the source Web says where it came from.
    created_by_id = fields.Many2one("res.users", string="Založil(a)", compute="_compute_created_by_id",
                                    compute_sudo=True)
    room_id = fields.Many2one("elite.vet.room", string="Ordinace", ondelete="restrict", index=True, tracking=True)
    doctor_id = fields.Many2one("elite.vet.doctor", string="Lékařka", ondelete="set null", tracking=True)
    procedure_id = fields.Many2one("elite.vet.procedure", string="Úkon", ondelete="restrict", tracking=True)
    start = fields.Datetime(string="Začátek", required=True, index=True, tracking=True)
    stop = fields.Datetime(string="Konec", required=True, tracking=True)
    duration_minutes = fields.Integer(compute="_compute_duration", string="Minut")
    partner_id = fields.Many2one("res.partner", string="Klient", ondelete="set null", tracking=True)
    pet_id = fields.Many2one("elite.vet.pet", string="Mazlíček", ondelete="set null", domain="[('partner_id', '=', partner_id)]")
    contact_name = fields.Char(string="Jméno a příjmení")
    contact_email = fields.Char(string="E-mail")
    contact_phone = fields.Char(string="Telefon")
    pet_name = fields.Char(string="Jméno mazlíčka")
    pet_species = fields.Selection(SPECIES, string="Druh zvířete")
    problem = fields.Text(string="Popis problému")
    note = fields.Text(string="Interní poznámka")
    # Internal note (request 25. 10.): not translatable, the reason typed in any UI language is the
    # one everybody sees (it used to be stored only in the language of the user who typed it).
    block_reason = fields.Char(string="Důvod blokace")
    block_scope = fields.Selection(
        BLOCK_SCOPES, string="Druh blokace", default="full",
        help="Úplná: v tom čase nikdo nic nevytvoří (web ani recepce).\n"
             "Jen web: web v tom čase nenabízí termíny, recepce tam rezervaci vložit smí.")
    repeat_weekly_until = fields.Date(string="Opakovat týdně do", help="Jen u blokace: založí kopie na stejný den v týdnu až do tohoto data.")
    cancel_token = fields.Char(default=lambda self: uuid.uuid4().hex, index=True, copy=False)
    cancel_reason = fields.Selection([("client", "Klient"), ("clinic", "Klinika"), ("no_show", "Nedorazil")], string="Důvod zrušení")
    deposit_state = fields.Selection([("none", "Bez zálohy"), ("pending", "Čeká na zálohu"), ("paid", "Zaplaceno"), ("refunded", "Vráceno")], default="none", string="Záloha")
    transaction_id = fields.Many2one("payment.transaction", string="Platba", ondelete="set null")
    lang = fields.Char(string="Jazyk klienta", default="cs_CZ")
    color_hex = fields.Char(compute="_compute_color_hex")
    # Two-doctor procedure: a copy of the reservation in a second room (logic in second_room.py).
    linked_reservation_id = fields.Many2one("elite.vet.reservation", string="Společně s", copy=False, readonly=True,
                                 ondelete="set null",
                                 help="Druhá rezervace téhož zákroku v jiné ordinaci. Přesun a zrušení platí pro obě.")
    is_second_room = fields.Boolean(string="Druhá ordinace", copy=False, readonly=True,
                                    help="Kopie pro druhou lékařku. Klientovi se z ní neposílají e-maily.")

    _sql_constraints = [
        ("cancel_token_uniq", "unique(cancel_token)", "Token rezervace musí být jedinečný."),
        ("start_before_stop", "check(start < stop)", "Začátek musí být dřív než konec."),
    ]

    # ---------- compute ----------
    @api.model
    def _clinic_lang(self):
        """The reservation name and the board use the clinic language, not the language
        of whoever created the reservation (a client from the German site, an admin in English)."""
        installed = dict(self.env["res.lang"].get_installed())
        return "cs_CZ" if "cs_CZ" in installed else (self.env.lang or "en_US")

    @api.depends("kind", "contact_name", "partner_id.name", "pet_name", "pet_id.name", "procedure_id.name", "block_reason")
    def _compute_name(self):
        lang = self._clinic_lang()
        for rec in self:
            loc = rec.with_context(lang=lang)
            if rec.kind == "block":
                rec.name = loc.block_reason or loc.env._("Blokace")
                continue
            parts = [rec.partner_id.name or rec.contact_name or loc.env._("Bez jména"),
                     rec.pet_id.name or rec.pet_name or "", loc.procedure_id.name or ""]
            rec.name = " / ".join(p for p in parts if p)

    @api.depends("create_uid")
    def _compute_created_by_id(self):
        for rec in self:
            user = rec.create_uid
            rec.created_by_id = user if user and not user.share else False

    def _board_origin(self):
        """{source, created_by, created_by_initials, created_at} of a reservation for the boards.

        The second-room copy of a two-doctor procedure shows its main reservation (a web booking
        stays WEB in both rooms). The creator's name is read under sudo (internal users only)."""
        self.ensure_one()
        main = self.linked_reservation_id if self.is_second_room and self.linked_reservation_id else self
        user = main.sudo().created_by_id
        created_at = ""
        if main.create_date:
            local = pytz.utc.localize(main.create_date).astimezone(TZ)
            created_at = "%d. %d. %d %s" % (local.day, local.month, local.year, local.strftime("%H:%M"))
        return {"source": main.source, "created_by": user.name or "",
                "created_by_initials": name_initials(user.name) if user else "", "created_at": created_at}

    @api.depends("start", "stop")
    def _compute_duration(self):
        for rec in self:
            rec.duration_minutes = int((rec.stop - rec.start).total_seconds() // 60) if rec.start and rec.stop else 0

    @api.depends("kind", "procedure_id.color_hex")
    def _compute_color_hex(self):
        # The card has the procedure color; the doctor is shown by the left stripe (doctor_color on the board).
        for rec in self:
            if rec.kind == "block":
                rec.color_hex = "#64748b"
            else:
                rec.color_hex = rec.procedure_id.color_hex or "#64748b"

    @api.onchange("procedure_id", "start")
    def _onchange_stop(self):
        """Konec follows Začátek. Task 28: a saved reservation moved in the form keeps its own
        length (it may have been made longer or shorter); a new one / another procedure takes the
        procedure's duration. Konec can then be changed by hand."""
        if not (self.start and self.kind == "reservation"):
            return
        origin = self._origin
        if origin.start and origin.stop and origin.procedure_id == self.procedure_id:
            self.stop = self.start + (origin.stop - origin.start)
        elif self.procedure_id:
            self.stop = self.start + timedelta(minutes=self.procedure_id.duration)

    # ---------- overlaps ----------
    @api.model
    def _busy_domain(self, room_ids, start, stop, exclude_ids=None, scope="internal"):
        """Records that actually occupy rooms at the given time (confirmed + blocks).

        The single place defining what counts as busy:
        - scope="web" (public website): both block types, "web only" and full;
        - scope="internal" (reception, overlap check on write): full blocks only.
        """
        if scope not in ("web", "internal"):
            raise ValueError("scope must be 'web' or 'internal'")
        block_domain = ["&", ("kind", "=", "block"), ("state", "not in", INACTIVE_STATES)]
        if scope == "internal":
            block_domain = ["&"] + block_domain + [("block_scope", "=", "full")]
        domain = [
            ("start", "<", stop), ("stop", ">", start),
            # A block is busy until cancelled; a reservation only when confirmed / done.
            "|", *block_domain,
            "&", ("kind", "=", "reservation"), ("state", "in", BUSY_STATES),
            # Without a room only a block is busy (clinic-wide); a reservation without a room blocks nobody.
            "|", "&", ("room_id", "=", False), ("kind", "=", "block"), ("room_id", "in", list(room_ids)),
        ]
        if exclude_ids:
            domain.append(("id", "not in", list(exclude_ids)))
        return domain

    @api.model
    def _busy_external(self, room_ids, start, stop):
        """Entries outside this model that occupy rooms at the given time - the second half of the
        busy rule next to `_busy_domain` (extension point: elite_vet_winvet adds the timed events
        of the WinVet calendar). Returns a recordset of any model whose records have `start`,
        `stop`, `name` and `room_ids`; reservations only (blocks may be placed over them).
        Callers: availability.busy_minutes (web, chat, wizard, POS Objednat), _check_overlap
        (every save, board drop) and the wizard's manual-time collision check."""
        return self.browse()

    @api.constrains("kind", "state", "room_id")
    def _check_room_required(self):
        for rec in self:
            if rec.kind == "reservation" and rec.state in BUSY_STATES and not rec.room_id:
                raise ValidationError(_("Potvrzená rezervace musí mít ordinaci."))

    @api.model
    def _lock_rooms(self, room_ids):
        """Lock rooms against a double write of the same slot.

        Odoo runs on REPEATABLE READ: the snapshot is fixed by the first query of the
        transaction. SELECT ... FOR UPDATE alone is not enough: the second writer waits
        for the lock, but once it is released it looks for overlaps in its old snapshot
        and does not see the winner's reservation. PostgreSQL raises a serialization
        error only if the locked row was *modified*, so after locking we also do a dummy
        update of the room rows. The loser gets SerializationFailure, the request is
        retried with a fresh snapshot and _check_overlap then sees the winner's
        reservation. We always lock in id order so two writers cannot deadlock.
        """
        ids = sorted(set(room_ids)) or self.env["elite.vet.room"].search([]).ids
        if ids:
            cr = self.env.cr
            cr.execute("SELECT id FROM elite_vet_room WHERE id IN %s ORDER BY id FOR UPDATE", (tuple(ids),))
            cr.execute("UPDATE elite_vet_room SET write_date = write_date WHERE id IN %s", (tuple(ids),))

    def _after_web_submit(self):
        """Hook for e-mails after a web submission; implemented by task 11."""
        return True

    def _check_overlap(self):
        for rec in self:
            if rec.state in INACTIVE_STATES:
                continue
            all_rooms = self.env["elite.vet.room"].search([]).ids
            rooms = [rec.room_id.id] if rec.room_id else all_rooms
            if not rec.room_id and rec.kind == "reservation":
                continue   # a pending web request without a room is not placed anywhere yet
            if rec.kind == "block" and rec.block_scope == "web":
                continue   # a web-only block does not get in anyone's way; it can be created any time
            self._lock_rooms(rooms)
            clash = self.search(self._busy_domain(rooms, rec.start, rec.stop, exclude_ids=[rec.id]), limit=1)
            if not clash and rec.kind == "reservation":
                clash = self._busy_external(rooms, rec.start, rec.stop)[:1]
            if clash:
                raise ValidationError(_(
                    "Termín %s–%s v ordinaci %s je obsazený: %s."
                ) % (fields.Datetime.context_timestamp(rec, rec.start).strftime("%d.%m. %H:%M"),
                     fields.Datetime.context_timestamp(rec, rec.stop).strftime("%H:%M"),
                     rec.room_id.name or _("všechny"), clash.name))

    # ---------- block rights ----------
    @api.model
    def _can_edit_blocks(self):
        return self.env.su or self.env.user.has_group(BLOCK_MANAGER_GROUP)

    def _check_block_rights(self, vals=None):
        """Only Správce rezervací changes blocks. The record rules (security/rules.xml) say the same;
        this check runs first so the user gets a clear message instead of the generic one."""
        if self._can_edit_blocks():
            return
        if (vals and vals.get("kind") == "block") or any(rec.kind == "block" for rec in self):
            raise AccessError(_("Blokace může měnit jen správce rezervací."))

    # ---------- create / write ----------
    @api.model_create_multi
    def create(self, vals_list):
        # Before super(): its record rule check would answer first, with the generic message.
        # "Nová blokace" passes the kind as a context default (default_kind).
        default_kind = self.env.context.get("default_kind")
        for vals in vals_list:
            self._check_block_rights({"kind": vals.get("kind", default_kind)})
        for vals in vals_list:
            if vals.get("start") and not vals.get("stop"):
                proc = self.env["elite.vet.procedure"].browse(vals.get("procedure_id"))
                minutes = proc.duration if proc else 30
                vals["stop"] = fields.Datetime.to_datetime(vals["start"]) + timedelta(minutes=minutes)
        records = super().create(vals_list)
        records._check_block_rights()   # any other default of the kind
        # Copies of a repeated block are created from the original input (all rooms),
        # hence before splitting; each copy is then split according to its own week.
        records._repeat_weekly_blocks()
        records._split_all_rooms_block()
        records._check_overlap()
        return records

    def _split_all_rooms_block(self):
        """A full "all rooms" block over time that is already blocked.

        When some room already has its own (or another clinic-wide) full block at
        that time, the whole input is not rejected: the block is split per room and
        fills only the still-free periods. A confirmed reservation still prevents it -
        a block over a client would silently drop them from the board.
        """
        for rec in self.filtered(lambda r: r.kind == "block" and r.block_scope == "full"
                                 and not r.room_id and r.state not in INACTIVE_STATES):
            rooms = self.env["elite.vet.room"].search([])
            self._lock_rooms(rooms.ids)
            existing = self.search(self._busy_domain(rooms.ids, rec.start, rec.stop, exclude_ids=[rec.id]))
            if not existing:
                continue   # nothing there, keep a single clinic-wide block
            if existing.filtered(lambda r: r.kind == "reservation"):
                continue   # the reservation is reported by _check_overlap as before
            pieces = []
            for room in rooms:
                taken = sorted((max(b.start, rec.start), min(b.stop, rec.stop))
                               for b in existing if not b.room_id or b.room_id == room)
                cursor = rec.start
                for b_start, b_stop in taken:
                    if b_start > cursor:
                        pieces.append((room, cursor, b_start))
                    cursor = max(cursor, b_stop)
                if cursor < rec.stop:
                    pieces.append((room, cursor, rec.stop))
            if not pieces:
                raise ValidationError(self.env._("Ve všech ordinacích už je v tomto čase úplná blokace."))
            (room, start, stop), rest = pieces[0], pieces[1:]
            rec.write({"room_id": room.id, "start": start, "stop": stop})
            if rest:
                self.create([{
                    "kind": "block", "state": rec.state, "block_reason": rec.block_reason,
                    "block_scope": "full", "note": rec.note,
                    "room_id": r.id, "start": s, "stop": e} for r, s, e in rest])

    def write(self, vals):
        self._check_block_rights(vals)
        res = super().write(vals)
        if {"start", "stop", "room_id", "state", "kind", "block_scope"} & set(vals):
            self._check_overlap()
        return res

    def unlink(self):
        self._check_block_rights()
        return super().unlink()

    def _repeat_weekly_blocks(self):
        """Weekly block repetition = materialized copies, no rrule."""
        for rec in self.filtered(lambda r: r.kind == "block" and r.repeat_weekly_until):
            until = rec.repeat_weekly_until
            rec.repeat_weekly_until = False
            # Shift by weeks in local time so 12:00 stays 12:00 across daylight-saving changes.
            tz_start = pytz.utc.localize(rec.start).astimezone(TZ).replace(tzinfo=None)
            tz_stop = pytz.utc.localize(rec.stop).astimezone(TZ).replace(tzinfo=None)
            vals_list = []
            for i in range(1, 53):
                shift = timedelta(days=7 * i)
                if (tz_start + shift).date() > until:
                    break
                vals_list.append({
                    "kind": "block", "block_reason": rec.block_reason, "block_scope": rec.block_scope,
                    "room_id": rec.room_id.id, "note": rec.note,
                    "start": TZ.localize(tz_start + shift).astimezone(pytz.utc).replace(tzinfo=None),
                    "stop": TZ.localize(tz_stop + shift).astimezone(pytz.utc).replace(tzinfo=None)})
            if vals_list:
                self.create(vals_list)

    # ---------- actions ----------
    def action_confirm(self):
        for rec in self:
            if rec.kind != "reservation":
                continue
            if not rec.room_id:
                raise UserError(_("Vyberte ordinaci, do které rezervaci zapsat."))
            if rec.state not in ("web_new", "confirmed"):
                raise UserError(_("Potvrdit jde jen čekající rezervaci."))
            if not rec.partner_id:
                rec.action_match_client()
            rec.write({"state": "confirmed"})

    def action_cancel(self, reason="clinic"):
        self.write({"state": "cancelled", "cancel_reason": reason})

    def action_done(self):
        self.write({"state": "done"})

    def action_no_show(self):
        self.write({"state": "no_show", "cancel_reason": "no_show"})

    def action_reschedule(self, start, room_id=None, doctor_id=None, stop=None):
        """New start (+ room / doctor). `stop` (task 28): the new end; without it the duration is kept."""
        self.ensure_one()
        start = fields.Datetime.to_datetime(start)
        stop = fields.Datetime.to_datetime(stop) if stop else start + (self.stop - self.start)
        if stop <= start:
            raise UserError(_("Konec musí být po začátku."))
        vals = {"start": start, "stop": stop}
        if room_id:
            vals["room_id"] = room_id
        if doctor_id is not None:
            vals["doctor_id"] = doctor_id or False
        self.write(vals)

    def action_match_client(self):
        """Find / create the client and the pet from the data submitted on the website."""
        Partner = self.env["res.partner"]
        Pet = self.env["elite.vet.pet"]
        for rec in self:
            if not rec.partner_id:
                rec.partner_id = Partner.find_or_create_client(rec.contact_name, rec.contact_email, rec.contact_phone)
            if not rec.pet_id and rec.pet_name:
                rec.pet_id = Pet.find_or_create(rec.partner_id, rec.pet_name, rec.pet_species)

    # ---------- board ----------
    @api.model
    def board_data(self, day_str):
        day = fields.Date.from_string(day_str)
        A = self.env["elite.vet.availability"]
        s = self.env["elite.vet.setting"].nastaveni()
        lang = self._clinic_lang()
        rooms = self.env["elite.vet.room"].search([])
        start, stop = A.local_to_utc(day, 0), A.local_to_utc(day, 1440)
        assignments = self.env["elite.vet.doctor.assignment"].search([("date", "=", day)])
        rooms_out, axis_from, axis_to = [], 8 * 60, 20 * 60
        for room in rooms:
            open_iv = A.open_minutes(room, day)
            for f, t in open_iv:
                axis_from, axis_to = min(axis_from, f), max(axis_to, t)
            # Doctor shifts = vertical bands on the left of the column; two concurrent doctors side by side.
            shifts, lanes, overlaps = shift_bands([
                {"id": a.id, "doctor_id": a.doctor_id.id, "name": a.doctor_id.name,
                 "initials": name_initials(a.doctor_id.name), "color": doctor_color(a.doctor_id),
                 "from": int(round(a.hour_from * 60)), "to": int(round(a.hour_to * 60)),
                 "from_roster": bool(a.shift_id), "shift_id": a.shift_id.id or False}
                for a in assignments if a.room_id == room])
            for d in shifts:
                d["time_label"] = "%s–%s" % (minutes_label(d["from"]), minutes_label(d["to"]))
            rooms_out.append({
                "id": room.id, "name": room.name, "color_hex": room.color_hex, "online": room.online,
                "open": [[f, t] for f, t in open_iv],
                "doctors": shifts, "lanes": lanes, "overlaps": overlaps,
            })
        events = []
        for r in self.search([("start", "<", stop), ("stop", ">", start),
                              "|", "&", ("kind", "=", "block"), ("state", "not in", INACTIVE_STATES),
                              ("state", "in", ("confirmed", "done", "no_show"))]):
            ev_start, ev_end = A.utc_to_local_minutes(r.start, day), A.utc_to_local_minutes(r.stop, day)
            events.append({
                "id": r.id, "name": r.name, "kind": r.kind, "state": r.state,
                "block_scope": r.block_scope if r.kind == "block" else False,
                "room_id": r.room_id.id or False,
                "start": ev_start, "end": ev_end,
                "time_label": "%s–%s" % (minutes_label(ev_start), minutes_label(ev_end)),
                "pet": r.pet_id.name or r.pet_name or "",
                "owner": r.partner_id.name or r.contact_name or "",
                "color_hex": r.color_hex, "symbol": r.procedure_id.symbol or "",
                "phone": r.contact_phone or r.partner_id.phone or "", "email": r.contact_email or r.partner_id.email or "",
                "problem": r.problem or "", "procedure": r.procedure_id.with_context(lang=lang).name or "",
                "doctor": r.doctor_id.name or "", "doctor_initials": name_initials(r.doctor_id.name),
                "doctor_color": doctor_color(r.doctor_id) if r.doctor_id else False,
                "linked": r._linked_label(),
                # Task 24: WEB / Klinika (initials of who booked it) on the card; for blocks only "source".
                **(r._board_origin() if r.kind == "reservation" else {"source": r.source}),
                # Request 25. 10.: the drop asks first; it says whether the client gets an e-mail
                # about the new time (mailing.write: a confirmed reservation with a contact e-mail).
                "mail_on_move": r._mail_on_move(),
            })
        waiting = []
        for w in self.search([("state", "=", "web_new"), ("stop", ">=", fields.Datetime.now())], order="start"):
            # Clinic local time (module TZ), not the logged-in user's tz - that may not be set.
            local = pytz.utc.localize(w.start).astimezone(TZ)
            waiting.append({
                "id": w.id, "name": w.name, "date": local.strftime("%Y-%m-%d"), "time": local.strftime("%H:%M"),
                "minute": local.hour * 60 + local.minute,
                "date_label": "%s %d. %d. %s" % (WEEKDAY_ABBR[local.weekday()], local.day, local.month,
                                                 local.strftime("%H:%M")),
                "procedure": w.procedure_id.with_context(lang=lang).name or "", "duration": w.duration_minutes,
                "phone": w.contact_phone or "", "email": w.contact_email or "", "problem": w.problem or "",
                "doctor": w.doctor_id.name or "",
                # for the question before confirming (board.js confirmQuestion)
                "pet": w.pet_id.name or w.pet_name or "", "owner": w.partner_id.name or w.contact_name or "",
                "past": w.start <= fields.Datetime.now(),
                # Suggestions computed here: one request per board refresh, not one per card.
                "suggestions": w.board_suggestions(w.id),
            })
        return {"date": day_str, "step": s.booking_slot_step,
                # Rozpis služeb managers edit shifts from the board (click on a doctor, + Služba)
                "can_edit_shifts": self.env.user.has_group("elite_vet_calendar.group_calendar_manager"),
                # Nová blokace, dragging and editing blocks: Správce rezervací only
                "can_edit_blocks": self._can_edit_blocks(),
                "axis": {"from": axis_from, "to": axis_to},
                "rooms": rooms_out, "events": events, "waiting": waiting,
                # Weekend / public holiday when the website does not book (label only; reception still books).
                "day_note": A.web_day_note(day) or "",
                # Public holiday of the day (always, also when the website books): badge in the day header.
                "holiday": self._board_holiday(day, s),
                # {"YYYY-MM-DD": name} of the holidays of the shown week (Mon-Sun): the weekday chips.
                "week_holidays": self._week_holidays(day)}

    @api.model
    def _board_holiday(self, day, settings=None):
        """{name, label, web_closed} of a public holiday on `day`, otherwise False.

        Reception is only warned, never blocked (the clinic works nights and weekends);
        `web_closed` = the website does not book on holidays (setting booking_block_holidays)."""
        name = holiday_name(day)
        if not name:
            return False
        settings = settings or self.env["elite.vet.setting"].nastaveni()
        web_closed = bool(settings.booking_block_holidays)
        label = "Státní svátek: %s" % name
        return {"name": name, "web_closed": web_closed,
                "label": label + (" · web neobjednává" if web_closed else "")}

    @api.model
    def _week_holidays(self, day):
        monday = day - timedelta(days=day.weekday())
        out = {}
        for offset in range(7):
            current = monday + timedelta(days=offset)
            name = holiday_name(current)
            if name:
                out[current.isoformat()] = name
        return out

    @api.model
    def board_suggestions(self, res_id):
        """Where a pending request can be confirmed at exactly the requested time.

        Rooms where the time is free and a doctor who does the procedure is on duty
        (or the one the client chose). Doctor = the chosen one, otherwise the first on duty.
        A procedure that does not need a doctor (same rule as in slots) is also
        offered in a room with no shift - without a doctor.
        """
        rec = self.browse(res_id).exists()
        if not rec or rec.kind != "reservation" or not rec.procedure_id or rec.state != "web_new":
            return []
        A = self.env["elite.vet.availability"]
        proc = rec.procedure_id
        local = pytz.utc.localize(rec.start).astimezone(TZ)
        day, minute = local.date(), local.hour * 60 + local.minute
        doctor = rec.doctor_id or None
        # Reception may confirm a request closer than the website's "minimum hours ahead":
        # min_hours=0 keeps everything that has not started yet.
        # scope="internal": web-only blocks, weekends and holidays do not restrict reception.
        slot = next((x for x in A.slots(proc, day, doctor=doctor, min_hours=0, max_days=RECEPTION_HORIZON_DAYS,
                                        scope="internal")
                     if x["minute"] == minute), None)
        if not slot:
            return []
        Room, Doctor = self.env["elite.vet.room"], self.env["elite.vet.doctor"]
        out = []
        for room_id, doc_id in A.room_doctors(proc, day, slot, doctor):
            doc = Doctor.browse(doc_id)
            out.append({"room_id": room_id, "room": Room.browse(room_id).name,
                        "doctor_id": doc.id or False, "doctor": doc.name or ""})
        return out

    @api.model
    def board_slot_utc(self, day_str, minute):
        A = self.env["elite.vet.availability"]
        return fields.Datetime.to_string(A.local_to_utc(fields.Date.from_string(day_str), int(minute)))

    def _board_doctor_check(self, day_str, minute, room_id, doctor=None, strict=True, duration=None):
        """May the reservation go on the board into room `room_id` at `minute`?

        Same rule as suggestions and the wizard: a doctor who does the procedure
        (with `strict`, exactly `doctor`) must be on duty in the room for the whole
        procedure if the procedure needs a doctor; the room must be one of the
        procedure's reception rooms. Collisions are checked on write (_check_overlap).
        Returns the doctor id to set (the only one on duty), False = clear, None = keep.
        `duration` (minutes, task 28: a new end chosen in the move dialog) replaces the procedure's
        duration for the "on duty for the whole time" rule.
        """
        self.ensure_one()
        proc = self.procedure_id
        if self.kind != "reservation" or not proc or not room_id:
            return None
        A = self.env["elite.vet.availability"]
        day, minute = fields.Date.from_string(day_str), int(minute)
        room = self.env["elite.vet.room"].browse(room_id)
        proc_name = proc.with_context(lang=self._clinic_lang()).name
        if room not in proc.rooms_for_reception():
            raise UserError(_("Úkon %s se v %s nedělá.") % (proc_name, room.name))
        wanted = doctor if strict else None
        doc_ids = A.serving_doctors(proc, day, room.id, minute, wanted or None, duration=duration)
        if not doc_ids and A.need_doctor(proc, wanted or None):
            if wanted:
                raise UserError(_("V %s v %s neslouží %s.") % (minutes_label(minute), room.name, wanted.name))
            raise UserError(_("V %s v %s neslouží lékařka, která dělá %s.")
                            % (minutes_label(minute), room.name, proc_name))
        if doctor and doctor.id in doc_ids:
            return None
        if len(doc_ids) == 1:
            return doc_ids[0]
        # The original doctor is not on duty at the new time/room: do not leave a wrong name.
        return False if doctor else None

    @api.model
    def _board_interval(self, day_str, minute, end_minute):
        """(start, stop or None, duration or None) in UTC for the board methods; `end_minute`
        (minutes from midnight of the same day, task 28) must be after `minute`."""
        minute = int(minute)
        if end_minute in (None, False, ""):
            return self.board_slot_utc(day_str, minute), None, None
        try:
            end_minute = int(end_minute)
        except (TypeError, ValueError):
            raise UserError(_("Neplatný čas konce: %s") % end_minute) from None
        if not minute < end_minute <= 1440:
            raise UserError(_("Konec musí být po začátku."))
        return (self.board_slot_utc(day_str, minute), self.board_slot_utc(day_str, end_minute),
                end_minute - minute)

    @api.model
    def board_move(self, res_id, day_str, minute, room_id, notify=True, end_minute=None):
        """Move on the board. A reservation only where a doctor who does the procedure is on duty
        (if the current doctor has no shift at the new place, she is replaced); a block anywhere.
        notify=False (task 25, the dialog's e-mail checkbox unticked): no e-mail about the new time,
        a chatter note instead. end_minute (task 28): the new end on that day; without it the
        duration is kept. The collision and on-duty rules apply to the whole new interval."""
        rec = self.browse(res_id)
        if not notify:
            rec = rec.with_context(ev_no_reschedule_mail=True)
        start, stop, duration = self._board_interval(day_str, minute, end_minute)
        doctor_id = rec._board_doctor_check(day_str, minute, room_id or rec.room_id.id,
                                            doctor=rec.doctor_id, strict=False, duration=duration)
        rec.action_reschedule(start, room_id=room_id or None, doctor_id=doctor_id, stop=stop)
        return True

    def _mail_on_move(self):
        """E-mail address the client is told about a new time at (moving changes the time),
        or False. The second-room copy tells the client through its main reservation."""
        self.ensure_one()
        main = self.linked_reservation_id if self.is_second_room and self.linked_reservation_id else self
        if self.kind != "reservation" or self.state != "confirmed" or main.state != "confirmed":
            return False
        return main.contact_email or False

    @api.model
    def board_confirm(self, res_id, day_str, minute, room_id, doctor_id=None, notify=True, end_minute=None):
        """doctor_id=None keeps the doctor; a number sets it (suggestion from the Waiting panel).
        Checks that a doctor who does the procedure (or the one the client chose) is on
        duty at that time and room; if only one is on duty, she is set.
        notify=False (task 25): no confirmation e-mail, a chatter note instead.
        end_minute (task 28): the end chosen in the dialog (otherwise the duration is kept)."""
        rec = self.browse(res_id)
        if not notify:
            rec = rec.with_context(ev_no_mail=True, ev_no_confirm_mail_note=True)
        doctor = self.env["elite.vet.doctor"].browse(doctor_id) if doctor_id else rec.doctor_id
        start, stop, duration = self._board_interval(day_str, minute, end_minute)
        found = rec._board_doctor_check(day_str, minute, room_id, doctor=doctor, duration=duration)
        if doctor_id:
            found = doctor_id
        rec.action_reschedule(start, room_id=room_id, doctor_id=found, stop=stop)
        rec.action_confirm()
        return True
