import pytz

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

from odoo.addons.elite_vet_winvet.models.item import KINDS

TZ = pytz.timezone("Europe/Prague")

STATES = [("draft", "Rozepsaný"), ("done", "Hotovo – k pokladně"), ("cancelled", "Zrušeno")]
DOCTOR_GROUP = "elite_vet_clinic.group_clinic_doctor"
# Content of the visit: a linked doctor who changes one of these (or the bill lines, or finishes
# the visit) becomes its treating doctor (see _elite_vet_note_treating_doctor).
TREATING_FIELDS = frozenset(("temperature", "weight", "heart_rate", "respiratory_rate", "record_text",
                             "room_note"))
# Task 32: the visit text was split into three fields until 18.0.1.7.0. They stay in the database
# (deprecated, not shown, not written) and the migration joined them into record_text with these
# headings.
LEGACY_TEXT_PARTS = (("anamnesis", "Anamnéza:"), ("examination", "Vyšetření:"),
                     ("diagnosis", "Diagnóza a doporučení:"))
SUMMARY_LENGTH = 140


def combine_legacy_texts(anamnesis, examination, diagnosis):
    """The three old texts as one record text: only the filled parts, each under its heading on
    its own line, separated by a blank line; a single filled part without a heading."""
    parts = [(heading, (text or "").strip())
             for (_name, heading), text in zip(LEGACY_TEXT_PARTS, (anamnesis, examination, diagnosis))]
    parts = [(heading, text) for heading, text in parts if text]
    if len(parts) == 1:
        return parts[0][1]
    return "\n\n".join("%s\n%s" % (heading, text) for heading, text in parts)


def migrate_legacy_texts(cr):
    """Task 32 (migration to 18.0.1.7.0): fill record_text from the three deprecated texts where
    it is still empty and any of them has text. Plain SQL (no tracking, write_date kept); the old
    columns are left as they are. Idempotent: a record that has a record text is never touched.
    Returns the number of records filled."""
    cr.execute("""
        SELECT id, anamnesis, examination, diagnosis FROM elite_vet_clinical_record
         WHERE coalesce(btrim(record_text), '') = ''
           AND (coalesce(btrim(anamnesis), '') <> '' OR coalesce(btrim(examination), '') <> ''
                OR coalesce(btrim(diagnosis), '') <> '')
         ORDER BY id""")
    rows = [(combine_legacy_texts(a, e, d), rec_id) for rec_id, a, e, d in cr.fetchall()]
    rows = [(text, rec_id) for text, rec_id in rows if text]
    if rows:
        cr.executemany("UPDATE elite_vet_clinical_record SET record_text = %s WHERE id = %s", rows)
    return len(rows)


def record_text_title(text, length=SUMMARY_LENGTH):
    """First line that says something: headings ("Anamnéza:") and blank lines are skipped."""
    for line in (text or "").split("\n"):
        line = line.strip()
        if line and not line.endswith(":"):
            return line[:length].rstrip() + ("…" if len(line) > length else "")
    return ""


def insert_template_text(text, body, position=None):
    """Task 32: the template body put into the record text, never replacing anything.

    `position` is the cursor (an index into `text`): the body goes there, on its own lines when
    the cursor is inside a line. Without a cursor, or with the cursor after the last character
    that is not white space, the body is appended after a blank line. Returns (text, caret) –
    caret is the index right after the inserted body."""
    text = text or ""
    body = (body or "").strip()
    if not body:
        return text, len(text) if position is None else max(0, min(int(position), len(text)))
    if position is not None:
        position = max(0, min(int(position), len(text)))
    if position is None or not text[position:].strip():
        current = text.rstrip()
        new = "%s\n\n%s" % (current, body) if current else body
        return new, len(new)
    before, after = text[:position], text[position:]
    if before.strip() and not before.endswith("\n"):
        before += "\n"
    elif not before.strip():
        before = ""
    if not after.startswith("\n"):
        after = "\n" + after
    return before + body + after, len(before) + len(body)


def local_date(dt):
    """Naive UTC datetime -> date in the clinic timezone (independent of the user's tz)."""
    if not dt:
        return False
    return pytz.utc.localize(dt).astimezone(TZ).date()


class VetClinicalRecord(models.Model):
    """Visit record written in Odoo (phase 1 of replacing WinVet).

    Task 32: the text of the visit is one field, record_text ("Záznam z vyšetření"). The fields
    anamnesis, examination and diagnosis are DEPRECATED: kept in the database so nothing is lost
    (the migration to 18.0.1.7.0 copied them into record_text), not shown anywhere and never
    written by the code."""

    _name = "elite.vet.clinical.record"
    _description = "Záznam návštěvy"
    _inherit = ["mail.thread"]
    _order = "start desc, id desc"

    pet_id = fields.Many2one("elite.vet.pet", string="Pacient", required=True, index=True, ondelete="restrict",
                             tracking=True)
    partner_id = fields.Many2one(related="pet_id.partner_id", string="Majitel", store=True, index=True)
    doctor_id = fields.Many2one("elite.vet.doctor", string="Lékařka", ondelete="set null", tracking=True)
    # Task 23: the doctor was filled automatically (roster, reservation, default of the card) and
    # not chosen. A linked doctor who takes the visit or changes its content replaces it; any
    # other change of the doctor clears the flag, so that doctor is kept.
    doctor_auto = fields.Boolean(string="Lékařka doplněná automaticky", copy=False, readonly=True)
    other_doctor_ids = fields.Many2many(
        "elite.vet.doctor", "elite_vet_clinical_record_other_doctor_rel", "record_id", "doctor_id",
        string="Upravovaly také", copy=False, readonly=True, tracking=True,
        help="Další lékařky (s vlastním účtem), které záznam upravily po ošetřující lékařce.")
    user_id = fields.Many2one("res.users", string="Zapsal(a)", default=lambda self: self.env.user,
                              ondelete="set null")
    reservation_id = fields.Many2one("elite.vet.reservation", string="Rezervace", ondelete="set null", index=True,
                                     copy=False)
    start = fields.Datetime(string="Čas", required=True, default=fields.Datetime.now, index=True)
    date = fields.Date(string="Datum", compute="_compute_date", store=True, index=True,
                       help="Den návštěvy v čase kliniky.")
    state = fields.Selection(STATES, string="Stav", required=True, default="draft", tracking=True, index=True)
    temperature = fields.Float(string="Teplota (°C)", digits=(4, 1))
    weight = fields.Float(string="Hmotnost (kg)", digits=(6, 2))
    heart_rate = fields.Integer(string="Tep (/min)")
    respiratory_rate = fields.Integer(string="Dech (/min)")
    record_text = fields.Text(string="Záznam z vyšetření",
                              help="Text návštěvy – anamnéza, vyšetření, diagnóza a doporučení v jednom poli.")
    record_summary = fields.Char(string="Záznam", compute="_compute_record_summary",
                                 help="První řádek záznamu z vyšetření (bez nadpisů).")
    # deprecated (task 32): see the class docstring
    anamnesis = fields.Text(string="Anamnéza (zastaralé)", copy=False)
    examination = fields.Text(string="Vyšetření (zastaralé)", copy=False)
    diagnosis = fields.Text(string="Diagnóza a doporučení (zastaralé)", copy=False)
    # Request 25. 10.: internal note of the reception written when the client is checked in
    # (POS Dnes / Kartotéka), shown in the room. Never printed for the client.
    reception_note = fields.Text(string="Poznámka recepce", tracking=True, copy=False,
                                 help="Interní poznámka recepce při příjmu pacienta – ukáže se v ordinaci "
                                      "(karta pacienta, Moji pacienti dnes, obrazovka Ordinace). "
                                      "Klient ji nikde nevidí.")
    # Request 25. 10.: internal note of the room for the reception, written next to "Hotovo,
    # k pokladně" (also after finishing); shown at the till before paying. Never on the receipt.
    room_note = fields.Text(string="Poznámka pro recepci", tracking=True, copy=False,
                            help="Interní poznámka z ordinace pro recepci – ukáže se v pokladně u účtu "
                                 "(K pokladně, Zaplatit). Na účtence ani faktuře není.")
    line_ids = fields.One2many("elite.vet.clinical.record.line", "record_id", string="Položky účtu", copy=True)
    currency_id = fields.Many2one("res.currency", string="Měna", required=True,
                                  default=lambda self: self.env.ref("base.CZK"))
    amount_total = fields.Monetary(string="Celkem", compute="_compute_amount_total", store=True,
                                   currency_field="currency_id")

    _sql_constraints = [
        ("reservation_uniq", "unique(reservation_id)", "K této rezervaci už záznam návštěvy existuje."),
    ]

    @api.depends("start")
    def _compute_date(self):
        for rec in self:
            rec.date = local_date(rec.start)

    @api.depends("record_text")
    def _compute_record_summary(self):
        for rec in self:
            rec.record_summary = record_text_title(rec.record_text) or False

    @api.depends("line_ids.amount")
    def _compute_amount_total(self):
        for rec in self:
            rec.amount_total = sum(rec.line_ids.mapped("amount"))

    @api.depends("pet_id.name", "date")
    def _compute_display_name(self):
        for rec in self:
            day = rec.date.strftime("%-d. %-m. %Y") if rec.date else ""
            rec.display_name = " – ".join(p for p in (rec.pet_id.name, day) if p) or _("Záznam návštěvy")

    @api.constrains("temperature", "weight", "heart_rate", "respiratory_rate")
    def _check_vitals(self):
        for rec in self:
            if min(rec.temperature, rec.weight, rec.heart_rate, rec.respiratory_rate) < 0:
                raise ValidationError(_("Vitální hodnoty nesmí být záporné."))

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records.filtered(lambda r: r.state == "done")._update_pet_weight()
        return records

    def write(self, vals):
        cleared = self.browse()
        if "doctor_id" in vals and "doctor_auto" not in vals:
            new = vals["doctor_id"]
            new_id = (new.id if isinstance(new, models.BaseModel) else new) or False
            cleared = self.filtered(lambda r: r.doctor_auto and r.doctor_id.id != new_id)
        res = super().write(vals)
        if cleared:
            cleared.write({"doctor_auto": False})
        if "weight" in vals or vals.get("state") == "done":
            self.filtered(lambda r: r.state == "done")._update_pet_weight()
        if "doctor_id" not in vals and (TREATING_FIELDS.intersection(vals) or vals.get("state") == "done"):
            self._elite_vet_note_treating_doctor()
        return res

    # ------------------------------------------------------------------ treating doctor (task 23)

    @api.model
    def _elite_vet_is_room_account(self, user):
        """A shared account of a consultation room (elite_vet_reception)."""
        return False

    @api.model
    def _elite_vet_treating_doctor(self, user=None):
        """Team member of the user when her work makes her the treating doctor: an account linked
        in Rozpis služeb › Lékařky to a doctor who accepts bookings, role Lékařka, not a room
        account. Nurses and reception never are."""
        user = user or self.env.user
        Doctor = self.env["elite.vet.doctor"]
        if not user or not user.has_group(DOCTOR_GROUP) or self._elite_vet_is_room_account(user):
            return Doctor
        doctor = Doctor.sudo().search([("user_id", "=", user.id)], limit=1)
        return Doctor.browse(doctor.id) if doctor.accepts_bookings else Doctor

    def _elite_vet_note_treating_doctor(self):
        """The content of the records was changed: a linked doctor (see _elite_vet_treating_doctor)
        becomes the doctor where it is empty or was filled automatically. A chosen doctor or one
        set by an earlier doctor's edit is kept (the first treating doctor wins); the later one is
        added to Upravovaly také (tracked in the history)."""
        doctor = self._elite_vet_treating_doctor()
        if not doctor:
            return
        for rec in self:
            if rec.state == "cancelled":
                continue
            if not rec.doctor_id or rec.doctor_auto:
                rec.write({"doctor_id": doctor.id, "doctor_auto": False})
            elif rec.doctor_id != doctor and doctor not in rec.other_doctor_ids:
                rec.write({"other_doctor_ids": [(4, doctor.id)]})

    def _update_pet_weight(self):
        """The weight measured in a finished record becomes the pet's current weight."""
        for rec in self:
            if rec.weight and rec.pet_id.weight != rec.weight:
                rec.pet_id.weight = rec.weight

    def action_done(self):
        for rec in self:
            if rec.state == "cancelled":
                raise UserError(_("Zrušený záznam nelze uzavřít."))
        self.write({"state": "done"})
        return True

    def action_reopen(self):
        self.write({"state": "draft"})
        return True

    def action_cancel(self):
        self.write({"state": "cancelled"})
        return True

    def action_open_patient_card(self):
        self.ensure_one()
        return self.pet_id._patient_card_action(reservation=self.reservation_id)


class VetClinicalRecordLine(models.Model):
    """Line of the bill being put together during the visit (phase 2 turns it into a sale)."""

    _name = "elite.vet.clinical.record.line"
    _description = "Položka účtu návštěvy"
    _order = "record_id, sequence, id"

    record_id = fields.Many2one("elite.vet.clinical.record", string="Záznam", required=True, index=True,
                                ondelete="cascade")
    sequence = fields.Integer(string="Pořadí", default=10)
    item_id = fields.Many2one("elite.vet.winvet.item", string="Položka ceníku", ondelete="restrict", index=True)
    name = fields.Char(string="Název", required=True)
    kind = fields.Selection(KINDS, string="Druh", compute="_compute_kind", store=True, readonly=False,
                            required=True, precompute=True,
                            help="Podle položky ceníku; u volné položky „Jiné“, dokud ho někdo nezmění.")
    quantity = fields.Float(string="Množství", default=1.0, digits=(10, 3))
    unit = fields.Char(string="Jednotka")
    currency_id = fields.Many2one(related="record_id.currency_id")
    price_unit = fields.Monetary(string="Cena za jednotku", compute="_compute_price_unit", store=True,
                                 readonly=False, precompute=True, currency_field="currency_id",
                                 help="Výchozí cena s DPH z ceníku, lze ji změnit.")
    amount = fields.Monetary(string="Částka", compute="_compute_amount", store=True, currency_field="currency_id")
    bundle_id = fields.Many2one("elite.vet.procedure.bundle", string="Z balíčku", ondelete="set null")

    @api.depends("item_id.kind")
    def _compute_kind(self):
        for line in self:
            if line.item_id:
                line.kind = line.item_id.kind or "other"
            elif not line.kind:
                line.kind = "other"

    @api.depends("item_id")
    def _compute_price_unit(self):
        for line in self:
            line.price_unit = line.item_id.price if line.item_id else (line.price_unit or 0.0)

    @api.depends("quantity", "price_unit")
    def _compute_amount(self):
        for line in self:
            line.amount = line.currency_id.round(line.quantity * line.price_unit) if line.currency_id \
                else line.quantity * line.price_unit

    @api.onchange("item_id")
    def _onchange_item_id(self):
        if self.item_id:
            self.name = self.item_id.name
            self.unit = self.item_id.unit

    @api.model_create_multi
    def create(self, vals_list):
        Item = self.env["elite.vet.winvet.item"]
        for vals in vals_list:
            if vals.get("item_id") and not vals.get("name"):
                item = Item.browse(vals["item_id"])
                vals["name"] = item.name
                vals.setdefault("unit", item.unit)
        lines = super().create(vals_list)
        lines.record_id._elite_vet_note_treating_doctor()
        return lines

    def write(self, vals):
        res = super().write(vals)
        self.record_id._elite_vet_note_treating_doctor()
        return res

    def unlink(self):
        records = self.record_id
        res = super().unlink()
        records.exists()._elite_vet_note_treating_doctor()
        return res

    @api.constrains("quantity")
    def _check_quantity(self):
        for line in self:
            if line.quantity < 0:
                raise ValidationError(_("Množství nesmí být záporné."))
