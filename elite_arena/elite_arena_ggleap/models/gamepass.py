from odoo import api, fields, models

from .product import OFFER_TYPES

STATES = [
    ("active", "Platný"),
    ("used", "Vyčerpaný"),
    ("expired", "Propadlý"),
    ("removed", "Odebraný"),
]


def pass_state(seconds, seconds_used, consumed_at, removed_at, expires_at, now):
    """State of a game pass and the hours that are still left on it."""
    if removed_at:
        return "removed", 0.0
    if consumed_at or (seconds and seconds_used >= seconds):
        return "used", 0.0
    if expires_at and expires_at < now:
        return "expired", 0.0
    return "active", max((seconds or 0) - (seconds_used or 0), 0) / 3600.0


class GgleapGamepass(models.Model):
    """Game pass (prepaid play time) on a player's ggLeap account: bought at the counter,
    won as a prize or added from Odoo. Data come from ggLeap; Odoo only adds new ones."""

    _name = "elite.arena.ggleap.gamepass"
    _description = "ggLeap – herní pass"
    _order = "added_at desc, id desc"

    uuid = fields.Char(string="ID v ggLeap", required=True, index=True, readonly=True)
    player_id = fields.Many2one("elite.arena.ggleap.player", string="Hráč", required=True, index=True,
                                ondelete="cascade", readonly=True)
    partner_id = fields.Many2one(related="player_id.partner_id", string="Kontakt", store=True, index=True)
    product_id = fields.Many2one("elite.arena.ggleap.product", string="Produkt", readonly=True, ondelete="set null")
    offer_uuid = fields.Char(string="ID produktu v ggLeap", readonly=True)
    name = fields.Char(string="Pass", readonly=True)
    seconds = fields.Integer(string="Čas (s)", readonly=True)
    seconds_used = fields.Integer(string="Využito (s)", readonly=True)
    hours = fields.Float(string="Hodin", compute="_compute_hours", store=True)
    hours_used = fields.Float(string="Využito (h)", compute="_compute_hours", store=True)
    hours_left = fields.Float(string="Zbývá (h)", readonly=True)
    state = fields.Selection(STATES, string="Stav", readonly=True, index=True, default="active")
    pass_type = fields.Selection(OFFER_TYPES, string="Začne běžet", readonly=True)
    priority = fields.Char(string="Priorita", readonly=True)
    added_at = fields.Datetime(string="Přidán", readonly=True)
    started_at = fields.Datetime(string="Začal", readonly=True)
    consumed_at = fields.Datetime(string="Vyčerpán", readonly=True)
    removed_at = fields.Datetime(string="Odebrán", readonly=True)
    expires_at = fields.Datetime(string="Platí do", readonly=True)
    granted_in_odoo = fields.Boolean(string="Přidán z Odoo", readonly=True)
    granted_by_id = fields.Many2one("res.users", string="Přidal", readonly=True)
    grant_note = fields.Char(string="Důvod", readonly=True)

    _sql_constraints = [("uuid_uniq", "unique(uuid)", "Pass z ggLeapu už existuje.")]

    @api.depends("seconds", "seconds_used")
    def _compute_hours(self):
        for rec in self:
            rec.hours = (rec.seconds or 0) / 3600.0
            rec.hours_used = (rec.seconds_used or 0) / 3600.0

    @api.depends("name", "hours")
    def _compute_display_name(self):
        for rec in self:
            rec.display_name = "%s (%g h)" % (rec.name or "Pass", round(rec.hours, 2))
