"""Client deposits from WinVet (contract v5: entities `deposits` and `deposit_uses`).

WinVet keeps a deposit (PARTNER_ZALOHA) apart from the payments: a received deposit is not a PLATBA
row, its use in a document is a PARTNER_ZALOHA_CERPANI row (the document's payment then carries the
amount in `from_deposit`), and a refund only fills VRACENO / VRACENO_DATUM. WinVet has no method for
the refund; its cash handover view lists refunded deposits as cash, so Odoo stores "cash".
"""
from odoo import _, api, fields, models

from .payment import METHOD_CODES, METHODS
from .winvet_tools import to_date, to_float, to_int, to_str


def _czk(model):
    return model.env.ref("base.CZK")


def format_czk(amount):
    """1234.5 -> '1 234,50 Kč' (non-breaking spaces, Czech decimal comma)."""
    text = "{:,.2f}".format(amount or 0.0).replace(",", " ").replace(".", ",")
    return "%s Kč" % text


class VetDeposit(models.Model):
    _name = "elite.vet.deposit"
    _description = "Záloha (WinVet)"
    _order = "date desc, id desc"

    winvet_ref = fields.Integer(string="ID ve WinVetu", required=True, index=True, readonly=True)
    partner_id = fields.Many2one("res.partner", string="Klient", index=True, ondelete="set null", readonly=True)
    owner_winvet_ref = fields.Integer(string="ID klienta ve WinVetu", index=True, readonly=True)
    date = fields.Date(string="Přijato dne", index=True, readonly=True)
    currency_id = fields.Many2one("res.currency", default=_czk, readonly=True)
    amount = fields.Monetary(string="Přijato", readonly=True)
    method = fields.Selection(METHODS, string="Forma přijetí", index=True, readonly=True)
    method_code = fields.Char(string="Kód formy přijetí", readonly=True)
    used = fields.Monetary(string="Čerpáno", readonly=True, help="Podle WinVetu (aktuální stav).")
    refunded = fields.Monetary(string="Vráceno", readonly=True)
    refunded_date = fields.Date(string="Vráceno dne", index=True, readonly=True)
    refund_method = fields.Selection(
        METHODS, string="Forma vrácení", readonly=True,
        help="WinVet u vrácení zálohy formu nevede; vrácení je pokladní (hotovostní) pohyb.")
    balance = fields.Monetary(string="Zůstatek", readonly=True, help="Podle WinVetu (aktuální stav).")
    note = fields.Char(string="Poznámka", readonly=True)
    state = fields.Char(string="Stav (WinVet)", readonly=True)
    use_ids = fields.One2many("elite.vet.deposit.use", "deposit_id", string="Čerpání", readonly=True)
    use_count = fields.Integer(string="Počet čerpání", compute="_compute_use_count")

    _sql_constraints = [
        ("winvet_ref_uniq", "unique(winvet_ref)", "Záloha s tímto ID z WinVetu už existuje."),
    ]

    @api.depends("use_ids")
    def _compute_use_count(self):
        for rec in self:
            rec.use_count = len(rec.use_ids)

    @api.depends("date", "amount", "partner_id")
    def _compute_display_name(self):
        for rec in self:
            day = "%d. %d. %d" % (rec.date.day, rec.date.month, rec.date.year) if rec.date else ""
            rec.display_name = "Záloha %s %s" % (day, format_czk(rec.amount))


class VetDepositUse(models.Model):
    _name = "elite.vet.deposit.use"
    _description = "Čerpání zálohy (WinVet)"
    _order = "date desc, id desc"

    winvet_ref = fields.Integer(string="ID ve WinVetu", required=True, index=True, readonly=True)
    deposit_id = fields.Many2one("elite.vet.deposit", string="Záloha", index=True, ondelete="set null",
                                 readonly=True)
    deposit_winvet_ref = fields.Integer(string="ID zálohy ve WinVetu", index=True, readonly=True)
    partner_id = fields.Many2one(related="deposit_id.partner_id", string="Klient", store=True, index=True)
    document_id = fields.Many2one("elite.vet.sale.document", string="Doklad", index=True, ondelete="set null",
                                  readonly=True)
    document_winvet_ref = fields.Integer(string="ID dokladu ve WinVetu", index=True, readonly=True)
    document_number = fields.Char(string="Číslo dokladu", readonly=True)
    date = fields.Date(string="Datum", index=True, readonly=True)
    currency_id = fields.Many2one("res.currency", default=_czk, readonly=True)
    amount = fields.Monetary(string="Částka", readonly=True)
    state = fields.Char(string="Stav (WinVet)", readonly=True)

    _sql_constraints = [
        ("winvet_ref_uniq", "unique(winvet_ref)", "Čerpání zálohy s tímto ID z WinVetu už existuje."),
    ]


class ResPartner(models.Model):
    _inherit = "res.partner"

    winvet_deposit_ids = fields.One2many("elite.vet.deposit", "partner_id", string="Zálohy z WinVetu",
                                         readonly=True, groups="elite_vet_reservation.group_reservation_manager")
    winvet_deposit_count = fields.Integer(string="Počet záloh", compute="_compute_winvet_deposit")
    winvet_deposit_balance = fields.Float(string="Zůstatek záloh", compute="_compute_winvet_deposit",
                                          help="Součet zůstatků záloh klienta podle WinVetu.")
    winvet_deposit_balance_text = fields.Char(string="Zůstatek záloh (text)", compute="_compute_winvet_deposit")

    @api.depends("winvet_deposit_ids.balance")
    def _compute_winvet_deposit(self):
        # sudo: the balance is shown quietly on the patient card / Kartotéka (reception), the
        # deposit records themselves stay readable for managers only
        groups = self.env["elite.vet.deposit"].sudo()._read_group(
            [("partner_id", "in", self.ids)], ["partner_id"], ["__count", "balance:sum"]) if self.ids else []
        by_partner = {partner.id: (count, balance) for partner, count, balance in groups}
        for partner in self:
            count, balance = by_partner.get(partner.id, (0, 0.0))
            partner.winvet_deposit_count = count
            partner.winvet_deposit_balance = balance
            partner.winvet_deposit_balance_text = format_czk(balance) if balance > 0.005 else False

    def action_view_winvet_deposits(self):
        self.ensure_one()
        action = self.env["ir.actions.act_window"]._for_xml_id("elite_vet_winvet.action_deposit")
        action.update({
            "name": _("Zálohy – %s", self.display_name),
            "domain": [("partner_id", "=", self.id)],
            "context": {"default_partner_id": self.id, "search_default_group_month": 0},
        })
        return action


class WinvetDepositSync(models.AbstractModel):
    """Receiving the deposit entities of contract v5 (upsert like payments)."""

    _inherit = "elite.vet.winvet.sync"

    DEPOSIT_ENTITIES = ["deposits", "deposit_uses"]

    @api.model
    def _winvet_entities(self):
        entities = super()._winvet_entities()
        return entities + [e for e in self.DEPOSIT_ENTITIES if e not in entities]

    @api.model
    def _winvet_entity_models(self):
        return dict(super()._winvet_entity_models(), deposits="elite.vet.deposit",
                    deposit_uses="elite.vet.deposit.use")

    @api.model
    def _winvet_entity_labels(self):
        return dict(super()._winvet_entity_labels(), deposits="Zálohy", deposit_uses="Čerpání záloh")

    @api.model
    def _winvet_fixups(self):
        return super()._winvet_fixups() + [
            ("elite.vet.deposit", "partner_id", "owner_winvet_ref", "res.partner"),
            ("elite.vet.deposit.use", "deposit_id", "deposit_winvet_ref", "elite.vet.deposit"),
            ("elite.vet.deposit.use", "document_id", "document_winvet_ref", "elite.vet.sale.document"),
        ]

    @api.model
    def _winvet_date_keys(self):
        return dict(super()._winvet_date_keys(), deposits=("date", "refunded_date"), deposit_uses=("date",))

    def _push_deposits(self, records, stats, errors, batch, batches):
        partners = self._ref_map("res.partner", {to_int(r.get("owner_id")) for r in records.values()})
        vals = {}
        for ref, r in records.items():
            owner = to_int(r.get("owner_id"))
            code = (to_str(r.get("method")) or "").lower()
            refunded = to_float(r.get("refunded"))
            vals[ref] = {
                "partner_id": partners.get(owner, False), "owner_winvet_ref": owner or False,
                "date": to_date(r.get("date")),
                "amount": to_float(r.get("amount")),
                "method": METHOD_CODES.get(code, "other") if code else False,
                "method_code": code or False,
                "used": to_float(r.get("used")),
                "refunded": refunded,
                "refunded_date": to_date(r.get("refunded_date")),
                "refund_method": "cash" if refunded else False,
                "balance": to_float(r.get("balance")),
                "note": to_str(r.get("note")),
                "state": to_str(r.get("state")),
            }
        self._upsert("elite.vet.deposit", vals, stats, errors)

    def _push_deposit_uses(self, records, stats, errors, batch, batches):
        recs = records.values()
        deposits = self._ref_map("elite.vet.deposit", {to_int(r.get("deposit_id")) for r in recs})
        docs = self._ref_map("elite.vet.sale.document", {to_int(r.get("document_id")) for r in recs})
        vals = {}
        for ref, r in records.items():
            deposit, doc = to_int(r.get("deposit_id")), to_int(r.get("document_id"))
            vals[ref] = {
                "deposit_id": deposits.get(deposit, False), "deposit_winvet_ref": deposit or False,
                "document_id": docs.get(doc, False), "document_winvet_ref": doc or False,
                "document_number": to_str(r.get("document_number")),
                "date": to_date(r.get("date")),
                "amount": to_float(r.get("amount")),
                "state": to_str(r.get("state")),
            }
        self._upsert("elite.vet.deposit.use", vals, stats, errors)
