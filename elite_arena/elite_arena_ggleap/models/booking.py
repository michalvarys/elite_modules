from odoo import api, fields, models


class GgleapBooking(models.Model):
    _name = "elite.arena.ggleap.booking"
    _description = "ggLeap – rezervace"
    _order = "start desc, id desc"

    name = fields.Char(string="Název", readonly=True)
    uuid = fields.Char(string="ID v ggLeap", required=True, index=True, readonly=True)
    player_id = fields.Many2one("elite.arena.ggleap.player", string="Hráč", index=True, readonly=True,
                                ondelete="set null")
    partner_id = fields.Many2one(related="player_id.partner_id", string="Kontakt", store=True)
    guest_name = fields.Char(string="Host", readonly=True)
    start = fields.Datetime(string="Začátek", index=True, readonly=True)
    duration_minutes = fields.Integer(string="Délka (min)", readonly=True)
    duration_hours = fields.Float(string="Délka (h)", compute="_compute_duration_hours", store=True)
    machine_count = fields.Integer(string="Počet PC", readonly=True)
    paid = fields.Boolean(string="Zaplaceno", readonly=True)
    finished_at = fields.Datetime(string="Ukončeno", readonly=True)
    deleted = fields.Boolean(string="Zrušeno", readonly=True)
    delete_reason = fields.Selection([("Canceled", "Zrušeno"), ("NoShow", "Nedorazil"),
                                      ("PaymentSessionExpired", "Nezaplaceno včas")],
                                     string="Důvod zrušení", readonly=True)
    state = fields.Selection([("planned", "Naplánováno"), ("done", "Proběhlo"), ("canceled", "Zrušeno"),
                              ("noshow", "Nedorazil")], string="Stav", readonly=True, index=True)

    _sql_constraints = [("uuid_uniq", "unique(uuid)", "Rezervace z ggLeapu už existuje.")]

    @api.depends("duration_minutes")
    def _compute_duration_hours(self):
        for rec in self:
            rec.duration_hours = (rec.duration_minutes or 0) / 60.0
