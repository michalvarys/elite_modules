from odoo import fields, models


class PosSession(models.Model):
    _inherit = "pos.session"

    def get_elite_closing_receipt(self):
        """Data of the printed closing receipt of this session.

        Sales, VAT and categories come from Odoo's "Daily Sale" computation (report_saledetails), so
        the receipt matches that report. Cash is computed here (see _elite_cash_details) the same way
        the closing popup does, and works for closed sessions too, so the receipt can be printed
        again later from the session. Amounts are with VAT, as the cashier sees them on the till."""
        self.ensure_one()
        # A plain POS user may close the session, but Odoo's sale-details computation also reads
        # accounting records (account.payment) a cashier has no rights to. Check access to the
        # session itself, then compute as superuser.
        self.check_access("read")
        session = self.sudo()
        details = self.env["report.point_of_sale.report_saledetails"].sudo().get_sale_details(
            session_ids=[session.id]
        )
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
        for tax in details.get("taxes", []) + details.get("refund_taxes", []):
            entry = taxes.setdefault(tax["name"], {"name": tax["name"], "base": 0.0, "tax": 0.0})
            entry["base"] += tax["base_amount"]
            entry["tax"] += tax["tax_amount"]
        vat = [{
            "name": entry["name"],
            "base": currency.round(entry["base"]),
            "tax": currency.round(entry["tax"]),
            "total": currency.round(entry["base"] + entry["tax"]),
        } for entry in taxes.values()]

        refunds = categories(details.get("refund_products", []))
        return {
            "company": session.config_id.company_id.name,
            "config": session.config_id.name,
            "session": session.name,
            "opened": fields.Datetime.to_string(session.start_at) if session.start_at else False,
            "closed": fields.Datetime.to_string(session.stop_at)
            if session.state == "closed" and session.stop_at else False,
            "user": session.user_id.name,
            "orders": details["nbr_orders"],
            "total": currency.round(details["currency"]["total_paid"]),
            "payments": session._elite_payments_per_method(),
            "cash": session._elite_cash_details(),
            "vat": vat,
            "discounts": {"count": details.get("discount_number", 0),
                          "amount": currency.round(details.get("discount_amount", 0.0))},
            "refunds": {"qty": sum(c["qty"] for c in refunds),
                        "total": currency.round(sum(c["total"] for c in refunds))},
            "rounding": details.get("cash_rounding_total", 0.0),
            "categories": categories(details.get("products", [])),
        }

    def _elite_payments_per_method(self):
        """Paid amount per payment method. Computed here rather than taken from the sale details,
        whose "payments_per_method" key exists only in recent Odoo 18 builds."""
        self.ensure_one()
        groups = self.env["pos.payment"]._read_group(
            [("session_id", "=", self.id)], ["payment_method_id"], ["amount:sum"]
        )
        methods = sorted(groups, key=lambda g: (g[0].sequence, g[0].id))
        return [{"name": method.name, "total": self.currency_id.round(amount)} for method, amount in methods]

    def _elite_cash_details(self):
        """Cash in the register, as in the closing popup (get_closing_control_data).

        On closing, Odoo adds two kinds of cash statement lines next to the cashier's cash in/out:
        the cash sales (against a receivable account) and the counting difference (against the loss
        or profit account of the cash journal). Both are left out of the moves here, so a closed
        session shows the same moves as at closing, plus the counted cash and the difference."""
        self.ensure_one()
        method = self.payment_method_ids.filtered(lambda pm: pm.type == "cash")[:1]
        if not method:
            return False
        currency = self.currency_id
        payments = sum(self._get_closed_orders().payment_ids.filtered(
            lambda p: p.payment_method_id == method).mapped("amount"))
        journal = self.cash_journal_id
        difference_accounts = journal.loss_account_id | journal.profit_account_id
        moves = []
        cash_in = cash_out = 0
        for line in self.statement_line_ids.sorted("create_date"):
            accounts = line.move_id.line_ids.account_id
            if accounts & difference_accounts or "asset_receivable" in accounts.mapped("account_type"):
                continue
            if line.amount > 0:
                cash_in += 1
                name = f"Cash in {cash_in}"
            else:
                cash_out += 1
                name = f"Cash out {cash_out}"
            moves.append({"name": line.payment_ref or name, "amount": currency.round(line.amount)})
        opening = self.cash_register_balance_start
        expected = currency.round(opening + payments + sum(m["amount"] for m in moves))
        cash = {
            "name": method.name,
            "opening": currency.round(opening),
            "payments": currency.round(payments),
            "moves": moves,
            "expected": expected,
        }
        if self.state == "closed":
            counted = currency.round(self.cash_register_balance_end_real)
            cash.update(counted=counted, difference=currency.round(counted - expected))
        return cash

    def action_print_elite_closing_receipt(self):
        """Print the closing receipt of these sessions through the browser's print dialog."""
        self.check_access("read")
        return {
            "type": "ir.actions.client",
            "tag": "elite_pos_closing_receipt.print",
            "params": {"session_ids": self.ids},
        }

