import logging
import secrets
from datetime import datetime, time, timedelta, timezone

import pytz

from odoo import api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

STATES = [
    ("offered", "Čeká na vyzvednutí"),
    ("claimed", "Vyzvednuto"),
    ("expired", "Propadlo"),
    ("canceled", "Zrušeno"),
]


class ArenaRewardClaim(models.Model):
    """A personal link to one reward. The pass is added in ggLeap only when the player
    clicks "Vyzvednout" on the web page (/odmena/<token>)."""

    _name = "elite.arena.reward.claim"
    _description = "Elite Arena – odměna k vyzvednutí"
    _order = "create_date desc, id desc"
    _rec_name = "reward_id"

    token = fields.Char(required=True, readonly=True, index=True, copy=False,
                        default=lambda self: secrets.token_urlsafe(18))
    reward_id = fields.Many2one("elite.arena.reward", string="Odměna", required=True, readonly=True,
                                ondelete="restrict")
    partner_id = fields.Many2one("res.partner", string="Kontakt", required=True, readonly=True, index=True,
                                 ondelete="cascade")
    origin = fields.Char(string="Odkud", readonly=True, help="Který e-mail nebo dotazník odkaz poslal.")
    state = fields.Selection(STATES, string="Stav", required=True, default="offered", readonly=True, index=True)
    is_test = fields.Boolean(string="Zkušební", readonly=True,
                             help="Zkušební odkaz ze zkušebního e-mailu: stránka jde otevřít, ale nic se nepřidá.")
    expires_at = fields.Datetime(string="Odkaz platí do", readonly=True)
    visited_at = fields.Datetime(string="Poprvé otevřeno", readonly=True)
    claimed_at = fields.Datetime(string="Vyzvednuto", readonly=True)
    player_id = fields.Many2one("elite.arena.ggleap.player", string="Účet v ggLeap", readonly=True)
    gamepass_id = fields.Many2one("elite.arena.ggleap.gamepass", string="Přidaný pass", readonly=True)
    last_error = fields.Char(string="Poslední chyba", readonly=True)
    url = fields.Char(string="Odkaz", compute="_compute_url")

    _sql_constraints = [("token_uniq", "unique(token)", "Kód odkazu už existuje.")]

    def _compute_url(self):
        base = self.env["ir.config_parameter"].sudo().get_param("web.base.url", "")
        for rec in self:
            rec.url = "%s/odmena/%s" % (base, rec.token)

    # ------------------------------------------------------------------ helpers
    @api.model
    def _tz(self):
        return pytz.timezone(self.env.user.tz or "Europe/Prague")

    @api.model
    def date_text(self, value):
        """Czech date ("30. 11. 2026") in Prague time, whatever the visitor's language."""
        if not value:
            return ""
        return pytz.utc.localize(value).astimezone(self._tz()).strftime("%-d. %-m. %Y")

    def _pass_expires_at(self, now):
        """End of the last valid day of the pass (Prague time), as naive UTC."""
        tz = self._tz()
        last_day = now.replace(tzinfo=timezone.utc).astimezone(tz).date() + timedelta(days=self.reward_id.pass_valid_days)
        return tz.localize(datetime.combine(last_day, time(23, 59, 59))).astimezone(timezone.utc).replace(tzinfo=None)

    def _player(self):
        """The partner's ggLeap account: the one used most recently."""
        players = self.partner_id.ggleap_player_ids.filtered(lambda p: not p.deleted)
        return players.sorted(lambda p: p.last_visit or datetime.min, reverse=True)[:1]

    @property
    def is_open(self):
        return self.state == "offered" and not (self.expires_at and self.expires_at < fields.Datetime.now())

    def mark_visited(self):
        for rec in self.filtered(lambda r: not r.visited_at):
            rec.visited_at = fields.Datetime.now()

    # ------------------------------------------------------------------ claim
    def claim(self):
        """Adds the pass in ggLeap. Safe against double clicks: the row is locked and ggLeap
        gets the same idempotency key every time. Returns the claim; raises UserError with a
        text that can be shown to the player."""
        self.ensure_one()
        self.env.cr.execute("SELECT id FROM elite_arena_reward_claim WHERE id = %s FOR UPDATE", (self.id,))
        self.invalidate_recordset()
        if self.state == "claimed":
            return self
        if not self.is_open:
            raise UserError("Platnost odkazu už vypršela.")
        if self.is_test:
            raise UserError("Tohle je zkušební odkaz, odměna se nepřidá.")
        player = self._player()
        if not player:
            raise UserError("K tvému e-mailu jsme nenašli herní účet. Ozvi se nám prosím na baru, odměnu ti přidáme ručně.")
        reward = self.reward_id
        now = fields.Datetime.now()
        key = "odoo-%s-claim-%s" % (self.env["ir.config_parameter"].sudo().get_param("database.uuid", "")[:8],
                                    self.id)
        sync = self.env["elite.arena.ggleap.sync"].with_user(self.env.ref("base.user_root")).sudo()
        try:
            gamepass = sync.grant_gamepass(player, reward._resolve_product(), round(reward.hours * 3600),
                                           reward.name, self._pass_expires_at(now), reward.start_type,
                                           note="Odměna: %s" % (self.origin or reward.name), key=key)
        except UserError as err:
            _logger.warning("Odměna %s se nepřidala: %s", self.id, err)
            self.write({"last_error": str(err)[:250]})
            raise UserError("Odměnu se teď nepodařilo přidat. Zkus to prosím za chvíli znovu.") from err
        self.write({"state": "claimed", "claimed_at": now, "player_id": player.id, "gamepass_id": gamepass.id,
                    "last_error": False})
        self.partner_id.message_post(
            body="Hráč si vyzvedl odměnu „%s“ (%s)." % (reward.name, self.origin or "odkaz"),
            subtype_xmlid="mail.mt_note", author_id=self.env.ref("base.partner_root").id)
        return self

    def action_claim_for_player(self):
        """Back office: add the reward for the player (e.g. the web page failed)."""
        for rec in self:
            rec.claim()
        return True

    def action_cancel(self):
        self.filtered(lambda r: r.state == "offered").write({"state": "canceled"})

    @api.model
    def _cron_expire(self):
        self.search([("state", "=", "offered"), ("expires_at", "<", fields.Datetime.now())]).write(
            {"state": "expired"})
