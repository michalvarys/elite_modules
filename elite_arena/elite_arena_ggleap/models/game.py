from odoo import api, fields, models

APP_TYPES = [
    ("Game", "Hra"),
    ("Program", "Program"),
    ("Setting", "Nastavení"),
    ("Unknown", "Neznámé"),
]
# launchers, chat, browsers, tools: launched often, but they say nothing about what people play
NOT_GAME_WORDS = (
    "steam", "epic games", "launcher", "discord", "chrome", "browser", "firefox", "edge", "opera", "settings",
    "devices", "anti cheat", "anticheat", "faceit", "battle.net", "battlenet", "ea app", "origin", "ubisoft connect", "uplay",
    "riot client", "overwolf", "spotify", "explorer", "nvidia", "teamspeak", "obs ", "youtube", "twitch",
)


def guess_is_game(name, app_type=None):
    """ggLeap marks the type of enabled apps; apps known only from old launches are guessed by name."""
    if app_type == "Game":
        return True
    if app_type in ("Program", "Setting"):
        return False
    low = (name or "").lower() + " "
    return not any(w in low for w in NOT_GAME_WORDS)


class GgleapApp(models.Model):
    """An application from the ggLeap catalog (games, launchers, tools)."""

    _name = "elite.arena.ggleap.app"
    _description = "ggLeap – hra / aplikace"
    _order = "player_count desc, name"

    name = fields.Char(string="Název", required=True)
    uuid = fields.Char(string="ID v ggLeap", required=True, index=True, readonly=True)
    app_type = fields.Selection(APP_TYPES, string="Typ v ggLeap", readonly=True)
    tags = fields.Char(string="Žánr", readonly=True, help="Štítky z ggLeapu, např. FPS, BattleRoyale, MOBA.")
    is_game = fields.Boolean(string="Je to hra", default=True,
                             help="Jen hry se počítají do přehledu a ke kontaktům. Launchery (Steam, Epic), "
                                  "Discord nebo prohlížeč ne. Ručně změněné nastavení synchronizace nepřepíše.")
    is_game_manual = fields.Boolean(string="Nastaveno ručně")
    in_catalog = fields.Boolean(string="V nabídce ggLeap", readonly=True,
                                help="Vypnuté = aplikace už v nabídce herny není, známe ji jen ze spuštění.")
    # statistics (recomputed by the sync)
    player_count = fields.Integer(string="Hráčů", readonly=True, help="Kolik různých hráčů hru někdy spustilo.")
    launch_count = fields.Integer(string="Spuštění", readonly=True)
    last_played = fields.Datetime(string="Naposledy", readonly=True)

    _sql_constraints = [("uuid_uniq", "unique(uuid)", "Aplikace z ggLeapu už existuje.")]

    def write(self, vals):
        if "is_game" in vals and not self.env.context.get("ggleap_sync"):
            vals = dict(vals, is_game_manual=True)
        return super().write(vals)

    def action_open_partners(self):
        self.ensure_one()
        return {"type": "ir.actions.act_window", "name": "Hrají %s" % self.name, "res_model": "res.partner",
                "view_mode": "list,form", "domain": [("ggleap_game_ids", "in", self.ids)]}


class GgleapAppLaunch(models.Model):
    """One start of an application on a PC (activity log "LaunchedApplication").
    Consoles and simulators do not log what is played."""

    _name = "elite.arena.ggleap.app.launch"
    _description = "ggLeap – spuštění hry"
    _order = "start desc, id desc"

    uuid = fields.Char(string="ID v ggLeap", required=True, index=True, readonly=True)
    start = fields.Datetime(string="Spuštěno", required=True, index=True, readonly=True)
    app_id = fields.Many2one("elite.arena.ggleap.app", string="Hra / aplikace", required=True, index=True,
                             ondelete="cascade", readonly=True)
    is_game = fields.Boolean(related="app_id.is_game", store=True, string="Je to hra")
    player_id = fields.Many2one("elite.arena.ggleap.player", string="Hráč", index=True, ondelete="cascade",
                                readonly=True)
    is_guest = fields.Boolean(string="Host", readonly=True)
    machine_id = fields.Many2one("elite.arena.ggleap.machine", string="Počítač", readonly=True, ondelete="set null")
    session_uuid = fields.Char(string="Sezení v ggLeap", readonly=True)

    _sql_constraints = [("uuid_uniq", "unique(uuid)", "Spuštění z ggLeapu už existuje.")]


class GgleapPlayerGame(models.Model):
    """How much one player plays one game (recomputed by the sync from the launches)."""

    _name = "elite.arena.ggleap.player.game"
    _description = "ggLeap – hra hráče"
    _order = "days desc, last_played desc"

    key = fields.Char(required=True, index=True, readonly=True)
    player_id = fields.Many2one("elite.arena.ggleap.player", string="Hráč", required=True, index=True,
                                ondelete="cascade", readonly=True)
    partner_id = fields.Many2one(related="player_id.partner_id", string="Kontakt", store=True, index=True)
    app_id = fields.Many2one("elite.arena.ggleap.app", string="Hra", required=True, index=True,
                             ondelete="cascade", readonly=True)
    days = fields.Integer(string="Dní hraní", readonly=True, help="Ve kolika různých dnech hru spustil.")
    launches = fields.Integer(string="Spuštění", readonly=True)
    first_played = fields.Datetime(string="Poprvé", readonly=True)
    last_played = fields.Datetime(string="Naposledy", readonly=True)

    _sql_constraints = [("key_uniq", "unique(key)", "Hra hráče už existuje.")]

    @api.depends("app_id", "days")
    def _compute_display_name(self):
        for rec in self:
            rec.display_name = "%s (%d dní)" % (rec.app_id.name or "", rec.days)
