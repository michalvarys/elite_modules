from odoo import api, fields, models


class GgleapVisit(models.Model):
    """One game session on a PC or console: a login (LoggedIn / RemoteLoggedIn) closed by the
    matching logout, or – when ggLeap logged no logout (time ran out) – by the session from
    /sessions/get-user-sessions. One visit of the arena = one day with sessions."""

    _name = "elite.arena.ggleap.visit"
    _description = "ggLeap – herní sezení"
    _order = "start desc, id desc"
    _rec_name = "start"

    login_uuid = fields.Char(string="ID přihlášení", index=True, readonly=True)
    logout_uuid = fields.Char(string="ID odhlášení", index=True, readonly=True)
    player_id = fields.Many2one("elite.arena.ggleap.player", string="Hráč", index=True, readonly=True,
                                ondelete="cascade")
    partner_id = fields.Many2one(related="player_id.partner_id", string="Kontakt", store=True)
    is_guest = fields.Boolean(string="Host", readonly=True)
    machine_id = fields.Many2one("elite.arena.ggleap.machine", string="Počítač", index=True, readonly=True)
    device_uuid = fields.Char(string="ID konzole v ggLeap", index=True, readonly=True,
                              help="Konzole a simulátory (PS5, SIM) se v ggLeap hlásí jako zařízení, ne jako PC.")
    device_name = fields.Char(string="Konzole", readonly=True)
    place = fields.Char(string="Kde hrál", compute="_compute_place", store=True, index=True)
    start = fields.Datetime(string="Začátek", required=True, index=True, readonly=True)
    end = fields.Datetime(string="Konec", readonly=True)
    duration_hours = fields.Float(string="Délka (h)", readonly=True, aggregator="sum")
    end_source = fields.Selection([("logout", "Odhlášení"), ("session", "Sezení z ggLeap"),
                                   ("unknown", "Konec neznámý")], string="Konec podle", readonly=True)
    count = fields.Integer(string="Počet", default=1, readonly=True, aggregator="sum")

    _sql_constraints = [
        ("login_uniq", "unique(login_uuid)", "Přihlášení už je uložené."),
        ("logout_uniq", "unique(logout_uuid)", "Odhlášení už je uložené."),
    ]

    @api.depends("machine_id.name", "device_name", "device_uuid")
    def _compute_place(self):
        for rec in self:
            if rec.machine_id:
                rec.place = rec.machine_id.name
            elif rec.device_uuid or rec.device_name:
                rec.place = "Konzole %s" % (rec.device_name or rec.device_uuid[:6])
            else:
                rec.place = False

    @api.depends("start", "player_id")
    def _compute_display_name(self):
        for rec in self:
            who = rec.player_id.display_label if rec.player_id else "Host"
            rec.display_name = "%s · %s" % (who, fields.Datetime.to_string(rec.start)[:16] if rec.start else "")
