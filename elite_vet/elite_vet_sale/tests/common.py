from uuid import uuid4

from odoo import fields

from odoo.addons.elite_vet_clinic.tests.common import ClinicCase

PAYMENT_METHODS = {"card": "Kartou", "cash": "Hotově", "transfer": "Převodem"}


class SaleCase(ClinicCase):
    """ClinicCase with the sale/POS/stock setup of elite_vet_sale applied (idempotent)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.setup = cls.env["elite.vet.sale.setup"]
        cls.setup.ensure_setup()
        # Recepce gets the till group when the role is set (elite_vet_reception); granted here
        # too, so these tests do not depend on that module (idempotent).
        cls.reception._elite_vet_grant_till()
        cls.company = cls.env.company
        cls.pos_config = cls.setup.pos_config()
        cls.tax21 = cls.setup.tax_for_rate(21)
        cls.tax12 = cls.setup.tax_for_rate(12)
        cls.tax0 = cls.setup.tax_for_rate(0)

    def pos_session(self):
        """The open session of the Recepce till (opened when there is none). A new session starts
        in opening control; it is opened with an empty cash box as the POS UI does, so the tests do
        not depend on a session left open in the database."""
        config = self.env["elite.vet.sale.setup"].pos_config()
        if not config.current_session_id:
            config.open_ui()
        session = config.current_session_id
        if session.state == "opening_control":
            session.set_opening_control(0, "")
        return session

    def settle(self, quotation, method="card", invoice=False, order_lines=None, draft=False, link_lines=True):
        """Settle a quotation in the Recepce till as the POS UI does with pos_sale's "Settle the
        order" (one POS line per quotation line, prices incl. tax, paid in full) -> pos.order.
        `order_lines` (sale.order.line): settle only these lines (a partial settlement).
        `draft`: the order is only synced, not paid (reception still at the till).
        `link_lines` False: POS lines keep only sale_order_origin_id (no sale_order_line_id)."""
        session = self.pos_session()
        config = session.config_id
        currency = config.currency_id
        payment_method = config.payment_method_ids.filtered(lambda m: m.name == PAYMENT_METHODS[method])[:1]
        assert payment_method, "payment method %s missing on %s" % (method, config.name)
        lines = []
        for sol in (order_lines if order_lines is not None else quotation.order_line).filtered(lambda l: not l.display_type):
            taxes = sol.tax_id
            values = taxes.compute_all(sol.price_unit, currency, sol.product_uom_qty, product=sol.product_id,
                                       partner=quotation.partner_id) if taxes else {
                "total_excluded": sol.price_unit * sol.product_uom_qty,
                "total_included": sol.price_unit * sol.product_uom_qty}
            lines.append((0, 0, {
                "id": len(lines) + 1, "pack_lot_ids": [], "discount": 0.0,
                "price_unit": sol.price_unit, "product_id": sol.product_id.id, "qty": sol.product_uom_qty,
                "full_product_name": sol.name,
                "price_subtotal": values["total_excluded"], "price_subtotal_incl": values["total_included"],
                "tax_ids": [(6, 0, taxes.ids)],
                "sale_order_origin_id": quotation.id, "sale_order_line_id": sol.id if link_lines else False,
            }))
        total_incl = currency.round(sum(line[2]["price_subtotal_incl"] for line in lines))
        total_excl = currency.round(sum(line[2]["price_subtotal"] for line in lines))
        uuid = str(uuid4())
        data = {
            "amount_paid": total_incl, "amount_return": 0, "amount_tax": total_incl - total_excl,
            "amount_total": total_incl, "date_order": fields.Datetime.to_string(fields.Datetime.now()),
            "fiscal_position_id": config.default_fiscal_position_id.id, "pricelist_id": config.pricelist_id.id,
            "name": "Order %s" % uuid, "last_order_preparation_change": "{}", "lines": lines,
            "partner_id": quotation.partner_id.id, "session_id": session.id, "sequence_number": 1,
            "payment_ids": [(0, 0, {"amount": total_incl, "name": fields.Datetime.now(),
                                    "payment_method_id": payment_method.id})],
            "uuid": uuid, "user_id": self.env.uid, "to_invoice": invoice,
        }
        if draft:
            data.update({"state": "draft", "amount_paid": 0, "payment_ids": []})
        self.env["pos.order"].sync_from_ui([data])
        return self.env["pos.order"].search([("uuid", "=", uuid)])
