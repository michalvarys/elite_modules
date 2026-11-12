import logging
from datetime import timedelta

from odoo import _, api, fields, models

from odoo.addons.elite_eet.eet import fields as eet_fields

_logger = logging.getLogger(__name__)

# An order reaching the server later than this after payment was not sent at
# payment (till offline), so EET gets it as a repeated sending.
LATE_SYNC = timedelta(minutes=5)


class PosOrder(models.Model):
    _inherit = "pos.order"

    eet_sale_ids = fields.One2many("elite.eet.sale", "pos_order_id", "Tržby EET")
    eet_sale_id = fields.Many2one("elite.eet.sale", "Tržba EET", compute="_compute_eet_sale")
    eet_state = fields.Selection(
        [("pending", "Čeká"), ("registered", "Evidováno"), ("error", "Chyba")],
        "Stav EET", compute="_compute_eet_sale",
    )
    eet_pok = fields.Char("POK", compute="_compute_eet_sale")

    @api.depends("eet_sale_ids.state", "eet_sale_ids.pok")
    def _compute_eet_sale(self):
        for order in self:
            sale = order.eet_sale_ids[:1]
            order.eet_sale_id = sale
            order.eet_state = sale.state
            order.eet_pok = sale.pok

    @api.model
    def sync_from_ui(self, orders):
        return super(PosOrder, self.with_context(elite_eet_from_ui=True)).sync_from_ui(orders)

    def _process_saved_order(self, draft):
        order_id = super()._process_saved_order(draft)
        if not draft and self.env.context.get("elite_eet_from_ui") and self.state in ("paid", "done", "invoiced"):
            # An EET problem must never stop the till from saving a paid order.
            try:
                with self.env.cr.savepoint():
                    self._eet_create_sale()
            except Exception:  # noqa: BLE001
                _logger.exception("EET: no sale created for POS order %s", self.id)
                device = self.sudo().config_id.eet_device_id
                if device:
                    device._eet_notify(
                        _("Tržba EET nevznikla"),
                        _("U objednávky %s se nepodařilo vytvořit tržbu EET. Zkontrolujte ji a evidujte ručně.",
                          self.name),
                    )
        return order_id

    def _eet_porad_cis(self):
        """Receipt number for EET: unique by construction (order id), max 25 characters.

        Odoo names every refund of an order the same ("<order> REFUND"), and long till
        names would lose the sequence number when truncated, so the id is appended.
        """
        self.ensure_one()
        suffix = "#%s" % self.id
        base = eet_fields.sanitize_text(self.name or "", 25 - len(suffix)) if self.name else ""
        return "%s%s" % (base, suffix)

    def _eet_create_sale(self):
        """Create the EET sale of a paid till order and send it after commit."""
        self.ensure_one()
        order = self.sudo()
        device = order.config_id.eet_device_id
        if (
            not device
            or not device.active_eet
            or (device.start_datetime and order.date_order < device.start_datetime)
            or order.eet_sale_ids
        ):
            return self.env["elite.eet.sale"]
        payments = order.payment_ids.filtered(lambda p: p.payment_method_id.eet_register)
        if not payments:
            return self.env["elite.eet.sale"]
        sale = self.env["elite.eet.sale"].sudo().create({
            "device_id": device.id,
            "pos_order_id": order.id,
            "source_ref": order.name,
            "porad_cis": order._eet_porad_cis(),
            "dat_trzby": order.date_order,
            "celk_trzba": sum(payments.mapped("amount")),
            "cerp_zuct": sum(payments.filtered(lambda p: p.payment_method_id.eet_voucher_redemption).mapped("amount")),
            "urceno_cerp_zuct": sum(
                order.lines.filtered(lambda line: line.product_id.eet_prepaid_voucher).mapped("price_subtotal_incl")
            ),
        })
        first_send = fields.Datetime.now() - order.date_order <= LATE_SYNC
        sale._eet_send_after_commit(first_send=first_send)
        return sale
