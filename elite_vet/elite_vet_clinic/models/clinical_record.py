import pytz

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

from odoo.addons.elite_vet_winvet.models.item import KINDS

TZ = pytz.timezone("Europe/Prague")

STATES = [("draft", "Rozepsaný"), ("done", "Hotovo – k pokladně"), ("cancelled", "Zrušeno")]


def local_date(dt):
    """Naive UTC datetime -> date in the clinic timezone (independent of the user's tz)."""
    if not dt:
        return False
    return pytz.utc.localize(dt).astimezone(TZ).date()


class VetClinicalRecord(models.Model):
    """Visit record written in Odoo (phase 1 of replacing WinVet)."""

    _name = "elite.vet.clinical.record"
    _description = "Záznam návštěvy"
    _inherit = ["mail.thread"]
    _order = "start desc, id desc"

    pet_id = fields.Many2one("elite.vet.pet", string="Pacient", required=True, index=True, ondelete="restrict",
                             tracking=True)
    partner_id = fields.Many2one(related="pet_id.partner_id", string="Majitel", store=True, index=True)
    doctor_id = fields.Many2one("elite.vet.doctor", string="Lékařka", ondelete="set null", tracking=True)
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
    anamnesis = fields.Text(string="Anamnéza")
    examination = fields.Text(string="Vyšetření")
    diagnosis = fields.Text(string="Diagnóza a doporučení")
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
        res = super().write(vals)
        if "weight" in vals or vals.get("state") == "done":
            self.filtered(lambda r: r.state == "done")._update_pet_weight()
        return res

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
        return super().create(vals_list)

    @api.constrains("quantity")
    def _check_quantity(self):
        for line in self:
            if line.quantity < 0:
                raise ValidationError(_("Množství nesmí být záporné."))
