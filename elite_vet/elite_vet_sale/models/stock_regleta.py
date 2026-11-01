"""Regleta skladu (PDF): opening stock, receipts, issues and closing stock of a period, per item,
from the WinVet stock movements (contract v6: stock_moves) – for the accountant.

Valuation: by the receipt line. WinVet keeps the receipt price as entered (with VAT) but issues at a
net cost of its own, so its stock value keeps the VAT of the receipts (see winvet_bridge/CONTRACT.md,
contract v6). Here every receipt line gets a value without and with VAT from its quantity x unit
price (the line total CENA is wrong on some negative receipt lines – returns) and VAT rate:

* price entered with VAT: with VAT = the value, without VAT = value / (1 + rate);
* price entered without VAT: without VAT = the value, with VAT = value * (1 + rate);

(the VAT amount of the line, CENA_DPH, is not used: on some lines WinVet computes it as rate x the
price with VAT - 36 Kč of 300 Kč at 12 % instead of 32,14 Kč);

and every issue is valued by the receipt line it was issued from (WinVet links each issue to it):
quantity x that unit price. What comes in leaves at the same price. An issue without a known
receipt line falls back to WinVet's own (net) cost. Receipt lines entered at VAT rate 0 are taken
as entered and listed in the report.
"""
from collections import defaultdict
from datetime import date

from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError

from odoo.addons.elite_vet_winvet.models.cash_closure import money, period_label, prague_today

MANAGER_GROUP = "elite_vet_reservation.group_reservation_manager"
KIND_ROWS = [("product", "Léky a zboží"), ("service", "Úkony"), ("other", "Ostatní")]
EPS = 0.0005
PARTS = ("opening", "in", "out", "closing")


def quantity_label(value):
    """1.5 -> '1,5', 2.0 -> '2' (at most 3 decimals, Czech comma)."""
    value = round(value or 0.0, 3)
    if abs(value) < EPS:
        value = 0.0
    text = ("{:,.3f}".format(value)).rstrip("0").rstrip(".")
    return text.replace(",", " ").replace(".", ",")


def regleta_preset_dates(preset, today):
    first = today.replace(day=1)
    if preset == "last_month":
        start = first - relativedelta(months=1)
        return start, first - relativedelta(days=1)
    if preset == "this_year":
        return date(today.year, 1, 1), date(today.year, 12, 31)
    if preset == "last_year":
        return date(today.year - 1, 1, 1), date(today.year - 1, 12, 31)
    # this_month (default)
    return first, first + relativedelta(months=1, days=-1)


class WinvetStockMove(models.Model):
    _name = "elite.vet.winvet.stock.move"
    _description = "WinVet – pohyb skladu"
    _order = "date, winvet_ref"

    winvet_ref = fields.Integer(string="WinVet ID", required=True, index=True, readonly=True)
    item_id = fields.Many2one("elite.vet.winvet.item", string="Položka", index=True, ondelete="set null",
                              readonly=True)
    item_winvet_ref = fields.Integer(string="WinVet ID položky", readonly=True)
    direction = fields.Selection([("in", "Příjem"), ("out", "Výdej")], string="Směr", readonly=True)
    move_type = fields.Char(string="Typ pohybu", readonly=True, help="TYP_POHYBU ve WinVetu: P, D příjem, "
                            "V výdej, G počáteční řádek bez dokladu.")
    date = fields.Date(string="Datum", index=True, readonly=True)
    document = fields.Char(string="Doklad", readonly=True)
    document_type = fields.Char(string="Druh dokladu", readonly=True)
    quantity = fields.Float(string="Množství", digits="Product Unit of Measure", readonly=True)
    unit = fields.Char(string="Jednotka", readonly=True)
    unit_price = fields.Float(string="Cena za MJ", readonly=True)
    amount = fields.Float(string="Částka", readonly=True, help="Hodnota řádku, jak je ve WinVetu.")
    vat_amount = fields.Float(string="DPH", readonly=True)
    vat_rate = fields.Float(string="Sazba DPH (%)", readonly=True)
    amount_includes_vat = fields.Boolean(string="Částka s DPH", readonly=True)
    receipt_winvet_ref = fields.Integer(string="WinVet ID příjmu", index=True, readonly=True,
                                        help="U výdeje řádek příjemky, ze kterého se vydalo.")

    _sql_constraints = [("winvet_ref_unique", "unique(winvet_ref)", "Pohyb WinVetu už existuje.")]

    def _receipt_values(self):
        """(value without VAT, value with VAT) of a receipt line: quantity x unit price and VAT rate."""
        self.ensure_one()
        amount = (self.quantity or 0.0) * (self.unit_price or 0.0) if self.unit_price else (self.amount or 0.0)
        factor = 1.0 + (self.vat_rate or 0.0) / 100.0
        if self.amount_includes_vat:
            return amount / factor, amount
        return amount, amount * factor


class StockRegletaWizard(models.TransientModel):
    _name = "elite.vet.stock.regleta.wizard"
    _description = "Regleta skladu (PDF)"

    preset = fields.Selection(
        [("this_month", "Tento měsíc"), ("last_month", "Minulý měsíc"), ("this_year", "Tento rok"),
         ("last_year", "Minulý rok"), ("custom", "Jiné období")],
        string="Období", default="last_month", required=True)
    date_from = fields.Date(string="Od", required=True,
                            default=lambda s: regleta_preset_dates("last_month", prague_today())[0])
    date_to = fields.Date(string="Do", required=True,
                          default=lambda s: regleta_preset_dates("last_month", prague_today())[1])

    @api.onchange("preset")
    def _onchange_preset(self):
        if self.preset and self.preset != "custom":
            self.date_from, self.date_to = regleta_preset_dates(self.preset, prague_today())

    @api.onchange("date_from", "date_to")
    def _onchange_dates(self):
        if self.preset != "custom" and self.date_from and self.date_to and \
                (self.date_from, self.date_to) != regleta_preset_dates(self.preset, prague_today()):
            self.preset = "custom"

    def _check_manager(self):
        if not self.env.user.has_group(MANAGER_GROUP):
            raise AccessError(_("Regletu skladu smí tisknout jen vedení."))

    def action_print(self):
        self.ensure_one()
        self._check_manager()
        if self.date_from > self.date_to:
            raise UserError(_("Datum „od“ je po datu „do“."))
        return self.env.ref("elite_vet_sale.report_stock_regleta").report_action(self, config=False)

    def _regleta_filename(self):
        self.ensure_one()
        return "Regleta_skladu_%s_%s" % (self.date_from.isoformat(), self.date_to.isoformat())

    def _regleta_data(self):
        self.ensure_one()
        self._check_manager()
        return self.env["elite.vet.stock.regleta"].regleta_data(self.date_from, self.date_to)


class StockRegleta(models.AbstractModel):
    """Computes the regleta; reads with the rights of the user (managers read all WinVet data)."""

    _name = "elite.vet.stock.regleta"
    _description = "Regleta skladu – výpočet"

    @staticmethod
    def _zero():
        return {part: {"qty": 0.0, "net": 0.0, "gross": 0.0} for part in PARTS}

    @staticmethod
    def _add(bucket, sign, qty, net, gross):
        bucket["qty"] += sign * qty
        bucket["net"] += sign * net
        bucket["gross"] += sign * gross

    @api.model
    def regleta_data(self, date_from, date_to):
        Move = self.env["elite.vet.winvet.stock.move"]
        moves = Move.search([("date", "<=", date_to)])
        receipts = {m.winvet_ref: m for m in Move.search([("direction", "=", "in")])}
        unit_prices = {}
        for ref, rec in receipts.items():
            net, gross = rec._receipt_values()
            qty = rec.quantity or 0.0
            unit_prices[ref] = (net / qty, gross / qty) if qty else (0.0, 0.0)

        items = defaultdict(self._zero)
        info = {}
        receipt_docs = {}
        vat_rows = defaultdict(lambda: {"net": 0.0, "vat": 0.0, "gross": 0.0})
        zero_vat = {"count": 0, "net": 0.0}
        no_receipt = {"count": 0, "net": 0.0}
        for m in moves:
            if not m.direction or not m.item_winvet_ref:
                continue
            qty = m.quantity or 0.0
            if m.direction == "in":
                net, gross = m._receipt_values()
            else:
                prices = unit_prices.get(m.receipt_winvet_ref)
                if prices:
                    net, gross = qty * prices[0], qty * prices[1]
                else:
                    # no receipt line known: WinVet's own cost (net), VAT rate of the item
                    net = m.amount or 0.0
                    gross = net * (1.0 + (m.item_id.vat_rate or 0.0) / 100.0)
            key = m.item_winvet_ref
            info.setdefault(key, m)
            row = items[key]
            in_period = m.date and m.date >= date_from
            sign = 1 if m.direction == "in" else -1
            if not in_period:
                self._add(row["opening"], sign, qty, net, gross)
            else:
                self._add(row[m.direction], 1, qty, net, gross)
                if m.direction == "out" and not unit_prices.get(m.receipt_winvet_ref):
                    no_receipt["count"] += 1
                    no_receipt["net"] += net
                if m.direction == "in" and (m.amount or m.quantity):
                    rate = m.vat_rate or 0.0
                    vat_rows[rate]["net"] += net
                    vat_rows[rate]["vat"] += gross - net
                    vat_rows[rate]["gross"] += gross
                    if not rate and m.amount:
                        zero_vat["count"] += 1
                        zero_vat["net"] += net
                    doc = receipt_docs.setdefault(m.document or "", {
                        "number": m.document or _("bez dokladu"), "date": m.date, "net": 0.0, "gross": 0.0,
                        "zero_vat": False, "layers": []})
                    doc["net"] += net
                    doc["gross"] += gross
                    doc["zero_vat"] = doc["zero_vat"] or (not rate and bool(m.amount))
                    doc["layers"].append(m.winvet_ref)
            row["closing"]["qty"] = row["opening"]["qty"] + row["in"]["qty"] - row["out"]["qty"]
            row["closing"]["net"] = row["opening"]["net"] + row["in"]["net"] - row["out"]["net"]
            row["closing"]["gross"] = row["opening"]["gross"] + row["in"]["gross"] - row["out"]["gross"]

        groups = self._groups(items, info)
        totals = self._zero()
        for group in groups:
            for part in PARTS:
                for k in ("qty", "net", "gross"):
                    totals[part][k] += group["totals"][part][k]
        last_move = max((m.date for m in Move.search([], order="date desc", limit=1)), default=False)
        return {
            "clinic": self.env["elite.vet.cash.closure"]._clinic(),
            "period": period_label(date_from, date_to),
            "generated": self.env["elite.vet.cash.closure"]._now_label(),
            "groups": groups,
            "totals": totals,
            "item_count": sum(len(g["rows"]) for g in groups),
            # WinVet lets an item go below zero (more issued than received)
            "negative": sum(1 for g in groups for row in g["rows"] if row["closing"]["qty"] <= -0.001),
            "receipts": self._receipt_rows(receipt_docs),
            "vat_rows": [dict(v, rate=rate) for rate, v in sorted(vat_rows.items())],
            "zero_vat": zero_vat,
            "no_receipt": no_receipt,
            "last_move": last_move,
            "check": self._check_winvet(items, date_to, last_move),
            "has_data": bool(Move.search_count([])),
        }

    def _groups(self, items, info):
        by_kind = defaultdict(list)
        for key, row in items.items():
            if all(abs(row[p][k]) < EPS for p in PARTS for k in ("qty", "net")):
                continue
            move = info[key]
            item = move.item_id
            by_kind[item.kind or "other"].append({
                "code": item.code or "", "name": item.name or _("Položka %s", key),
                "unit": item.unit or move.unit or "", **row})
        groups = []
        for kind, label in KIND_ROWS:
            rows = sorted(by_kind.get(kind, []), key=lambda r: (r["name"].lower(), r["code"]))
            if not rows:
                continue
            totals = self._zero()
            for row in rows:
                for part in PARTS:
                    for k in ("net", "gross"):
                        totals[part][k] += row[part][k]
            groups.append({"label": label, "rows": rows, "totals": totals})
        return groups

    def _receipt_rows(self, docs):
        suppliers = {}
        layer_refs = [ref for doc in docs.values() for ref in doc["layers"]]
        for layer in self.env["elite.vet.winvet.stock.layer"].search([("winvet_ref", "in", layer_refs)]):
            suppliers[layer.winvet_ref] = layer.supplier
        rows = []
        for doc in docs.values():
            supplier = next((suppliers[r] for r in doc["layers"] if suppliers.get(r)), "")
            rows.append({"number": doc["number"], "date": doc["date"], "supplier": supplier or "",
                         "net": doc["net"], "vat": doc["gross"] - doc["net"], "gross": doc["gross"],
                         "zero_vat": doc["zero_vat"]})
        return sorted(rows, key=lambda r: (r["date"] or date.min, r["number"]))

    def _check_winvet(self, items, date_to, last_move):
        """Closing quantities against WinVet's current stock, when the period ends with the data."""
        if not last_move or date_to < last_move:
            return False
        # quantities of issued fractions differ in the thousandths (1,416 / 1,417): not a difference
        winvet = defaultdict(float)
        for total in self.env["elite.vet.winvet.stock.total"].search([]):
            winvet[total.item_winvet_ref] += total.total or 0.0
        keys = set(winvet) | set(items)
        differ = [k for k in keys if abs(winvet.get(k, 0.0) - (items[k]["closing"]["qty"] if k in items else 0.0))
                  >= 0.01]
        return {"items": len(keys), "differ": len(differ)}


class StockRegletaReport(models.AbstractModel):
    _name = "report.elite_vet_sale.report_stock_regleta_document"
    _description = "Regleta skladu (PDF) – data"

    @api.model
    def _get_report_values(self, docids, data=None):
        docs = self.env["elite.vet.stock.regleta.wizard"].browse(docids)
        if not self.env.user.has_group(MANAGER_GROUP):
            raise AccessError(_("Regletu skladu smí tisknout jen vedení."))
        return {"doc_ids": docids, "doc_model": "elite.vet.stock.regleta.wizard", "docs": docs,
                "money": money, "quantity_label": quantity_label}
