from odoo import api, fields, models

from .player import SEGMENTS


class ResPartner(models.Model):
    _inherit = "res.partner"

    ggleap_uuid = fields.Char(string="ID hráče v ggLeap", index=True, copy=False)
    ggleap_player_ids = fields.One2many("elite.arena.ggleap.player", "partner_id", string="Účty ggLeap")
    ggleap_segment = fields.Selection(SEGMENTS, string="Herna: skupina", compute="_compute_ggleap", store=True,
                                      help="Jak hráč chodí do herny (z ggLeapu). Hodí se jako filtr pro e-mailing.")
    ggleap_last_visit = fields.Datetime(string="Herna: poslední návštěva", compute="_compute_ggleap", store=True)
    ggleap_visit_count = fields.Integer(string="Herna: návštěv", compute="_compute_ggleap", store=True)
    ggleap_total_spent = fields.Float(string="Herna: utratil (Kč)", compute="_compute_ggleap", store=True)
    ggleap_days_since_visit = fields.Integer(string="Herna: dní od návštěvy", compute="_compute_ggleap", store=True)

    @api.depends("ggleap_player_ids.segment", "ggleap_player_ids.last_visit", "ggleap_player_ids.visit_count",
                 "ggleap_player_ids.total_spent", "ggleap_player_ids.days_since_visit", "ggleap_player_ids.deleted")
    def _compute_ggleap(self):
        order = [key for key, _label in SEGMENTS]
        for partner in self:
            players = partner.ggleap_player_ids.filtered(lambda p: not p.deleted) or partner.ggleap_player_ids
            if not players:
                partner.update({"ggleap_segment": False, "ggleap_last_visit": False, "ggleap_visit_count": 0,
                                "ggleap_total_spent": 0.0, "ggleap_days_since_visit": 0})
                continue
            last = max((p.last_visit for p in players if p.last_visit), default=False)
            # one person with several accounts: the "best" segment wins (most active)
            segment = min((p.segment for p in players if p.segment), key=order.index, default=False)
            partner.update({
                "ggleap_segment": segment,
                "ggleap_last_visit": last,
                "ggleap_visit_count": sum(players.mapped("visit_count")),
                "ggleap_total_spent": sum(players.mapped("total_spent")),
                "ggleap_days_since_visit": min((p.days_since_visit for p in players if p.last_visit), default=0),
            })

    def action_open_ggleap_players(self):
        self.ensure_one()
        players = self.ggleap_player_ids
        action = {"type": "ir.actions.act_window", "name": "Účty ggLeap", "res_model": "elite.arena.ggleap.player"}
        if len(players) == 1:
            return dict(action, view_mode="form", res_id=players.id)
        return dict(action, view_mode="list,form", domain=[("id", "in", players.ids)])
