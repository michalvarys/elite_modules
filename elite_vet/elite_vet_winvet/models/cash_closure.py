"""Uzávěrka (PDF): the cash closure of a period from the WinVet data.

Bases (printed as notes in the report):

* sales by documents (PODP, FAV, VRAT) by the document date; a VRAT counts negative;
* new payments of documents = payment amount minus the part paid from a deposit, by the payment date;
  payments with a negative amount and payments of a VRAT are refunds;
* deposits count as income when received (their date), deposit refunds by the refund date; using a
  deposit in a document is not new income;
* a VRAT without payment rows is refunded by its `paid` amount on its date, with the method written on
  the document (`recorded_method`, bridge 5.0+), else the method of the original document, else cash;
* items by the line date (= visit date) with the payment method of their owner account; lines in the
  money unit ("měna", transfers of an unpaid balance into a new account) are not items and are listed
  apart, lines with a zero amount are left out.
"""
from collections import defaultdict
from datetime import datetime, timedelta

from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError

from .deposit import format_czk
from .payment import METHODS
from .winvet_tools import PRAGUE

MANAGER_GROUP = "elite_vet_reservation.group_reservation_manager"
#: payment methods of the closure, in column order ("other" only when it has an amount)
CLOSURE_METHODS = ["cash", "card", "transfer", "other"]
METHOD_ROWS = {"cash": "Hotovost", "card": "Platební karty", "transfer": "Převod", "other": "Jinak"}
METHOD_SHORT = dict(METHODS)
#: units of WinVet lines that are money, not an item (same rule as the visit report of elite_vet_clinic)
MONEY_UNITS = ("měna",)
DOC_ROWS = [("PODP", "Příjmové doklady (PODP)"), ("FAV", "Vystavené faktury (FAV)"), ("VRAT", "Vratky (VRAT)")]
KIND_ROWS = [("service", "Úkony"), ("product", "Léky a zboží"), ("other", "Ostatní")]
#: item table columns: (key, header); "mixed" and "other" only when present
ITEM_COLUMNS = [("cash", "Hotově"), ("card", "Kartou"), ("transfer", "Převodem"), ("mixed", "Kombinovaně"),
                ("other", "Jinak"), ("unpaid", "Bez úhrady")]
EPS = 0.005


def prague_today():
    return datetime.now(PRAGUE).date()


def money(amount):
    """1234.5 -> '1 234,50' (non-breaking space as the thousands separator)."""
    amount = round(amount or 0.0, 2)
    if abs(amount) < EPS:
        amount = 0.0
    return "{:,.2f}".format(amount).replace(",", " ").replace(".", ",")


def money_short(amount):
    """Sentence form: '2 000' for whole crowns, '1 234,50' otherwise."""
    amount = round(amount or 0.0, 2)
    if abs(amount - round(amount)) < EPS:
        return "{:,.0f}".format(amount).replace(",", " ")
    return money(amount)


def day_label(day, year=False):
    return "%d. %d.%s" % (day.day, day.month, " %d" % day.year if year else "")


def period_label(date_from, date_to):
    if date_from == date_to:
        return day_label(date_from, year=True)
    if date_from.year == date_to.year:
        return "%s – %s" % (day_label(date_from), day_label(date_to, year=True))
    return "%s – %s" % (day_label(date_from, year=True), day_label(date_to, year=True))


def preset_dates(preset, today):
    if preset == "today":
        return today, today
    if preset == "yesterday":
        day = today - timedelta(days=1)
        return day, day
    first = today.replace(day=1)
    if preset == "last_month":
        start = first - relativedelta(months=1)
        return start, first - timedelta(days=1)
    # this_month (default)
    return first, first + relativedelta(months=1) - timedelta(days=1)


class CashClosureWizard(models.TransientModel):
    _name = "elite.vet.cash.closure.wizard"
    _description = "Uzávěrka (PDF)"

    preset = fields.Selection(
        [("this_month", "Tento měsíc"), ("last_month", "Minulý měsíc"), ("today", "Dnes"),
         ("yesterday", "Včera"), ("custom", "Jiné období")],
        string="Období", default="this_month", required=True)
    date_from = fields.Date(string="Od", required=True, default=lambda s: preset_dates("this_month", prague_today())[0])
    date_to = fields.Date(string="Do", required=True, default=lambda s: preset_dates("this_month", prague_today())[1])

    @api.onchange("preset")
    def _onchange_preset(self):
        if self.preset and self.preset != "custom":
            self.date_from, self.date_to = preset_dates(self.preset, prague_today())

    @api.onchange("date_from", "date_to")
    def _onchange_dates(self):
        if self.preset != "custom" and self.date_from and self.date_to and \
                (self.date_from, self.date_to) != preset_dates(self.preset, prague_today()):
            self.preset = "custom"

    def _check_manager(self):
        if not self.env.user.has_group(MANAGER_GROUP):
            raise AccessError(_("Uzávěrku smí tisknout jen vedení."))

    def action_print(self):
        self.ensure_one()
        self._check_manager()
        if self.date_from > self.date_to:
            raise UserError(_("Datum „od“ je po datu „do“."))
        # own letterhead (company name, address, IČO): no "configure the document layout" dialog
        return self.env.ref("elite_vet_winvet.report_cash_closure").report_action(self, config=False)

    def _closure_filename(self):
        self.ensure_one()
        if self.date_from == self.date_to:
            return "Uzaverka_%s" % self.date_from.isoformat()
        return "Uzaverka_%s_%s" % (self.date_from.isoformat(), self.date_to.isoformat())

    def _closure_data(self):
        self.ensure_one()
        self._check_manager()
        return self.env["elite.vet.cash.closure"].closure_data(self.date_from, self.date_to)


class CashClosure(models.AbstractModel):
    """Computes the closure; reads with the rights of the user (managers read all WinVet data)."""

    _name = "elite.vet.cash.closure"
    _description = "Uzávěrka z WinVetu"

    # ------------------------------------------------------------------ helpers

    @api.model
    def _clinic(self):
        """Letterhead like the visit report of elite_vet_clinic: the company first, the website contact
        settings (elite_vet_web) fill a missing address."""
        company = self.env.company.sudo()
        address = [line for line in (
            company.street, company.street2, " ".join(p for p in (company.zip, company.city) if p)) if line]
        if not address and "elite.vet.setting" in self.env:
            setting = self.env["elite.vet.setting"].sudo().search([], limit=1)
            address = [line for line in (setting.address_line1, setting.address_line2) if line]
        return {"name": company.name or "", "address": ", ".join(address), "ico": company.company_registry or "",
                "dic": company.vat or ""}

    @api.model
    def _now_label(self):
        now = datetime.now(PRAGUE)
        return "%s %02d:%02d" % (day_label(now.date(), year=True), now.hour, now.minute)

    @staticmethod
    def _method(key):
        return key if key in ("cash", "card", "transfer") else "other"

    @api.model
    def _zero(self):
        return {m: 0.0 for m in CLOSURE_METHODS}

    # ------------------------------------------------------------------ main entry

    @api.model
    def closure_data(self, date_from, date_to):
        date_from, date_to = fields.Date.to_date(date_from), fields.Date.to_date(date_to)
        Doc = self.env["elite.vet.sale.document"]
        Payment = self.env["elite.vet.payment"]
        Deposit = self.env["elite.vet.deposit"]
        span = [("date", ">=", date_from), ("date", "<=", date_to)]

        docs = Doc.search(span + [("doc_type", "in", [k for k, _l in DOC_ROWS])], order="date, number, id")
        payments = Payment.search(span, order="date, time, id")
        deposits_any = bool(Deposit.search_count([], limit=1))
        deposits = Deposit.search(span, order="date, id")
        refunded_deposits = Deposit.search([("refunded_date", ">=", date_from), ("refunded_date", "<=", date_to),
                                            ("refunded", "!=", 0)], order="refunded_date, id")
        uses = self.env["elite.vet.deposit.use"].search(span, order="date, id")

        daily = defaultdict(lambda: {"sales": 0.0, "income": self._zero(), "refunded": 0.0})

        # 1. sales by documents
        doc_rows = []
        for key, label in DOC_ROWS:
            group = docs.filtered(lambda d, k=key: d.doc_type == k)
            sign = -1 if key == "VRAT" else 1
            doc_rows.append({"label": label, "count": len(group), "amount": sign * sum(group.mapped("total"))})
        for doc in docs:
            daily[doc.date]["sales"] += -doc.total if doc.doc_type == "VRAT" else doc.total
        sales_total = sum(r["amount"] for r in doc_rows)
        vrat_no_payout = docs.filtered(lambda d: d.doc_type == "VRAT" and not d.paid and not d.payment_ids)

        # 2. payments, deposits, refunds by method
        new = self._zero()
        deposit_in = self._zero()
        refund_docs, refund_deposits = self._zero(), self._zero()
        from_deposit = 0.0
        for pay in payments:
            method = self._method(pay.method)
            if pay.amount < 0 or pay.document_id.doc_type == "VRAT":
                refund_docs[method] += abs(pay.amount)
                daily[pay.date]["refunded"] += abs(pay.amount)
                continue
            amount = pay.amount - (pay.from_deposit or 0.0)
            from_deposit += pay.from_deposit or 0.0
            new[method] += amount
            daily[pay.date]["income"][method] += amount
        for doc in docs.filtered(lambda d: d.doc_type == "VRAT" and not d.payment_ids and d.paid):
            method = self._method(doc.recorded_method or doc.parent_id.payment_method or "cash")
            refund_docs[method] += abs(doc.paid)
            daily[doc.date]["refunded"] += abs(doc.paid)
        for dep in deposits:
            method = self._method(dep.method)
            deposit_in[method] += dep.amount
            daily[dep.date]["income"][method] += dep.amount
        for dep in refunded_deposits:
            method = self._method(dep.refund_method or "cash")
            refund_deposits[method] += abs(dep.refunded)
            daily[dep.refunded_date]["refunded"] += abs(dep.refunded)

        method_rows = []
        for method in CLOSURE_METHODS:
            row = {"key": method, "label": METHOD_ROWS[method], "new": new[method], "deposits": deposit_in[method],
                   "refunds": refund_docs[method] + refund_deposits[method]}
            row["income"] = row["new"] + row["deposits"]
            row["after"] = row["income"] - row["refunds"]
            if method != "other" or any(abs(row[k]) > EPS for k in ("new", "deposits", "refunds")):
                method_rows.append(row)
        totals = {k: sum(r[k] for r in method_rows) for k in ("new", "deposits", "income", "refunds", "after")}
        by_method = {r["key"]: r for r in method_rows}

        # 3. daily table (only days with data)
        show_other = "other" in by_method
        days = []
        for day in sorted(daily):
            values = daily[day]
            income = values["income"]
            row = {"label": day_label(day), "sales": values["sales"], "cash": income["cash"], "card": income["card"],
                   "transfer": income["transfer"], "other": income["other"], "refunded": values["refunded"]}
            row["after"] = sum(income.values()) - values["refunded"]
            days.append(row)
        day_totals = {k: sum(r[k] for r in days) for k in ("sales", "cash", "card", "transfer", "other", "refunded",
                                                            "after")}

        # 4. invoices and documents without payment
        invoices = [self._doc_row(d) for d in docs.filtered(lambda d: d.doc_type == "FAV")]
        unpaid_docs = [self._doc_row(d) for d in docs.filtered(
            lambda d: d.doc_type == "PODP" and d.payment_method == "unpaid" and d.total > EPS
            and not d.paid and not d.from_deposit)]
        invoice_total = sum(r["amount"] for r in invoices)
        invoice_unpaid = sum(max(r["amount"] - r["paid"], 0.0) for r in invoices)
        unpaid_total = sum(r["amount"] for r in unpaid_docs)

        # 5. deposits
        deposit_section = self._deposit_section(deposits, refunded_deposits, uses, date_to) if deposits_any else None

        # 6. items by payment method
        items = self._item_section(date_from, date_to)

        multi_day = date_from != date_to
        return {
            "clinic": self._clinic(),
            "period": period_label(date_from, date_to),
            "multi_day": multi_day,
            "generated": self._now_label(),
            "doc_rows": doc_rows,
            "doc_count": sum(r["count"] for r in doc_rows),
            "sales_total": sales_total,
            "vrat_no_payout_count": len(vrat_no_payout),
            "vrat_no_payout": sum(vrat_no_payout.mapped("total")),
            "method_rows": method_rows,
            "totals": totals,
            "from_deposit": from_deposit,
            "refund_docs": sum(refund_docs.values()),
            "refund_deposits": sum(refund_deposits.values()),
            "refund_methods": sorted({m for m in CLOSURE_METHODS if refund_docs[m] + refund_deposits[m] > EPS}),
            "summary": self._summary(method_rows, totals),
            "days": days if multi_day else [],
            "day_totals": day_totals,
            "show_other_day": show_other,
            "invoices": invoices,
            "invoice_total": invoice_total,
            "invoice_unpaid": invoice_unpaid,
            "unpaid_docs": unpaid_docs,
            "unpaid_total": unpaid_total,
            "deposits": deposit_section,
            "items": items,
        }

    # ------------------------------------------------------------------ sections

    @api.model
    def _doc_row(self, doc):
        methods = doc.recorded_method or next(
            (p.method for p in doc.payment_ids if p.method), False)
        return {"date": day_label(doc.date) if doc.date else "", "number": doc.number or "",
                "partner": doc.partner_id.name or "", "method": METHOD_SHORT.get(methods, "") if methods else "",
                "amount": doc.total, "paid": doc.paid}

    @api.model
    def _summary(self, method_rows, totals):
        parts = []
        names = {"cash": "hotovost", "card": "karty", "transfer": "převody", "other": "jiné formy"}
        for row in method_rows:
            parts.append("%s %s Kč" % (names[row["key"]], money(row["after"])))
        text = "Příjmy po evidovaných vráceních: %s Kč." % money(totals["after"])
        if parts:
            text += " Z toho " + (", ".join(parts[:-1]) + " a " + parts[-1] if len(parts) > 1 else parts[0]) + "."
        return text

    @api.model
    def _deposit_section(self, deposits, refunded_deposits, uses, date_to):
        rows = []
        for dep in deposits:
            dep_uses = dep.use_ids.filtered(lambda u: u.date and u.date <= date_to)
            used = sum(dep_uses.mapped("amount")) if dep.use_ids else (dep.used or 0.0)
            refunded = dep.refunded if dep.refunded_date and dep.refunded_date <= date_to else 0.0
            rows.append({"date": day_label(dep.date), "partner": dep.partner_id.name or "",
                         "method": METHOD_SHORT.get(dep.method, "") if dep.method else "",
                         "amount": dep.amount, "used": used, "refunded": refunded,
                         "balance": dep.amount - used - refunded,
                         # WinVet's own equation of the deposit (current state)
                         "ok": abs(dep.amount - (dep.used or 0) - (dep.refunded or 0) - (dep.balance or 0)) < EPS})
        total = {k: sum(r[k] for r in rows) for k in ("amount", "used", "refunded", "balance")}
        refunds = [{"date": day_label(d.refunded_date), "partner": d.partner_id.name or "", "amount": d.refunded,
                    "method": METHOD_SHORT.get(d.refund_method or "cash"),
                    "received_method": METHOD_SHORT.get(d.method, "") if d.method else ""}
                   for d in refunded_deposits]
        use_rows = [{"date": day_label(u.date), "partner": u.partner_id.name or "", "amount": u.amount,
                     "document": u.document_id.number or u.document_number or ""} for u in uses]
        return {
            "rows": rows, "total": total, "refunds": refunds, "refund_total": sum(r["amount"] for r in refunds),
            "uses": use_rows, "use_total": sum(r["amount"] for r in use_rows),
            "equation": abs(total["amount"] - total["used"] - total["refunded"] - total["balance"]) < EPS,
            "winvet_ok": all(r["ok"] for r in rows),
            "as_of": day_label(date_to, year=True),
        }

    @api.model
    def _item_section(self, date_from, date_to):
        lines = self.env["elite.vet.sale.line"].search(
            [("date", ">=", date_from), ("date", "<=", date_to), ("amount", "!=", 0)])
        money_lines = lines.filtered(lambda l: (l.unit or "").strip().lower() in MONEY_UNITS)
        lines -= money_lines
        items = {}
        kinds = {key: {"label": label, "values": defaultdict(float), "quantity": 0.0, "total": 0.0}
                 for key, label in KIND_ROWS}
        present = set()
        for line in lines:
            column = line.payment_method or "unpaid"
            present.add(column)
            name = (line.item_name or "").strip() or "(bez názvu)"
            item = items.setdefault((name, line.kind or "other"), {
                "label": name, "values": defaultdict(float), "quantity": 0.0, "total": 0.0})
            for target in (item, kinds[line.kind or "other"]):
                target["values"][column] += line.amount
                target["quantity"] += line.quantity or 0.0
                target["total"] += line.amount
        columns = [(k, h) for k, h in ITEM_COLUMNS if k in ("cash", "card", "transfer", "unpaid") or k in present]
        totals = {"values": defaultdict(float), "total": 0.0}
        for kind in kinds.values():
            for key, value in kind["values"].items():
                totals["values"][key] += value
            totals["total"] += kind["total"]
        rows = sorted(items.values(), key=lambda r: (-r["total"], r["label"]))
        for row in rows:
            row["quantity_text"] = ("%.2f" % row["quantity"]).rstrip("0").rstrip(".").replace(".", ",")
        money_rows = [{"date": day_label(l.date), "label": (l.item_name or "").strip(), "amount": l.amount,
                       "document": l.document_id.number or ""} for l in money_lines.sorted(lambda l: (l.date, l.id))]
        return {"columns": columns, "kinds": [kinds[k] for k, _l in KIND_ROWS if kinds[k]["total"] or kinds[k]["quantity"]],
                "rows": rows, "totals": totals, "money_rows": money_rows,
                "money_total": sum(r["amount"] for r in money_rows)}


class CashClosureReport(models.AbstractModel):
    _name = "report.elite_vet_winvet.report_cash_closure_document"
    _description = "Uzávěrka (PDF) – data"

    @api.model
    def _get_report_values(self, docids, data=None):
        docs = self.env["elite.vet.cash.closure.wizard"].browse(docids)
        if not self.env.user.has_group(MANAGER_GROUP):
            raise AccessError(_("Uzávěrku smí tisknout jen vedení."))
        return {"doc_ids": docids, "doc_model": "elite.vet.cash.closure.wizard", "docs": docs,
                "money": money, "money_short": money_short, "format_czk": format_czk}
