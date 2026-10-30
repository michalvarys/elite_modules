from datetime import datetime, time, timedelta, timezone

import pytz

from odoo import api, fields, models
from odoo.exceptions import UserError

from ..models.config import get_settings
from ..models.product import OFFER_TYPES

MAX_HOURS = 100


class GgleapGamepassWizard(models.TransientModel):
    """Adds a game pass (e.g. 1 free hour) to the player's ggLeap account."""

    _name = "elite.arena.ggleap.gamepass.wizard"
    _description = "ggLeap – přidat herní pass"

    partner_id = fields.Many2one("res.partner", string="Kontakt")
    player_id = fields.Many2one("elite.arena.ggleap.player", string="Účet v ggLeap", required=True,
                                domain="[('deleted', '=', False), ('partner_id', '=', partner_id)] if partner_id "
                                       "else [('deleted', '=', False)]")
    product_id = fields.Many2one("elite.arena.ggleap.product", string="Podle produktu", required=True,
                                 domain=[("product_type", "=", "Offers"), ("in_catalog", "=", True)],
                                 help="Pass převezme omezení produktu z ggLeapu: na kterých PC nebo konzolích "
                                      "a ve které dny platí. Např. PS5 pass jde použít jen na PS5.")
    name = fields.Char(string="Název passu", required=True, help="Tak ho hráč uvidí ve svém účtu v ggLeapu.")
    hours = fields.Float(string="Čas", required=True, default=1.0)
    valid_days = fields.Integer(string="Platí (dní)", required=True,
                                default=lambda self: get_settings(self.env)["gamepass_days"])
    expires_on = fields.Date(string="Platí do", compute="_compute_expires_on")
    start_type = fields.Selection(OFFER_TYPES[:2], string="Čas začne běžet", required=True,
                                  default="StartOnFirstUse")
    note = fields.Char(string="Důvod", help="Proč pass dostává (dotazník, narozeniny, omluva…). Zapíše se ke kontaktu.")
    restrictions = fields.Char(string="Omezení", compute="_compute_restrictions")

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        if "product_id" in fields_list and not res.get("product_id"):
            Product = self.env["elite.arena.ggleap.product"]
            domain = [("product_type", "=", "Offers"), ("in_catalog", "=", True)]
            # a free hour sold for 0 Kč (not the coin prize, which ggLeap prices at 1000 coins)
            free = Product.search(domain + [("kind", "=", "free"), ("seconds", "=", 3600)], order="price, id", limit=1)
            product = free or Product.search(domain + [("kind", "=", "free")], order="price, id", limit=1)
            res["product_id"] = product.id
            if product:
                res.setdefault("name", product.name)
                if product.seconds:
                    res.setdefault("hours", product.seconds / 3600.0)
        return res

    @api.onchange("product_id")
    def _onchange_product_id(self):
        product = self.product_id
        if product:
            self.name = product.name
            if product.seconds:
                self.hours = product.seconds / 3600.0
            if product.offer_type in ("StartOnFirstUse", "StartOnAllocation"):
                self.start_type = product.offer_type

    @api.onchange("partner_id")
    def _onchange_partner_id(self):
        if self.partner_id and self.player_id.partner_id != self.partner_id:
            self.player_id = self.partner_id.ggleap_player_ids.filtered(lambda p: not p.deleted)[:1]

    @api.depends("valid_days")
    def _compute_expires_on(self):
        today = fields.Date.context_today(self)
        for rec in self:
            rec.expires_on = today + timedelta(days=max(rec.valid_days, 0))

    @api.depends("product_id")
    def _compute_restrictions(self):
        days = {"Monday": "po", "Tuesday": "út", "Wednesday": "st", "Thursday": "čt", "Friday": "pá",
                "Saturday": "so", "Sunday": "ne"}
        for rec in self:
            parts = []
            if rec.product_id.eligible_days:
                parts.append("jen " + ", ".join(days.get(d, d) for d in rec.product_id.eligible_days.split(",")))
            if rec.product_id.eligible_pc_groups and rec.product_id.eligible_pc_groups != "[]":
                parts.append("jen na některých PC / konzolích")
            rec.restrictions = "; ".join(parts) or "bez omezení"

    def _expires_at(self):
        """End of the last valid day in the user's time zone, as naive UTC."""
        tz = pytz.timezone(self.env.user.tz or "Europe/Prague")
        local = tz.localize(datetime.combine(self.expires_on, time(23, 59, 59)))
        return local.astimezone(timezone.utc).replace(tzinfo=None)

    def action_grant(self):
        self.ensure_one()
        if not 0 < self.hours <= MAX_HOURS:
            raise UserError("Čas passu musí být víc než 0 a nejvýš %d hodin." % MAX_HOURS)
        if not 1 <= self.valid_days <= 3650:
            raise UserError("Platnost musí být 1 až 3650 dní.")
        key = "odoo-%s-gamepass-%s" % (self.env["ir.config_parameter"].sudo().get_param("database.uuid", "")[:8],
                                       self.id)
        gamepass = self.env["elite.arena.ggleap.sync"].grant_gamepass(
            self.player_id, self.product_id, round(self.hours * 3600), self.name, self._expires_at(),
            self.start_type, note=self.note, key=key)
        partner = self.player_id.partner_id
        if partner:
            body = "Přidán herní pass „%s“ (%g h), platí do %s." % (
                gamepass.name, round(gamepass.hours, 2), self.expires_on.strftime("%-d. %-m. %Y"))
            if self.note:
                body += " Důvod: %s" % self.note
            partner.sudo().message_post(body=body, subtype_xmlid="mail.mt_note",
                                        author_id=self.env.user.partner_id.id)
        self.env.user._bus_send("simple_notification", {
            "type": "success", "title": "Pass přidán",
            "message": "„%s“ je v účtu hráče %s." % (gamepass.name, self.player_id.display_label)})
        # closing the dialog reloads the form behind it, so the new pass shows up right away
        return {"type": "ir.actions.act_window_close"}
