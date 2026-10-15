"""Clinic expenses entered by hand (rent, salaries, purchases...).

WinVet only knows revenue, so expenses live here. The dashboard
(elite.vet.winvet.dashboard) reads them to show revenue, expenses and profit.
"""
import calendar
from datetime import date

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

from .payment import METHODS

MAX_REPEATS = 36  # three years of monthly copies at most
# Czech VAT rates since 2024. "0" also covers a supplier who is not a VAT payer.
VAT_RATES = [("0", "Bez DPH"), ("12", "12 %"), ("21", "21 %")]


def add_months(day, months):
    """Same day N months later; the 31st becomes the last day of a shorter month."""
    month_index = day.month - 1 + months
    year, month = day.year + month_index // 12, month_index % 12 + 1
    return date(year, month, min(day.day, calendar.monthrange(year, month)[1]))


class VetExpenseCategory(models.Model):
    _name = "elite.vet.expense.category"
    _description = "Kategorie výdajů"
    _order = "sequence, name"

    name = fields.Char(string="Název", required=True, translate=True)
    sequence = fields.Integer(string="Pořadí", default=10)
    color = fields.Char(string="Barva v grafu", default="#64748b")
    active = fields.Boolean(string="Aktivní", default=True)

    _sql_constraints = [("name_uniq", "unique(name)", "Kategorie s tímto názvem už existuje.")]


class VetExpense(models.Model):
    _name = "elite.vet.expense"
    _description = "Výdaj"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "date desc, id desc"

    name = fields.Char(string="Popis", required=True, tracking=True)
    date = fields.Date(string="Datum", required=True, index=True, default=fields.Date.context_today, tracking=True)
    category_id = fields.Many2one("elite.vet.expense.category", string="Kategorie", required=True,
                                  index=True, ondelete="restrict", tracking=True)
    currency_id = fields.Many2one("res.currency", default=lambda s: s.env.ref("base.CZK"), readonly=True)
    amount = fields.Monetary(string="Částka", required=True, tracking=True,
                             help="Celková částka včetně DPH, kterou klinika zaplatila.")
    vat_rate = fields.Selection(VAT_RATES, string="DPH", required=True, default="21",
                                help="Sazba DPH na dokladu. Plátce si DPH odečte, do zisku se proto počítá "
                                     "částka bez DPH.")
    amount_untaxed = fields.Monetary(string="Bez DPH", compute="_compute_amounts", store=True)
    amount_vat = fields.Monetary(string="DPH (částka)", compute="_compute_amounts", store=True)
    supplier_id = fields.Many2one("res.partner", string="Dodavatel", index=True, ondelete="set null")
    document_number = fields.Char(string="Číslo dokladu", help="Číslo faktury nebo účtenky.")
    payment_method = fields.Selection(METHODS, string="Zaplaceno", default="transfer")
    note = fields.Text(string="Poznámka")
    repeat_monthly_until = fields.Date(
        string="Opakovat měsíčně do",
        help="Jen při zakládání: výdaj se zkopíruje na stejný den každého dalšího měsíce až do "
             "tohoto data (např. nájem). Každá kopie je samostatný výdaj.")
    has_attachment = fields.Boolean(string="Má přiložený doklad", compute="_compute_has_attachment",
                                    search="_search_has_attachment")
    recurring_origin_id = fields.Many2one("elite.vet.expense", string="Opakování výdaje", readonly=True,
                                          ondelete="set null", index=True, copy=False)

    def _attached_ids(self, ids=None):
        domain = [("res_model", "=", self._name), ("res_id", "!=", False)]
        if ids is not None:
            domain.append(("res_id", "in", ids))
        return {a["res_id"] for a in self.env["ir.attachment"].sudo().search_read(domain, ["res_id"])}

    def _compute_has_attachment(self):
        attached = self._attached_ids(self.ids)
        for rec in self:
            rec.has_attachment = rec.id in attached

    def _search_has_attachment(self, operator, value):
        if operator not in ("=", "!="):
            raise ValidationError(_("Nepodporované hledání."))
        positive = (operator == "=") == bool(value)
        return [("id", "in" if positive else "not in", list(self._attached_ids()))]

    @api.depends("amount", "vat_rate")
    def _compute_amounts(self):
        for rec in self:
            rate = int(rec.vat_rate or "0")
            untaxed = rec.currency_id.round(rec.amount / (1 + rate / 100.0)) if rec.currency_id else rec.amount
            rec.amount_untaxed = untaxed
            rec.amount_vat = rec.amount - untaxed

    @api.constrains("amount")
    def _check_amount(self):
        for rec in self:
            if rec.amount <= 0:
                raise ValidationError(_("Částka výdaje musí být větší než nula."))

    @api.constrains("date", "repeat_monthly_until")
    def _check_repeat(self):
        for rec in self:
            if rec.repeat_monthly_until and rec.repeat_monthly_until < rec.date:
                raise ValidationError(_("„Opakovat měsíčně do“ musí být až po datu výdaje."))

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._create_monthly_copies()
        return records

    def _create_monthly_copies(self):
        """Monthly repetition = real copies, so every month can be edited or deleted alone."""
        copies = []
        for rec in self.filtered("repeat_monthly_until"):
            until = rec.repeat_monthly_until
            rec.repeat_monthly_until = False
            for i in range(1, MAX_REPEATS + 1):
                day = add_months(rec.date, i)
                if day > until:
                    break
                copies.append({
                    "name": rec.name, "date": day, "category_id": rec.category_id.id, "amount": rec.amount,
                    "vat_rate": rec.vat_rate,
                    "supplier_id": rec.supplier_id.id, "payment_method": rec.payment_method,
                    "note": rec.note, "recurring_origin_id": rec.id,
                })
        if copies:
            self.create(copies)
