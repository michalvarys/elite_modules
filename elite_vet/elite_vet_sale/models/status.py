from odoo import fields, models


class WinvetStatus(models.Model):
    _inherit = "elite.vet.winvet.status"

    stock_mirror_warnings = fields.Text(string="Upozornění zrcadla skladu", readonly=True,
                                        help="Rozdíly a úpravy z posledního zrcadlení skladu z WinVetu "
                                             "(prázdné = bez upozornění).")
    stock_mirror_date = fields.Datetime(string="Poslední zrcadlení skladu", readonly=True)
