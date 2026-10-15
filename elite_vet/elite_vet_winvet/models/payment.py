from odoo import api, fields, models

METHODS = [("cash", "Hotově"), ("card", "Kartou"), ("transfer", "Převodem"), ("other", "Jinak")]
METHOD_CODES = {"cash": "cash", "hot": "cash", "card": "card", "platk": "card", "transfer": "transfer",
                "prev": "transfer"}


class VetPayment(models.Model):
    _name = "elite.vet.payment"
    _description = "Platba (WinVet)"
    _order = "date desc, id desc"

    winvet_ref = fields.Integer(string="ID ve WinVetu", required=True, index=True, readonly=True)
    document_id = fields.Many2one("elite.vet.sale.document", string="Doklad", index=True, ondelete="set null",
                                  readonly=True)
    document_winvet_ref = fields.Integer(string="ID dokladu ve WinVetu", index=True, readonly=True)
    partner_id = fields.Many2one("res.partner", string="Majitel", index=True, ondelete="set null", readonly=True)
    owner_winvet_ref = fields.Integer(string="ID majitele ve WinVetu", index=True, readonly=True)
    date = fields.Date(string="Datum", index=True, readonly=True)
    time = fields.Char(string="Čas", readonly=True)
    method = fields.Selection(METHODS, string="Forma úhrady", index=True, readonly=True)
    method_code = fields.Char(string="Kód formy úhrady", readonly=True,
                              help="Kód z WinVetu; u formy „Jinak“ říká, o jakou úhradu šlo.")
    currency_id = fields.Many2one("res.currency", default=lambda s: s.env.ref("base.CZK"), readonly=True)
    amount = fields.Monetary(string="Částka", readonly=True)
    from_deposit = fields.Monetary(string="Ze zálohy", readonly=True)
    state = fields.Char(string="Stav (WinVet)", readonly=True)
    refunded_date = fields.Date(string="Vráceno dne", readonly=True)

    _sql_constraints = [
        ("winvet_ref_uniq", "unique(winvet_ref)", "Platba s tímto ID z WinVetu už existuje."),
    ]

    @api.depends("date", "amount", "method")
    def _compute_display_name(self):
        methods = dict(METHODS)
        for rec in self:
            rec.display_name = "%s %s %s" % (fields.Date.to_string(rec.date) if rec.date else "",
                                             methods.get(rec.method, ""), rec.amount)
