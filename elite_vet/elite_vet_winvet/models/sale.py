from odoo import api, fields, models

from .item import KINDS
from .payment import METHODS

#: How a document was paid (grouping in the analytics). An owner account (UM) is paid through its
#: receipt (PODP, parent_id = the account); documents without a non-zero payment are "unpaid".
PAYMENT_METHODS = METHODS + [("mixed", "Kombinovaně"), ("unpaid", "Bez úhrady")]

DOC_TYPES = {"UM": "Účet majitele", "PODP": "Doklad PODP", "FAV": "Faktura vydaná", "VRAT": "Vratka"}


def _czk(model):
    return model.env.ref("base.CZK")


class VetSaleDocument(models.Model):
    _name = "elite.vet.sale.document"
    _description = "Doklad (WinVet)"
    _order = "date desc, id desc"
    _rec_name = "number"

    winvet_ref = fields.Integer(string="ID ve WinVetu", required=True, index=True, readonly=True)
    doc_type = fields.Char(string="Typ dokladu", index=True, readonly=True)
    doc_type_name = fields.Char(string="Typ", compute="_compute_doc_type_name", store=True)
    number = fields.Char(string="Číslo", index=True, readonly=True)
    parent_id = fields.Many2one("elite.vet.sale.document", string="Předchozí doklad", ondelete="set null",
                                readonly=True)
    parent_winvet_ref = fields.Integer(string="ID předchozího dokladu ve WinVetu", index=True, readonly=True)
    partner_id = fields.Many2one("res.partner", string="Majitel", index=True, ondelete="set null", readonly=True)
    owner_winvet_ref = fields.Integer(string="ID majitele ve WinVetu", index=True, readonly=True)
    date = fields.Date(string="Datum", index=True, readonly=True)
    currency_id = fields.Many2one("res.currency", default=_czk, readonly=True)
    total = fields.Monetary(string="Celkem", readonly=True)
    paid = fields.Monetary(string="Zaplaceno", readonly=True)
    from_deposit = fields.Monetary(string="Ze zálohy", readonly=True)
    state = fields.Char(string="Stav (WinVet)", readonly=True)
    entered_by_id = fields.Many2one("elite.vet.winvet.user", string="Založil(a)", ondelete="set null", readonly=True)
    entered_by_winvet_ref = fields.Integer(string="ID uživatele ve WinVetu", readonly=True)
    line_ids = fields.One2many("elite.vet.sale.line", "document_id", string="Položky", readonly=True)
    payment_ids = fields.One2many("elite.vet.payment", "document_id", string="Platby", readonly=True)
    child_ids = fields.One2many("elite.vet.sale.document", "parent_id", string="Navazující doklady", readonly=True)
    payment_method = fields.Selection(
        PAYMENT_METHODS, string="Forma úhrady", compute="_compute_payment_method", store=True, index=True,
        help="Podle plateb dokladu; účet majitele podle plateb jeho příjmového dokladu (PODP). "
             "Bez úhrady = žádná platba s nenulovou částkou.")

    _sql_constraints = [
        ("winvet_ref_uniq", "unique(winvet_ref)", "Doklad s tímto ID z WinVetu už existuje."),
    ]

    @api.depends("payment_ids.method", "payment_ids.amount", "child_ids.payment_ids.method",
                 "child_ids.payment_ids.amount")
    def _compute_payment_method(self):
        for rec in self:
            payments = rec.payment_ids | rec.child_ids.filtered(lambda d: d.doc_type == "PODP").payment_ids
            methods = set(payments.filtered(lambda p: p.amount and p.method).mapped("method"))
            rec.payment_method = methods.pop() if len(methods) == 1 else ("mixed" if methods else "unpaid")

    @api.depends("doc_type")
    def _compute_doc_type_name(self):
        for rec in self:
            rec.doc_type_name = DOC_TYPES.get(rec.doc_type or "", rec.doc_type or False)


class VetSaleLine(models.Model):
    """One line of an owner account (service or product) - the main analytics table."""

    _name = "elite.vet.sale.line"
    _description = "Položka dokladu (WinVet)"
    _order = "date desc, id desc"
    _rec_name = "item_name"

    winvet_ref = fields.Integer(string="ID ve WinVetu", required=True, index=True, readonly=True)
    document_id = fields.Many2one("elite.vet.sale.document", string="Doklad", index=True, ondelete="set null",
                                  readonly=True)
    document_winvet_ref = fields.Integer(string="ID dokladu ve WinVetu", index=True, readonly=True)
    doc_type = fields.Char(related="document_id.doc_type", string="Typ dokladu", store=True)
    visit_id = fields.Many2one("elite.vet.visit", string="Návštěva", index=True, ondelete="set null", readonly=True)
    visit_winvet_ref = fields.Integer(string="ID návštěvy ve WinVetu", index=True, readonly=True)
    pet_id = fields.Many2one(related="visit_id.pet_id", string="Pacient", store=True, index=True)
    species = fields.Selection(related="pet_id.species", string="Druh zvířete", store=True)
    partner_id = fields.Many2one(related="document_id.partner_id", string="Majitel", store=True, index=True)
    item_id = fields.Many2one("elite.vet.winvet.item", string="Položka ceníku", index=True, ondelete="set null",
                              readonly=True)
    item_winvet_ref = fields.Integer(string="ID položky ve WinVetu", index=True, readonly=True)
    item_code = fields.Char(string="Kód", index=True, readonly=True)
    item_name = fields.Char(string="Název", readonly=True)
    kind = fields.Selection(KINDS, string="Druh položky", compute="_compute_kind", store=True, index=True)
    quantity = fields.Float(string="Množství", readonly=True)
    unit = fields.Char(string="Jednotka", readonly=True)
    currency_id = fields.Many2one("res.currency", default=_czk, readonly=True)
    unit_price = fields.Monetary(string="Cena za jednotku", readonly=True, aggregator="avg")
    amount = fields.Monetary(string="Částka", readonly=True)
    vat_rate = fields.Float(string="Sazba DPH", readonly=True, aggregator=False)
    date = fields.Date(string="Datum", index=True, readonly=True)
    entered_by_id = fields.Many2one("elite.vet.winvet.user", string="Zapsal(a)", index=True, ondelete="set null",
                                    readonly=True)
    entered_by_winvet_ref = fields.Integer(string="ID uživatele ve WinVetu", readonly=True)
    doctor_id = fields.Many2one(related="entered_by_id.doctor_id", string="Lékařka", store=True, index=True)
    payment_method = fields.Selection(related="document_id.payment_method", string="Forma úhrady", store=True,
                                      index=True)

    _sql_constraints = [
        ("winvet_ref_uniq", "unique(winvet_ref)", "Položka dokladu s tímto ID z WinVetu už existuje."),
    ]

    @api.depends("item_id.kind")
    def _compute_kind(self):
        for rec in self:
            rec.kind = rec.item_id.kind or "other"
