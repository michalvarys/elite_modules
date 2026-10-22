from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import float_is_zero

PAYMENT_STATES = [("none", "Bez účtu"), ("waiting", "Čeká na platbu"), ("partial", "Částečně zaplaceno"),
                  ("paid", "Zaplaceno"), ("cancelled", "Zrušeno")]
PAID_POS_STATES = ("paid", "done", "invoiced")


class ClinicalRecordSale(models.Model):
    """A finished visit record becomes a quotation (sale.order, draft) the reception settles in the POS."""

    _inherit = "elite.vet.clinical.record"

    sale_order_id = fields.Many2one("sale.order", string="Nabídka", readonly=True, copy=False,
                                    index="btree_not_null", ondelete="set null")
    payment_state = fields.Selection(PAYMENT_STATES, string="Stav platby", compute="_compute_payment_state")

    @api.depends("state", "sale_order_id.state", "sale_order_id.amount_total",
                 "sale_order_id.order_line.pos_order_line_ids.order_id.state",
                 "sale_order_id.order_line.pos_order_line_ids.price_subtotal_incl")
    def _compute_payment_state(self):
        for rec in self:
            order = rec.sale_order_id.sudo()
            if order and rec._has_pos_payment():
                # pos_sale's amount_unpaid: a deposit or a partial settlement leaves something to pay.
                paid = float_is_zero(order.amount_unpaid, precision_rounding=order.currency_id.rounding)
                rec.payment_state = "paid" if paid else "partial"
            elif rec.state == "cancelled" or order.state == "cancel":
                rec.payment_state = "cancelled"
            elif order:
                rec.payment_state = "waiting"
            else:
                rec.payment_state = "none"

    def _has_pos_payment(self):
        """Some POS order with a line of the quotation is paid (or invoiced)."""
        self.ensure_one()
        states = self.sale_order_id.sudo().order_line.pos_order_line_ids.order_id.mapped("state")
        return any(state in PAID_POS_STATES for state in states)

    # ------------------------------------------------------------------ state changes

    def _check_not_paid(self):
        states = set(self.mapped("payment_state"))
        if "paid" in states:
            raise UserError(_("Účet je už zaplacený – vrácení udělejte v pokladně jako vratku."))
        if "partial" in states:
            raise UserError(_("Na účet už je zaplacená záloha – změny udělejte v pokladně."))

    def action_done(self):
        res = super().action_done()
        for rec in self:
            if rec.payment_state in ("paid", "partial"):
                # Paid at the till while the record was reopened: the paid quotation stays as it is.
                rec.message_post(body=_("Účet už byl zaplacen v pokladně – položky účtu se nezměnily."))
            elif rec.line_ids or rec.sale_order_id:
                rec._sync_sale_order()
        return res

    def action_reopen(self):
        self._check_not_paid()
        return super().action_reopen()

    def action_cancel(self):
        self._check_not_paid()
        res = super().action_cancel()
        orders = self.sale_order_id.sudo().filtered(lambda o: o.state != "cancel")
        if orders:
            orders._action_cancel()
        return res

    # ------------------------------------------------------------------ quotation

    def _sync_sale_order(self):
        """Create or rewrite the quotation of the record from its bill lines.
        A record without lines has no quotation (an unpaid one is removed)."""
        self.ensure_one()
        self.check_access("write")
        self._check_not_paid()
        order = self.sale_order_id.sudo()
        if order.state == "sale":
            # Confirmed outside the till but never paid (checked above): back to a quotation.
            order._action_cancel()
        if not self.line_ids:
            if order:
                if order.state != "cancel":
                    order._action_cancel()
                order.unlink()
                self.sale_order_id = False
            return False
        if order.state == "cancel":
            order.action_draft()
        vals = self._sale_order_vals()
        if order:
            order.write(vals)
        else:
            order = self.env["sale.order"].sudo().create(dict(vals, clinical_record_id=self.id))
            self.sale_order_id = order
        return order

    def _sale_order_vals(self):
        self.ensure_one()
        day = self.date.strftime("%-d. %-m. %Y") if self.date else ""
        return {
            "partner_id": self.pet_id.partner_id.id,
            "pricelist_id": self.env["elite.vet.sale.setup"].pos_config().pricelist_id.id,
            "client_order_ref": " – ".join(p for p in (self.pet_id.name, day) if p),
            "order_line": [(5, 0, 0)] + [(0, 0, self._sale_line_vals(line)) for line in self.line_ids],
        }

    def _sale_line_vals(self, line):
        # An archived product (item withdrawn from the price list) is still billed as itself.
        product = line.item_id.with_context(active_test=False).product_id \
            or self.env["elite.vet.sale.setup"].free_product()
        return {
            "product_id": product.id,
            "name": line.name,
            "product_uom_qty": line.quantity,
            "price_unit": line.price_unit,  # tax included, the doctor's change of the price applies
            "sequence": line.sequence,
        }

    # ------------------------------------------------------------------ card API

    def _record_data(self):
        data = super()._record_data()
        data.update({
            "payment_state": self.payment_state,
            "payment_state_label": dict(PAYMENT_STATES)[self.payment_state],
            "sale_order_name": self.sale_order_id.sudo().name or None,
        })
        return data
