from odoo import api, fields, models

ENTITIES = [
    ("machines", "Počítače"),
    ("products", "Produkty"),
    ("players", "Hráči"),
    ("activity", "Návštěvy (přihlášení)"),
    ("transactions", "Prodeje"),
    ("bookings", "Rezervace"),
    ("gamepasses", "Herní passy"),
    ("details", "Detaily hráčů"),
    ("sessions", "Délka sezení"),
    ("partners", "Kontakty"),
    ("stats", "Skupiny hráčů"),
]


class GgleapStatus(models.Model):
    """One record (singleton) with the sync state: cursors, counters and the last error."""

    _name = "elite.arena.ggleap.status"
    _description = "Stav synchronizace ggLeap"
    _inherit = ["mail.thread"]

    name = fields.Char(string="Název", default="Synchronizace ggLeap", readonly=True)
    last_run_at = fields.Datetime(string="Poslední běh", readonly=True)
    last_success_at = fields.Datetime(string="Poslední úspěšný běh", readonly=True)
    last_run_seconds = fields.Integer(string="Trvání posledního běhu (s)", readonly=True)
    last_run_calls = fields.Integer(string="Dotazů v posledním běhu", readonly=True)
    last_error = fields.Text(string="Poslední chyba", readonly=True)
    last_error_at = fields.Datetime(string="Čas poslední chyby", readonly=True)
    message = fields.Char(string="Shrnutí", readonly=True)
    calls_date = fields.Date(string="Den počítání dotazů", readonly=True)
    calls_today = fields.Integer(string="Dotazů dnes", readonly=True)
    activity_cursor = fields.Datetime(string="Návštěvy staženy do", readonly=True)
    transaction_cursor = fields.Datetime(string="Prodeje staženy do", readonly=True)
    history_from = fields.Datetime(string="Historie od", readonly=True,
                                   help="Odkud se při prvním běhu začalo stahovat.")
    backfill_done = fields.Boolean(string="Historie stažena", readonly=True)
    entity_ids = fields.One2many("elite.arena.ggleap.status.entity", "status_id", string="Oblasti", readonly=True)
    alert = fields.Char(string="Upozornění", compute="_compute_alert")

    @api.depends("last_error_at", "last_success_at", "last_run_at")
    def _compute_alert(self):
        token = bool(self.env["ir.config_parameter"].sudo().get_param("elite_arena_ggleap.auth_token"))
        for rec in self:
            if not token:
                rec.alert = "Chybí AuthToken ggLeapu – synchronizace neběží. Doplňte ho v Konfigurace → Nastavení."
            elif rec.last_error_at and (not rec.last_success_at or rec.last_error_at > rec.last_success_at):
                rec.alert = "Poslední běh skončil chybou: %s" % (rec.last_error or "")[:200]
            else:
                rec.alert = False

    @api.model
    def get_status(self):
        rec = self.sudo().search([], limit=1)
        if not rec:
            rec = self.sudo().create({})
        return rec

    def entity(self, key):
        self.ensure_one()
        line = self.entity_ids.filtered(lambda l: l.entity == key)
        if not line:
            line = self.env["elite.arena.ggleap.status.entity"].sudo().create({"status_id": self.id, "entity": key})
        return line

    def count_calls(self, calls):
        """Adds API calls to today's counter (resets at midnight)."""
        self.ensure_one()
        today = fields.Date.context_today(self)
        if self.calls_date != today:
            self.write({"calls_date": today, "calls_today": calls})
        else:
            self.write({"calls_today": self.calls_today + calls})

    def calls_left_today(self, daily_limit):
        self.ensure_one()
        used = self.calls_today if self.calls_date == fields.Date.context_today(self) else 0
        return max(daily_limit - used, 0)

    def action_sync_now(self):
        self.env["elite.arena.ggleap.sync"].trigger()
        return {"type": "ir.actions.client", "tag": "display_notification",
                "params": {"message": "Synchronizace se spustí na pozadí během chvíle.", "type": "success"}}

    def action_relink_partners(self):
        """Players without a contact are matched again on the next run (e.g. after creating
        contacts by hand or after switching on "Zakládat kontakty")."""
        players = self.env["elite.arena.ggleap.player"].search([("partner_id", "=", False), ("deleted", "=", False)])
        players.write({"partner_dirty": True})
        return self.action_sync_now()

    def action_restart_history(self):
        """Downloads visits and sales again from the start of the history window."""
        self.ensure_one()
        self.write({"activity_cursor": False, "transaction_cursor": False, "history_from": False,
                    "backfill_done": False})
        return self.action_sync_now()


class GgleapStatusEntity(models.Model):
    _name = "elite.arena.ggleap.status.entity"
    _description = "Stav synchronizace ggLeap – oblast"
    _order = "sequence, id"

    status_id = fields.Many2one("elite.arena.ggleap.status", required=True, ondelete="cascade")
    entity = fields.Selection(ENTITIES, string="Oblast", required=True)
    sequence = fields.Integer(compute="_compute_sequence", store=True)
    last_run_at = fields.Datetime(string="Naposledy")
    created = fields.Integer(string="Nové")
    updated = fields.Integer(string="Změněné")
    total = fields.Integer(string="Celkem v Odoo")
    note = fields.Char(string="Poznámka")
    last_error = fields.Char(string="Chyba")

    @api.depends("entity")
    def _compute_sequence(self):
        order = {key: i for i, (key, _label) in enumerate(ENTITIES)}
        for rec in self:
            rec.sequence = order.get(rec.entity, 99)
