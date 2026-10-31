from datetime import timedelta

from odoo import api, fields, models
from odoo.exceptions import UserError

from odoo.addons.elite_arena_ggleap.models.product import OFFER_TYPES


class ArenaReward(models.Model):
    """What a player can claim: a game pass based on a ggLeap product (e.g. 1 free hour)."""

    _name = "elite.arena.reward"
    _description = "Elite Arena – odměna"
    _order = "sequence, id"

    name = fields.Char(string="Název odměny", required=True, translate=True,
                       help="Takhle ji hráč uvidí v e-mailu, na stránce pro vyzvednutí i ve svém účtu v ggLeapu.")
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    product_id = fields.Many2one("elite.arena.ggleap.product", string="Podle produktu v ggLeapu",
                                 domain=[("product_type", "=", "Offers"), ("in_catalog", "=", True)],
                                 help="Pass převezme omezení produktu (na kterých PC / konzolích a ve které dny platí). "
                                      "Prázdné = hodina zdarma za 0 Kč („1 HODINA FREE“).")
    hours = fields.Float(string="Herní čas (h)", required=True, default=1.0)
    pass_valid_days = fields.Integer(string="Pass platí (dní od vyzvednutí)", required=True, default=14)
    claim_valid_days = fields.Integer(string="Odkaz na vyzvednutí platí (dní)", required=True, default=30)
    start_type = fields.Selection(OFFER_TYPES[:2], string="Čas začne běžet", required=True,
                                  default="StartOnFirstUse")
    description = fields.Text(string="Text na stránce vyzvednutí", translate=True,
                              help="Krátce, co hráč dostane a jak ho použije.")
    claim_ids = fields.One2many("elite.arena.reward.claim", "reward_id", string="Odkazy")
    offered_count = fields.Integer(string="Nabídnuto", compute="_compute_counts")
    claimed_count = fields.Integer(string="Vyzvednuto", compute="_compute_counts")
    claim_rate = fields.Float(string="Vyzvednuto (%)", compute="_compute_counts")

    _sql_constraints = [
        ("hours_positive", "CHECK (hours > 0 AND hours <= 100)", "Herní čas musí být víc než 0 a nejvýš 100 hodin."),
        ("days_positive", "CHECK (pass_valid_days > 0 AND claim_valid_days > 0)", "Platnost musí být aspoň 1 den."),
    ]

    @api.depends("claim_ids.state", "claim_ids.is_test")
    def _compute_counts(self):
        data = {}
        for reward_id, state, count in self.env["elite.arena.reward.claim"]._read_group(
                [("reward_id", "in", self.ids), ("is_test", "=", False)], ["reward_id", "state"], ["__count"]):
            data.setdefault(reward_id.id, {})[state] = count
        for rec in self:
            states = data.get(rec.id, {})
            rec.offered_count = sum(states.values())
            rec.claimed_count = states.get("claimed", 0)
            rec.claim_rate = 100.0 * rec.claimed_count / rec.offered_count if rec.offered_count else 0.0

    def _resolve_product(self):
        """The product the pass is based on; without one, the free hour sold for 0 Kč."""
        self.ensure_one()
        if self.product_id:
            return self.product_id
        Product = self.env["elite.arena.ggleap.product"].sudo()
        domain = [("product_type", "=", "Offers"), ("in_catalog", "=", True), ("kind", "=", "free")]
        product = (Product.search(domain + [("seconds", "=", 3600), ("price", "=", 0)], order="id", limit=1)
                   or Product.search(domain, order="price, id", limit=1))
        if not product:
            raise UserError("Odměna „%s“ nemá produkt a v ggLeapu není produkt hodiny zdarma. "
                            "Vyberte produkt u odměny (Herna → Marketing → Odměny)." % self.name)
        return product

    def create_claim(self, partner, origin, test=False):
        """A personal claim link for the partner (nothing is added in ggLeap yet)."""
        self.ensure_one()
        return self.env["elite.arena.reward.claim"].sudo().create({
            "reward_id": self.id, "partner_id": partner.id, "origin": origin, "is_test": test,
            "expires_at": fields.Datetime.now() + timedelta(days=self.claim_valid_days),
        })

    def action_open_claims(self):
        self.ensure_one()
        return {"type": "ir.actions.act_window", "name": "Odkazy · %s" % self.name,
                "res_model": "elite.arena.reward.claim", "view_mode": "list,form",
                "domain": [("reward_id", "=", self.id)]}
