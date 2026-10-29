from odoo import api, fields, models

from .product import KINDS

STATUSES = [("Paid", "Zaplaceno"), ("Refunded", "Vráceno"), ("PartiallyRefunded", "Částečně vráceno"),
            ("Pending", "Čeká"), ("Canceled", "Zrušeno")]


class GgleapTransaction(models.Model):
    """One ggLeap transaction (sale). Only paid ones count as revenue."""

    _name = "elite.arena.ggleap.transaction"
    _description = "ggLeap – prodej"
    _order = "date desc, id desc"

    name = fields.Char(string="Číslo", readonly=True)
    uuid = fields.Char(string="ID v ggLeap", required=True, index=True, readonly=True)
    date = fields.Datetime(string="Datum", required=True, index=True, readonly=True)
    player_id = fields.Many2one("elite.arena.ggleap.player", string="Hráč", index=True, readonly=True,
                                ondelete="set null")
    partner_id = fields.Many2one(related="player_id.partner_id", string="Kontakt", store=True)
    user_uuid = fields.Char(string="ID hráče v ggLeap", readonly=True)
    employee = fields.Char(string="Obsluha", readonly=True)
    tx_type = fields.Char(string="Typ", readonly=True)
    source = fields.Selection([("Employee", "Na pokladně"), ("AutomaticClientOrder", "Objednávka z PC"),
                               ("ManualClientOrder", "Objednávka z PC (ručně)"),
                               ("BalancePaymentForOrder", "Platba z kreditu")],
                              string="Kde", readonly=True)
    status = fields.Selection(STATUSES, string="Stav", readonly=True, index=True)
    is_paid = fields.Boolean(string="Počítá se do tržeb", readonly=True, index=True)
    refunded_at = fields.Datetime(string="Vráceno dne", readonly=True)
    amount = fields.Float(string="Celkem (Kč)", readonly=True)
    discount = fields.Float(string="Sleva (Kč)", readonly=True)
    paid_cash = fields.Float(string="Hotově", readonly=True)
    paid_card = fields.Float(string="Kartou", readonly=True)
    paid_balance = fields.Float(string="Z kreditu", readonly=True)
    coupon_code = fields.Char(string="Kupon", readonly=True)
    content_hash = fields.Char(readonly=True)
    line_ids = fields.One2many("elite.arena.ggleap.transaction.line", "transaction_id", string="Položky",
                               readonly=True)

    _sql_constraints = [("uuid_uniq", "unique(uuid)", "Prodej z ggLeapu už existuje.")]


class GgleapTransactionLine(models.Model):
    _name = "elite.arena.ggleap.transaction.line"
    _description = "ggLeap – položka prodeje"
    _order = "date desc, id"

    transaction_id = fields.Many2one("elite.arena.ggleap.transaction", required=True, ondelete="cascade",
                                     index=True, readonly=True)
    date = fields.Datetime(related="transaction_id.date", store=True, index=True)
    player_id = fields.Many2one(related="transaction_id.player_id", store=True, string="Hráč")
    is_paid = fields.Boolean(related="transaction_id.is_paid", store=True, string="Počítá se do tržeb")
    status = fields.Selection(related="transaction_id.status", store=True)
    product_id = fields.Many2one("elite.arena.ggleap.product", string="Produkt", index=True, readonly=True)
    name = fields.Char(string="Položka", readonly=True)
    kind = fields.Selection(KINDS, string="Druh", readonly=True, index=True)
    quantity = fields.Float(string="Množství", readonly=True)
    amount = fields.Float(string="Celkem (Kč)", readonly=True,
                          help="Skutečně zaplaceno: položky prodeje se přepočítají na celkovou cenu prodeje "
                               "(hodina zdarma za coiny má cenu 0, i když má v ceníku hodnotu).")
    list_amount = fields.Float(string="Hodnota podle ceníku (Kč)", readonly=True)
    discount = fields.Float(string="Sleva (Kč)", readonly=True)
    hours = fields.Float(string="Herní čas (h)", readonly=True,
                         help="Množství × herní čas produktu (jen u hraní).")

    @api.depends("name", "transaction_id")
    def _compute_display_name(self):
        for rec in self:
            rec.display_name = rec.name or rec.transaction_id.name or ""
