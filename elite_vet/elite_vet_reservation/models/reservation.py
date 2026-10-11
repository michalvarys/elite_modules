import uuid
from datetime import timedelta

import pytz

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

from .pet import SPECIES

STATES = [
    ("web_new", "Čekající z webu"), ("confirmed", "Potvrzená"), ("done", "Proběhla"),
    ("cancelled", "Zrušená"), ("no_show", "Nedorazil"),
]
BUSY_STATES = ("confirmed", "done")
INACTIVE_STATES = ("cancelled", "no_show")
# Ordinacni cas kliniky; nesmi zalezet na casove zone prave jednajiciho uzivatele (cron, sudo, web).
TZ = pytz.timezone("Europe/Prague")
# České názvy dnů natvrdo: nesmí záviset na jazyce uživatele ani prohlížeče.
DNY_KRATCE = ["po", "út", "st", "čt", "pá", "so", "ne"]
# Recepce objednává i daleko dopředu (očkování za rok); web má vlastní horizont v nastavení.
HORIZONT_RECEPCE = 400
# Druh blokace: „jen web“ zavře čas jen pro online objednávky, „úplná“ pro všechny.
BLOCK_SCOPES = [("web", "Jen web"), ("full", "Úplná")]
# Stabilní barvy lékařek na tabuli (podle id), dobře čitelné s bílým písmem.
BARVY_LEKAREK = ["#7c3aed", "#db2777", "#ea580c", "#0891b2", "#4d7c0f", "#b45309", "#2563eb", "#be123c"]
TITULY = {"mvdr.", "mudr.", "dr.", "ing.", "bc.", "mgr.", "phd.", "dipl.", "ph.d."}


def inicialy(jmeno):
    """„MVDr. Dana Pokorná“ -> „DP“ (tituly a zkratky s tečkou se přeskočí)."""
    slova = [w for w in (jmeno or "").replace(",", " ").split()
             if w.lower() not in TITULY and not w.endswith(".")]
    if not slova:
        return ""
    vyber = [slova[0], slova[-1]] if len(slova) > 1 else slova[:1]
    return "".join(w[0].upper() for w in vyber)


def cas_label(minuta):
    return "%d:%02d" % (minuta // 60, minuta % 60)


def barva_lekarky(doctor):
    """Barva lékařky na tabuli: vybraná na její kartě, jinak stálá barva podle id.

    Bere záznam i samotné id (id = automatická barva), aby šla volat odkudkoli."""
    if hasattr(doctor, "barva"):
        if doctor.barva:
            return doctor.barva
        doctor = doctor.id
    return BARVY_LEKAREK[(doctor or 0) % len(BARVY_LEKAREK)]


def pruhy_sluzeb(sluzby):
    """Služby v jedné ordinaci -> (sluzby s `lane`, počet pruhů, souběhy).

    `sluzby` = [{"id", "from", "to", ...}]. Překrývající se služby dostanou
    různé pruhy (vedle sebe), souběhy = úseky, kdy slouží víc různých lékařek:
    [{"from", "to", "count", "label": "2 lékařky 10:00–14:00"}].
    """
    konce = []   # konec poslední služby v každém pruhu
    for s in sorted(sluzby, key=lambda x: (x["from"], x["to"])):
        lane = next((i for i, konec in enumerate(konce) if konec <= s["from"]), None)
        if lane is None:
            lane = len(konce)
            konce.append(0)
        konce[lane] = s["to"]
        s["lane"] = lane
    body = sorted({s["from"] for s in sluzby} | {s["to"] for s in sluzby})
    soubehy = []
    for f, t in zip(body, body[1:]):
        pocet = len({s["id"] for s in sluzby if s["from"] <= f and t <= s["to"]})
        if pocet >= 2:
            if soubehy and soubehy[-1]["to"] == f and soubehy[-1]["count"] == pocet:
                soubehy[-1]["to"] = t
            else:
                soubehy.append({"from": f, "to": t, "count": pocet})
    for x in soubehy:
        x["label"] = "%d lékařky %s–%s" % (x["count"], cas_label(x["from"]), cas_label(x["to"]))
    return sluzby, len(konce), soubehy


class VetReservation(models.Model):
    """Rezervace i blokace v jedne tabulce, aby tabule cetla jeden zdroj.

    Prekryv se hlida tady, ne jen v enginu dostupnosti: engine radi, co nabidnout,
    ale posledni slovo ma zapis pod zamkem ordinace.
    """

    _name = "elite.vet.reservation"
    _description = "Rezervace"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "start, id"

    name = fields.Char(compute="_compute_name", store=True)
    kind = fields.Selection([("reservation", "Rezervace"), ("block", "Blokace")], required=True, default="reservation")
    state = fields.Selection(STATES, string="Stav", required=True, default="confirmed", tracking=True, index=True)
    source = fields.Selection([("web", "Web"), ("internal", "Interně")], string="Zdroj", required=True, default="internal")
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
    block_reason = fields.Char(string="Důvod blokace", translate=True)
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

    _sql_constraints = [
        ("cancel_token_uniq", "unique(cancel_token)", "Token rezervace musí být jedinečný."),
        ("start_before_stop", "check(start < stop)", "Začátek musí být dřív než konec."),
    ]

    # ---------- compute ----------
    @api.model
    def _jazyk_kliniky(self):
        """Název rezervace a tabule mluví jazykem kliniky, ne jazykem toho, kdo
        rezervaci založil (klient z německého webu, správce v angličtině)."""
        installed = dict(self.env["res.lang"].get_installed())
        return "cs_CZ" if "cs_CZ" in installed else (self.env.lang or "en_US")

    @api.depends("kind", "contact_name", "partner_id.name", "pet_name", "pet_id.name", "procedure_id.name", "block_reason")
    def _compute_name(self):
        lang = self._jazyk_kliniky()
        for rec in self:
            loc = rec.with_context(lang=lang)
            if rec.kind == "block":
                rec.name = loc.block_reason or loc.env._("Blokace")
                continue
            parts = [rec.partner_id.name or rec.contact_name or loc.env._("Bez jména"),
                     rec.pet_id.name or rec.pet_name or "", loc.procedure_id.name or ""]
            rec.name = " / ".join(p for p in parts if p)

    @api.depends("start", "stop")
    def _compute_duration(self):
        for rec in self:
            rec.duration_minutes = int((rec.stop - rec.start).total_seconds() // 60) if rec.start and rec.stop else 0

    @api.depends("kind", "procedure_id.color_hex")
    def _compute_color_hex(self):
        # Karta má barvu úkonu; lékařku ukazuje proužek vlevo (doctor_color na tabuli).
        for rec in self:
            if rec.kind == "block":
                rec.color_hex = "#64748b"
            else:
                rec.color_hex = rec.procedure_id.color_hex or "#64748b"

    @api.onchange("procedure_id", "start")
    def _onchange_stop(self):
        if self.start and self.procedure_id and self.kind == "reservation":
            self.stop = self.start + timedelta(minutes=self.procedure_id.duration)

    # ---------- prekryvy ----------
    @api.model
    def _busy_domain(self, room_ids, start, stop, exclude_ids=None, scope="internal"):
        """Záznamy, které v daném čase opravdu blokují ordinace (potvrzené + blokace).

        Jediné místo s pravidlem, co je obsazené:
        - scope="web" (veřejný web): obě blokace, „jen web“ i úplná;
        - scope="internal" (recepce, kontrola překryvu při zápisu): jen úplná blokace.
        """
        if scope not in ("web", "internal"):
            raise ValueError("scope musí být 'web' nebo 'internal'")
        blokace = ["&", ("kind", "=", "block"), ("state", "not in", INACTIVE_STATES)]
        if scope == "internal":
            blokace = ["&"] + blokace + [("block_scope", "=", "full")]
        domain = [
            ("start", "<", stop), ("stop", ">", start),
            # Blokace blokuje, dokud neni zrusena; rezervace jen potvrzena / proběhla.
            "|", *blokace,
            "&", ("kind", "=", "reservation"), ("state", "in", BUSY_STATES),
            # Bez ordinace blokuje jen blokace (celoklinicka); rezervace bez ordinace nikoho neblokuje.
            "|", "&", ("room_id", "=", False), ("kind", "=", "block"), ("room_id", "in", list(room_ids)),
        ]
        if exclude_ids:
            domain.append(("id", "not in", list(exclude_ids)))
        return domain

    @api.constrains("kind", "state", "room_id")
    def _check_room_required(self):
        for rec in self:
            if rec.kind == "reservation" and rec.state in BUSY_STATES and not rec.room_id:
                raise ValidationError(_("Potvrzená rezervace musí mít ordinaci."))

    @api.model
    def _lock_rooms(self, room_ids):
        """Zamek ordinaci proti dvojimu zapisu stejneho slotu.

        Odoo bezi na REPEATABLE READ: snapshot se zafixuje prvnim dotazem transakce.
        Samotny SELECT ... FOR UPDATE nestaci: druhy zapis na zamek pocka, po jeho
        uvolneni ale hleda prekryv ve starem snapshotu a vitezovu rezervaci nevidi.
        PostgreSQL vyhodi chybu serializace az kdyz byl zamceny radek *zmenen*, proto
        radky ordinaci po zamceni i fiktivne updatujeme. Porazeny dostane
        SerializationFailure, request ho zopakuje s novym snapshotem a _check_overlap
        uz vitezovu rezervaci uvidi. Zamykame vzdy podle id, aby se dva zapisy
        nezablokovaly navzajem.
        """
        ids = sorted(set(room_ids)) or self.env["elite.vet.room"].search([]).ids
        if ids:
            cr = self.env.cr
            cr.execute("SELECT id FROM elite_vet_room WHERE id IN %s ORDER BY id FOR UPDATE", (tuple(ids),))
            cr.execute("UPDATE elite_vet_room SET write_date = write_date WHERE id IN %s", (tuple(ids),))

    def _po_prijeti_z_webu(self):
        """Hacek pro e-maily po prijeti z webu; naplni ho ukol 11."""
        return True

    def _check_overlap(self):
        for rec in self:
            if rec.state in INACTIVE_STATES:
                continue
            all_rooms = self.env["elite.vet.room"].search([]).ids
            rooms = [rec.room_id.id] if rec.room_id else all_rooms
            if not rec.room_id and rec.kind == "reservation":
                continue   # cekajici z webu bez ordinace se zatim nikam nepise
            if rec.kind == "block" and rec.block_scope == "web":
                continue   # blokace jen pro web nikomu nebrání, jde založit kdykoli
            self._lock_rooms(rooms)
            clash = self.search(self._busy_domain(rooms, rec.start, rec.stop, exclude_ids=[rec.id]), limit=1)
            if clash:
                raise ValidationError(_(
                    "Termín %s–%s v ordinaci %s je obsazený: %s."
                ) % (fields.Datetime.context_timestamp(rec, rec.start).strftime("%d.%m. %H:%M"),
                     fields.Datetime.context_timestamp(rec, rec.stop).strftime("%H:%M"),
                     rec.room_id.name or _("všechny"), clash.name))

    # ---------- create / write ----------
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("start") and not vals.get("stop"):
                proc = self.env["elite.vet.procedure"].browse(vals.get("procedure_id"))
                minutes = proc.duration if proc else 30
                vals["stop"] = fields.Datetime.to_datetime(vals["start"]) + timedelta(minutes=minutes)
        records = super().create(vals_list)
        # Kopie opakovane blokace se zakladaji z puvodniho zadani (vsechny ordinace),
        # proto pred rozdelenim; kazda kopie se pak rozdeli podle sveho tydne.
        records._rozkopirovat_blokace()
        records._rozdelit_blokaci_vsech_ordinaci()
        records._check_overlap()
        return records

    def _rozdelit_blokaci_vsech_ordinaci(self):
        """Úplná blokace „všechny ordinace“ přes už zablokovaný čas.

        Když některá ordinace má v tom čase vlastní (nebo jinou celoklinickou)
        úplnou blokaci, nezamítáme celé zadání: blokace se rozpadne po ordinacích
        a doplní jen ještě volné úseky. Potvrzená rezervace ale dál brání –
        blokace přes klienta by ho tiše vyřadila z tabule.
        """
        for rec in self.filtered(lambda r: r.kind == "block" and r.block_scope == "full"
                                 and not r.room_id and r.state not in INACTIVE_STATES):
            rooms = self.env["elite.vet.room"].search([])
            self._lock_rooms(rooms.ids)
            existing = self.search(self._busy_domain(rooms.ids, rec.start, rec.stop, exclude_ids=[rec.id]))
            if not existing:
                continue   # nic tam neni, zustane jedna blokace pro celou kliniku
            if existing.filtered(lambda r: r.kind == "reservation"):
                continue   # rezervaci nahlasi _check_overlap jako dosud
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
        res = super().write(vals)
        if {"start", "stop", "room_id", "state", "kind", "block_scope"} & set(vals):
            self._check_overlap()
        return res

    def _rozkopirovat_blokace(self):
        """Tydenni opakovani blokace = materializovane kopie, zadne rrule."""
        for rec in self.filtered(lambda r: r.kind == "block" and r.repeat_weekly_until):
            until = rec.repeat_weekly_until
            rec.repeat_weekly_until = False
            # Posun po tydnech v mistnim case, aby 12:00 zustalo 12:00 i pres zmenu letniho/zimniho casu.
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

    # ---------- akce ----------
    def action_confirm(self):
        for rec in self:
            if rec.kind != "reservation":
                continue
            if not rec.room_id:
                raise UserError(_("Vyberte ordinaci, do které rezervaci zapsat."))
            if rec.state not in ("web_new", "confirmed"):
                raise UserError(_("Potvrdit jde jen čekající rezervaci."))
            if not rec.partner_id:
                rec.action_sparovat()
            rec.write({"state": "confirmed"})

    def action_cancel(self, reason="clinic"):
        self.write({"state": "cancelled", "cancel_reason": reason})

    def action_done(self):
        self.write({"state": "done"})

    def action_no_show(self):
        self.write({"state": "no_show", "cancel_reason": "no_show"})

    def action_reschedule(self, start, room_id=None, doctor_id=None):
        self.ensure_one()
        start = fields.Datetime.to_datetime(start)
        vals = {"start": start, "stop": start + (self.stop - self.start)}
        if room_id:
            vals["room_id"] = room_id
        if doctor_id is not None:
            vals["doctor_id"] = doctor_id or False
        self.write(vals)

    def action_sparovat(self):
        """Najde / zalozi klienta a mazlicka podle toho, co prislo z webu."""
        Partner = self.env["res.partner"]
        Pet = self.env["elite.vet.pet"]
        for rec in self:
            if not rec.partner_id:
                rec.partner_id = Partner.najit_nebo_zalozit_klienta(rec.contact_name, rec.contact_email, rec.contact_phone)
            if not rec.pet_id and rec.pet_name:
                rec.pet_id = Pet.najit_nebo_zalozit(rec.partner_id, rec.pet_name, rec.pet_species)

    # ---------- tabule ----------
    @api.model
    def board_data(self, day_str):
        day = fields.Date.from_string(day_str)
        A = self.env["elite.vet.availability"]
        s = self.env["elite.vet.setting"].nastaveni()
        lang = self._jazyk_kliniky()
        rooms = self.env["elite.vet.room"].search([])
        start, stop = A.local_to_utc(day, 0), A.local_to_utc(day, 1440)
        assignments = self.env["elite.vet.doctor.assignment"].search([("date", "=", day)])
        rooms_out, axis_from, axis_to = [], 8 * 60, 20 * 60
        for room in rooms:
            open_iv = A.open_minutes(room, day)
            for f, t in open_iv:
                axis_from, axis_to = min(axis_from, f), max(axis_to, t)
            # Služby lékařek = svislé pruhy vlevo ve sloupci; souběh dvou lékařek vedle sebe.
            sluzby, lanes, soubehy = pruhy_sluzeb([
                {"id": a.id, "doctor_id": a.doctor_id.id, "name": a.doctor_id.name,
                 "initials": inicialy(a.doctor_id.name), "color": barva_lekarky(a.doctor_id),
                 "from": int(round(a.hour_from * 60)), "to": int(round(a.hour_to * 60))}
                for a in assignments if a.room_id == room])
            for d in sluzby:
                d["time_label"] = "%s–%s" % (cas_label(d["from"]), cas_label(d["to"]))
            rooms_out.append({
                "id": room.id, "name": room.name, "color_hex": room.color_hex, "online": room.online,
                "open": [[f, t] for f, t in open_iv],
                "doctors": sluzby, "lanes": lanes, "overlaps": soubehy,
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
                "time_label": "%s–%s" % (cas_label(ev_start), cas_label(ev_end)),
                "pet": r.pet_id.name or r.pet_name or "",
                "owner": r.partner_id.name or r.contact_name or "",
                "color_hex": r.color_hex, "symbol": r.procedure_id.symbol or "",
                "phone": r.contact_phone or r.partner_id.phone or "", "email": r.contact_email or r.partner_id.email or "",
                "problem": r.problem or "", "procedure": r.procedure_id.with_context(lang=lang).name or "",
                "doctor": r.doctor_id.name or "", "doctor_initials": inicialy(r.doctor_id.name),
                "doctor_color": barva_lekarky(r.doctor_id) if r.doctor_id else False,
                "source": r.source,
            })
        waiting = []
        for w in self.search([("state", "=", "web_new"), ("stop", ">=", fields.Datetime.now())], order="start"):
            # Mistni cas ordinace (TZ modulu), ne tz prihlaseneho uzivatele - ten nemusi byt nastaven.
            local = pytz.utc.localize(w.start).astimezone(TZ)
            waiting.append({
                "id": w.id, "name": w.name, "date": local.strftime("%Y-%m-%d"), "time": local.strftime("%H:%M"),
                "minute": local.hour * 60 + local.minute,
                "date_label": "%s %d. %d. %s" % (DNY_KRATCE[local.weekday()], local.day, local.month,
                                                 local.strftime("%H:%M")),
                "procedure": w.procedure_id.with_context(lang=lang).name or "", "duration": w.duration_minutes,
                "phone": w.contact_phone or "", "email": w.contact_email or "", "problem": w.problem or "",
                "doctor": w.doctor_id.name or "",
                "past": w.start <= fields.Datetime.now(),
                # Navrhy rovnou tady: jeden dotaz na obnovu tabule, ne jeden za kazdou kartu.
                "suggestions": w.board_suggestions(w.id),
            })
        return {"date": day_str, "step": s.booking_slot_step, "axis": {"from": axis_from, "to": axis_to},
                "rooms": rooms_out, "events": events, "waiting": waiting,
                # Víkend / státní svátek, kdy web neobjednává (jen štítek; recepce objednává dál).
                "day_note": A.web_day_note(day) or ""}

    @api.model
    def board_suggestions(self, res_id):
        """Kam jde čekající žádost potvrdit přesně v požadovaném čase.

        Ordinace, kde je čas volný a slouží lékařka, která úkon dělá (nebo ta,
        kterou si klient vybral). Lékařka = vybraná, jinak první sloužící.
        Úkon, který lékařku nepotřebuje (stejné pravidlo jako ve slots), se
        nabídne i do ordinace bez služby - bez lékařky.
        """
        rec = self.browse(res_id).exists()
        if not rec or rec.kind != "reservation" or not rec.procedure_id or rec.state != "web_new":
            return []
        A = self.env["elite.vet.availability"]
        proc = rec.procedure_id
        local = pytz.utc.localize(rec.start).astimezone(TZ)
        day, minute = local.date(), local.hour * 60 + local.minute
        doctor = rec.doctor_id or None
        # Recepce smí potvrdit i žádost, která už je blíž než „minimálně hodin předem“ pro web:
        # min_hours=0 nechá ve hře vše, co ještě nezačalo.
        # scope="internal": blokace „jen web“, víkend ani svátek recepci nebrání.
        slot = next((x for x in A.slots(proc, day, doctor=doctor, min_hours=0, max_days=HORIZONT_RECEPCE,
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

    def _board_doctor_check(self, day_str, minute, room_id, doctor=None, strict=True):
        """Smí rezervace na tabuli do ordinace `room_id` v čase `minute`?

        Stejné pravidlo jako návrhy a průvodce: v ordinaci musí po celou dobu úkonu
        sloužit lékařka, která úkon dělá (při `strict` přímo `doctor`), pokud úkon
        lékařku potřebuje; ordinace musí být mezi ordinacemi úkonu pro recepci.
        Kolize hlídá až zápis (_check_overlap). Vrací id lékařky, kterou zapsat
        (jediná sloužící), False = vyprázdnit, None = neměnit.
        """
        self.ensure_one()
        proc = self.procedure_id
        if self.kind != "reservation" or not proc or not room_id:
            return None
        A = self.env["elite.vet.availability"]
        day, minute = fields.Date.from_string(day_str), int(minute)
        room = self.env["elite.vet.room"].browse(room_id)
        proc_name = proc.with_context(lang=self._jazyk_kliniky()).name
        if room not in proc.rooms_for_reception():
            raise UserError(_("Úkon %s se v %s nedělá.") % (proc_name, room.name))
        wanted = doctor if strict else None
        doc_ids = A.serving_doctors(proc, day, room.id, minute, wanted or None)
        if not doc_ids and A.need_doctor(proc, wanted or None):
            if wanted:
                raise UserError(_("V %s v %s neslouží %s.") % (cas_label(minute), room.name, wanted.name))
            raise UserError(_("V %s v %s neslouží lékařka, která dělá %s.")
                            % (cas_label(minute), room.name, proc_name))
        if doctor and doctor.id in doc_ids:
            return None
        if len(doc_ids) == 1:
            return doc_ids[0]
        # Původní lékařka v novém čase/ordinaci neslouží: nenechat tam špatné jméno.
        return False if doctor else None

    @api.model
    def board_move(self, res_id, day_str, minute, room_id):
        """Přesun na tabuli. Rezervace jen tam, kde slouží lékařka, která úkon dělá
        (když v novém místě nemá službu dosavadní lékařka, přepíše se); blokace kamkoli."""
        rec = self.browse(res_id)
        doctor_id = rec._board_doctor_check(day_str, minute, room_id or rec.room_id.id,
                                            doctor=rec.doctor_id, strict=False)
        rec.action_reschedule(self.board_slot_utc(day_str, minute), room_id=room_id or None,
                              doctor_id=doctor_id)
        return True

    @api.model
    def board_confirm(self, res_id, day_str, minute, room_id, doctor_id=None):
        """doctor_id=None lékařku nemění; číslo ji nastaví (návrh z panelu Čekající).
        Zkontroluje, že v čase a ordinaci slouží lékařka, která úkon dělá (nebo
        ta, kterou si klient vybral); slouží-li jediná, zapíše ji."""
        rec = self.browse(res_id)
        doctor = self.env["elite.vet.doctor"].browse(doctor_id) if doctor_id else rec.doctor_id
        found = rec._board_doctor_check(day_str, minute, room_id, doctor=doctor)
        if doctor_id:
            found = doctor_id
        rec.action_reschedule(self.board_slot_utc(day_str, minute), room_id=room_id,
                              doctor_id=found)
        rec.action_confirm()
        return True
