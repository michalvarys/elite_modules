"""Revenue and expense dashboard: aggregated figures for the client action ``elite_vet_winvet.dashboard``.

Revenue comes from WinVet (sale lines), expenses are entered by hand (elite.vet.expense);
profit = revenue - expenses for the same period."""

from datetime import date, timedelta

from odoo import api, fields, models
from odoo.exceptions import AccessError

from odoo.addons.elite_vet_reservation.models.pet import SPECIES

SPECIES_LABELS = dict(SPECIES)

KIND_LABELS = {"service": "Úkony", "product": "Léky a zboží", "other": "Jiné"}
METHOD_LABELS = {"card": "Kartou", "cash": "Hotově", "transfer": "Převodem", "other": "Jinak"}
TOP_LIMIT = 10


class WinvetDashboard(models.AbstractModel):
    _name = "elite.vet.winvet.dashboard"
    _description = "Přehled tržeb WinVet"

    @api.model
    def _check_access(self):
        if not (self.env.user.has_group("elite_vet_reservation.group_reservation_manager")
                or self.env.user.has_group("elite_vet_winvet.group_winvet_readonly")):
            raise AccessError("Přehled tržeb je jen pro správce rezervací.")

    @api.model
    def get_data(self, date_from=None, date_to=None, compare_from=None, compare_to=None, compare=True):
        """Figures for <date_from, date_to> (ISO dates, inclusive) and a comparison period
        (given, otherwise the period of the same length right before)."""
        self._check_access()
        bounds = self._data_bounds()
        d_from = fields.Date.to_date(date_from) if date_from else (bounds["first"] or date.today())
        d_to = fields.Date.to_date(date_to) if date_to else (bounds["last"] or date.today())
        if d_to < d_from:
            d_from, d_to = d_to, d_from
        length = (d_to - d_from).days + 1
        if compare_from and compare_to:
            p_from, p_to = fields.Date.to_date(compare_from), fields.Date.to_date(compare_to)
        else:
            p_to = d_from - timedelta(days=1)
            p_from = p_to - timedelta(days=length - 1)
        return {
            "period": {"from": fields.Date.to_string(d_from), "to": fields.Date.to_string(d_to), "days": length},
            "previous": {"from": fields.Date.to_string(p_from), "to": fields.Date.to_string(p_to)},
            "bounds": {k: fields.Date.to_string(v) if v else False for k, v in bounds.items()},
            "kpi": self._kpi(d_from, d_to),
            "kpi_previous": self._kpi(p_from, p_to) if compare else False,
            "daily": self._daily(d_from, d_to),
            "by_user": self._by_user(d_from, d_to),
            "top_services": self._top(d_from, d_to, "service"),
            "top_products": self._top(d_from, d_to, "product"),
            "payment_methods": self._payment_methods(d_from, d_to),
            "species": self._species(d_from, d_to),
            "expense_categories": self._expense_categories(d_from, d_to),
            "top_expenses": self._top_expenses(d_from, d_to),
            "has_expenses": bool(self.env["elite.vet.expense"].search_count([], limit=1)),
        }

    # ------------------------------------------------------------------ helpers
    def _data_bounds(self):
        """first/last = any revenue or expense (period "from the start");
        winvet_last = newest WinVet data (shown as "data from WinVet up to ...")."""
        self.env.cr.execute("""
            select min(d), max(d) from (
                select date as d from elite_vet_sale_line where date is not null
                union all select date from elite_vet_payment where date is not null) x""")
        first, winvet_last = self.env.cr.fetchone()
        self.env.cr.execute("select min(date), max(date) from elite_vet_expense")
        exp_first, exp_last = self.env.cr.fetchone()
        if exp_last:  # monthly copies (rent) reach into the future; "from the start" ends today
            exp_last = min(exp_last, fields.Date.context_today(self))
        return {"first": min(filter(None, (first, exp_first)), default=None),
                "last": max(filter(None, (winvet_last, exp_last)), default=None),
                "winvet_last": winvet_last}

    def _line_domain(self, d_from, d_to, extra=None):
        return [("date", ">=", d_from), ("date", "<=", d_to)] + (extra or [])

    def _kpi(self, d_from, d_to):
        Line = self.env["elite.vet.sale.line"]
        out = {"revenue": 0.0, "services": 0.0, "products": 0.0, "other": 0.0}
        for group in Line._read_group(self._line_domain(d_from, d_to), ["kind"], ["amount:sum"]):
            kind, amount = group
            key = {"service": "services", "product": "products"}.get(kind, "other")
            out[key] += amount or 0.0
            out["revenue"] += amount or 0.0
        self.env.cr.execute(
            "select count(distinct visit_id) from elite_vet_sale_line "
            "where date between %s and %s and visit_id is not null", (d_from, d_to))
        out["visits"] = self.env.cr.fetchone()[0] or 0
        out["avg_per_visit"] = out["revenue"] / out["visits"] if out["visits"] else 0.0
        Payment = self.env["elite.vet.payment"]
        out["payments"] = 0.0
        for method, amount in Payment._read_group([("date", ">=", d_from), ("date", "<=", d_to)],
                                                  ["method"], ["amount:sum"]):
            out["payments_" + (method or "other")] = amount or 0.0
            out["payments"] += amount or 0.0
        out["clients"] = len(Line._read_group(self._line_domain(d_from, d_to, [("partner_id", "!=", False)]),
                                              ["partner_id"], []))
        # Expenses without VAT: a VAT payer deducts input VAT, so it is not a cost.
        [(expenses, expenses_gross, expense_count)] = self.env["elite.vet.expense"]._read_group(
            self._line_domain(d_from, d_to), [], ["amount_untaxed:sum", "amount:sum", "__count"])
        out["expenses"] = expenses or 0.0
        out["expenses_gross"] = expenses_gross or 0.0
        out["expense_count"] = expense_count
        out["profit"] = out["revenue"] - out["expenses"]
        return out

    def _daily(self, d_from, d_to):
        """One row per day: revenue by kind, expenses in total and by category id."""
        Line = self.env["elite.vet.sale.line"]
        days, day = {}, d_from
        while day <= d_to:  # every day, also the ones without revenue
            key = fields.Date.to_string(day)
            days[key] = {"date": key, "service": 0.0, "product": 0.0, "other": 0.0, "expense": 0.0, "by_category": {}}
            day += timedelta(days=1)
        for day, kind, amount in Line._read_group(self._line_domain(d_from, d_to), ["date:day", "kind"], ["amount:sum"]):
            days[fields.Date.to_string(day)][kind if kind in ("service", "product") else "other"] += amount or 0.0
        for day, category, amount in self.env["elite.vet.expense"]._read_group(
                self._line_domain(d_from, d_to), ["date:day", "category_id"], ["amount_untaxed:sum"]):
            row = days[fields.Date.to_string(day)]
            row["expense"] += amount or 0.0
            row["by_category"][str(category.id)] = row["by_category"].get(str(category.id), 0.0) + (amount or 0.0)
        return list(days.values())

    def _expense_categories(self, d_from, d_to):
        rows = [{"id": category.id, "label": category.name, "color": category.color or "#64748b",
                 "amount": amount or 0.0, "count": count}
                for category, amount, count in self.env["elite.vet.expense"]._read_group(
                    self._line_domain(d_from, d_to), ["category_id"], ["amount_untaxed:sum", "__count"])]
        return sorted(rows, key=lambda r: -r["amount"])

    def _top_expenses(self, d_from, d_to):
        return [{"id": e.id, "name": e.name, "amount": e.amount_untaxed, "date": fields.Date.to_string(e.date),
                 "category": e.category_id.name, "color": e.category_id.color or "#64748b"}
                for e in self.env["elite.vet.expense"].search(self._line_domain(d_from, d_to),
                                                              order="amount_untaxed desc", limit=TOP_LIMIT)]

    def _by_user(self, d_from, d_to):
        Line = self.env["elite.vet.sale.line"]
        users = {}
        for user, kind, amount in Line._read_group(self._line_domain(d_from, d_to), ["entered_by_id", "kind"], ["amount:sum"]):
            name = (user.doctor_id.name or user.name) if user else "Neuvedeno"
            row = users.setdefault(user.id if user else 0, {"id": user.id if user else False, "name": name,
                                                            "service": 0.0, "product": 0.0, "other": 0.0, "total": 0.0})
            row[kind if kind in ("service", "product") else "other"] += amount or 0.0
            row["total"] += amount or 0.0
        return sorted(users.values(), key=lambda r: -r["total"])

    def _top(self, d_from, d_to, kind):
        Line = self.env["elite.vet.sale.line"]
        groups = Line._read_group(self._line_domain(d_from, d_to, [("kind", "=", kind)]),
                                  ["item_name"], ["amount:sum", "quantity:sum", "__count"])
        rows = [{"name": name or "—", "amount": amount or 0.0, "quantity": qty or 0.0, "count": count}
                for name, amount, qty, count in groups]
        return sorted(rows, key=lambda r: -r["amount"])[:TOP_LIMIT]

    def _payment_methods(self, d_from, d_to):
        Payment = self.env["elite.vet.payment"]
        rows = [{"method": method or "other", "label": METHOD_LABELS.get(method or "other", method),
                 "amount": amount or 0.0, "count": count}
                for method, amount, count in Payment._read_group([("date", ">=", d_from), ("date", "<=", d_to)],
                                                                 ["method"], ["amount:sum", "__count"])]
        return sorted(rows, key=lambda r: -r["amount"])

    def _species(self, d_from, d_to):
        Line = self.env["elite.vet.sale.line"]
        rows = [{"species": species or False, "label": SPECIES_LABELS.get(species, "Neuvedeno") if species else "Neuvedeno",
                 "amount": amount or 0.0}
                for species, amount in Line._read_group(self._line_domain(d_from, d_to), ["species"], ["amount:sum"])]
        return sorted(rows, key=lambda r: -r["amount"])
