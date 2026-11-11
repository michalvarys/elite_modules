from odoo import fields, models

RESULTS = [
    ("pok", "POK"),
    ("verified", "Ověřeno"),
    ("temporary", "Dočasná chyba"),
    ("critical", "Chyba"),
    ("no_response", "Bez odpovědi"),
    ("local_error", "Chyba před odesláním"),
]


class EliteEetAttempt(models.Model):
    _name = "elite.eet.attempt"
    _description = "Pokus o odeslání do EET"
    _order = "sent_at desc, id desc"
    _rec_name = "uuid"

    device_id = fields.Many2one("elite.eet.device", "Pokladna EET", required=True, ondelete="cascade", index=True)
    company_id = fields.Many2one(related="device_id.company_id", store=True, string="Firma")
    sale_id = fields.Many2one("elite.eet.sale", "Tržba", ondelete="cascade", index=True)
    uuid = fields.Char("UUID zprávy", readonly=True)
    sent_at = fields.Datetime("Odesláno", readonly=True)
    first_send = fields.Boolean("První zaslání", readonly=True)
    verification = fields.Boolean("Ověřovací mód", readonly=True)
    request_xml = fields.Text("Odeslaná zpráva", readonly=True)
    response_xml = fields.Text("Odpověď", readonly=True)
    http_status = fields.Integer("HTTP stav", readonly=True)
    transaction_id = fields.Char("X-Global-Transaction-Id", readonly=True)
    result = fields.Selection(RESULTS, "Výsledek", readonly=True)
    code = fields.Integer("Kód chyby", readonly=True)
    message = fields.Text("Zpráva", readonly=True)
    warnings = fields.Text("Varování", readonly=True)
