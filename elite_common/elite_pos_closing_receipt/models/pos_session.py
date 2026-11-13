from odoo import fields, models


class PosSession(models.Model):
    _inherit = "pos.session"

    def get_elite_closing_receipt(self):
        """Data of the printed closing receipt of this session.

        Built on the same figures as Odoo's "Daily Sale" report (report_saledetails) and on the cash
        figures of the closing popup (get_closing_control_data), so the receipt matches both. Amounts
        are with VAT, as the cashier sees them on the till."""
        self.ensure_one()
        # A plain POS user may close the session, but Odoo's sale-details computation also reads
        # accounting records (account.payment) a cashier has no rights to. Check access to the
        # session itself, then compute as superuser.
        self.check_access("read")
        session = self.sudo()
        details = self.env["report.point_of_sale.report_saledetails"].sudo().get_sale_details(
            session_ids=[session.id]
        )
        control = session.get_closing_control_data()
        currency = session.currency_id

        def categories(groups):
            result = []
            for group in groups:
                products = [{
                    "name": product["product_name"],
                    "qty": product["quantity"],
                    "total": currency.round(product["total_paid"]),
                } for product in group["products"]]
                result.append({
                    "name": str(group["name"]),
                    "qty": sum(p["qty"] for p in products),
                    "total": currency.round(sum(p["total"] for p in products)),
                    "products": products,
                })
            return result

        taxes = {}
        for tax in details["taxes"] + details["refund_taxes"]:
            entry = taxes.setdefault(tax["name"], {"name": tax["name"], "base": 0.0, "tax": 0.0})
            entry["base"] += tax["base_amount"]
            entry["tax"] += tax["tax_amount"]
        vat = [{
            "name": entry["name"],
            "base": currency.round(entry["base"]),
            "tax": currency.round(entry["tax"]),
            "total": currency.round(entry["base"] + entry["tax"]),
        } for entry in taxes.values()]

        refunds = categories(details["refund_products"])
        cash = control["default_cash_details"]
        return {
            "company": session.config_id.company_id.name,
            "config": session.config_id.name,
            "session": session.name,
            "opened": fields.Datetime.to_string(session.start_at) if session.start_at else False,
            "user": session.user_id.name,
            "orders": details["nbr_orders"],
            "total": currency.round(details["currency"]["total_paid"]),
            "payments": [{"name": p["name"], "total": currency.round(p["total"])}
                         for p in details["payments_per_method"]],
            "cash": {
                "name": cash["name"],
                "opening": cash["opening"],
                "payments": cash["payment_amount"],
                "moves": cash["moves"],
                "expected": currency.round(cash["amount"]),
            } if cash else False,
            "vat": vat,
            "discounts": {"count": details["discount_number"],
                          "amount": currency.round(details["discount_amount"])},
            "refunds": {"qty": sum(c["qty"] for c in refunds),
                        "total": currency.round(sum(c["total"] for c in refunds))},
            "rounding": details["cash_rounding_total"],
            "categories": categories(details["products"]),
        }
