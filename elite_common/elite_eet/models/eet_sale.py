from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError

FROZEN_FIELDS = ("device_id", "porad_cis", "dat_trzby", "celk_trzba", "urceno_cerp_zuct", "cerp_zuct")


class EliteEetSale(models.Model):
    _name = "elite.eet.sale"
    _description = "Tržba EET"
    _order = "dat_trzby desc, id desc"
    _rec_name = "porad_cis"

    device_id = fields.Many2one("elite.eet.device", "Pokladna EET", required=True, ondelete="restrict", index=True)
    company_id = fields.Many2one(related="device_id.company_id", store=True, string="Firma")
    currency_id = fields.Many2one(related="company_id.currency_id", string="Měna")
    source_ref = fields.Char("Doklad")
    porad_cis = fields.Char("Pořadové číslo", required=True)
    dat_trzby = fields.Datetime("Čas tržby", required=True)
    celk_trzba = fields.Monetary("Celková tržba", required=True)
    urceno_cerp_zuct = fields.Monetary("Určeno k čerpání")
    cerp_zuct = fields.Monetary("Čerpání")
    state = fields.Selection(
        [("pending", "Čeká"), ("registered", "Evidováno"), ("error", "Chyba")],
        "Stav", default="pending", required=True, index=True,
    )
    pok = fields.Char("POK", readonly=True)
    received_at = fields.Datetime("Přijato", readonly=True)
    is_test = fields.Boolean("Testovací POK", readonly=True)
    warning_text = fields.Text("Varování", readonly=True)
    last_error = fields.Text("Poslední chyba", readonly=True)
    deadline = fields.Datetime("Lhůta 48 h", compute="_compute_deadline", store=True)
    attempt_ids = fields.One2many("elite.eet.attempt", "sale_id", "Pokusy")
    attempt_count = fields.Integer("Počet pokusů", compute="_compute_attempt_count")

    _sql_constraints = [
        ("porad_cis_unique", "unique(device_id, porad_cis)", "Pořadové číslo musí být v pokladně jedinečné."),
    ]

    @api.depends("dat_trzby")
    def _compute_deadline(self):
        for sale in self:
            sale.deadline = sale.dat_trzby and sale.dat_trzby + timedelta(hours=48)

    def _compute_attempt_count(self):
        for sale in self:
            sale.attempt_count = len(sale.attempt_ids)

    def write(self, vals):
        if any(f in vals for f in FROZEN_FIELDS) and self.filtered("attempt_ids"):
            raise UserError(_("Údaje tržby, která už byla odeslána do EET, se nesmí měnit."))
        return super().write(vals)
