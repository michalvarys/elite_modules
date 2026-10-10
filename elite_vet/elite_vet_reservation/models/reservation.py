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
    @api.depends("kind", "contact_name", "partner_id.name", "pet_name", "pet_id.name", "procedure_id.name", "block_reason")
    def _compute_name(self):
        for rec in self:
            if rec.kind == "block":
                rec.name = rec.block_reason or _("Blokace")
                continue
            parts = [rec.partner_id.name or rec.contact_name or _("Bez jména"),
                     rec.pet_id.name or rec.pet_name or "", rec.procedure_id.name or ""]
            rec.name = " / ".join(p for p in parts if p)

    @api.depends("start", "stop")
    def _compute_duration(self):
        for rec in self:
            rec.duration_minutes = int((rec.stop - rec.start).total_seconds() // 60) if rec.start and rec.stop else 0

    @api.depends("kind", "procedure_id.color_hex")
    def _compute_color_hex(self):
        for rec in self:
            rec.color_hex = "#64748b" if rec.kind == "block" else (rec.procedure_id.color_hex or "#64748b")

    @api.onchange("procedure_id", "start")
    def _onchange_stop(self):
        if self.start and self.procedure_id and self.kind == "reservation":
            self.stop = self.start + timedelta(minutes=self.procedure_id.duration)

    # ---------- prekryvy ----------
    @api.model
    def _busy_domain(self, room_ids, start, stop, exclude_ids=None):
        """Zaznamy, ktere v danem case opravdu blokuji ordinace (potvrzene + blokace)."""
        domain = [
            ("start", "<", stop), ("stop", ">", start),
            "|", ("kind", "=", "block"), ("state", "in", BUSY_STATES),
            "|", ("room_id", "=", False), ("room_id", "in", list(room_ids)),
        ]
        if exclude_ids:
            domain.append(("id", "not in", list(exclude_ids)))
        return domain

    @api.model
    def _lock_rooms(self, room_ids):
        """Radkovy zamek ordinaci: dva soubezne zapisy na stejny slot se serazi za sebe."""
        ids = list(room_ids) or self.env["elite.vet.room"].search([]).ids
        if ids:
            self.env.cr.execute("SELECT id FROM elite_vet_room WHERE id IN %s FOR UPDATE", (tuple(ids),))

    def _po_prijeti_z_webu(self):
        """Hacek pro e-maily po prijeti z webu; naplni ho ukol 11."""
        return True

    def _blokuje(self):
        self.ensure_one()
        return self.kind == "block" or self.state in BUSY_STATES

    def _check_overlap(self):
        for rec in self:
            if rec.kind == "reservation" and rec.state in ("cancelled", "no_show"):
                continue
            all_rooms = self.env["elite.vet.room"].search([]).ids
            rooms = [rec.room_id.id] if rec.room_id else all_rooms
            if not rec.room_id and rec.kind == "reservation":
                continue   # cekajici z webu bez ordinace se zatim nikam nepise
            self._lock_rooms(rooms)
            clash = self.search(self._busy_domain(rooms, rec.start, rec.stop, exclude_ids=[rec.id]), limit=1)
            if clash and (rec._blokuje() or rec.state == "web_new"):
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
        records._check_overlap()
        records._rozkopirovat_blokace()
        return records

    def write(self, vals):
        res = super().write(vals)
        if {"start", "stop", "room_id", "state", "kind"} & set(vals):
            self._check_overlap()
        return res

    def _rozkopirovat_blokace(self):
        """Tydenni opakovani blokace = materializovane kopie, zadne rrule."""
        for rec in self.filtered(lambda r: r.kind == "block" and r.repeat_weekly_until):
            until = rec.repeat_weekly_until
            rec.repeat_weekly_until = False
            # Posun po tydnech v mistnim case, aby 12:00 zustalo 12:00 i pres zmenu letniho/zimniho casu.
            tz_start = fields.Datetime.context_timestamp(rec, rec.start)
            delka = rec.stop - rec.start
            vals_list = []
            for i in range(1, 53):
                local = tz_start.tzinfo.localize(tz_start.replace(tzinfo=None) + timedelta(days=7 * i))
                if local.date() > until:
                    break
                start = local.astimezone(pytz.utc).replace(tzinfo=None)
                vals_list.append({"kind": "block", "block_reason": rec.block_reason, "room_id": rec.room_id.id,
                                  "start": start, "stop": start + delka, "note": rec.note})
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
