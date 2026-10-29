from odoo import api, fields, models

KINDS = [
    ("time", "Hraní"),
    ("free", "Hraní zdarma"),
    ("food", "Občerstvení"),
    ("other", "Ostatní"),
]
FREE_WORDS = ("free", "zdarma", "grátis", "gratis")


def guess_kind(name, product_type=None, price=None):
    """Kind of a sold item. ggLeap: ProductType "Offers" = play time (game pass),
    "Generic" = goods. Free play time is an offer with price 0 or "free" in its name."""
    low = (name or "").lower()
    is_time = product_type == "Offers" or any(w in low for w in ("hodin", "hour", "session", "pass", "minut"))
    if product_type == "Generic":
        return "food"
    if is_time:
        if any(w in low for w in FREE_WORDS) or (price is not None and float(price) == 0.0):
            return "free"
        return "time"
    return "other"


class GgleapProduct(models.Model):
    _name = "elite.arena.ggleap.product"
    _description = "ggLeap – produkt"
    _order = "kind, name"

    name = fields.Char(string="Název", required=True)
    uuid = fields.Char(string="ID v ggLeap", required=True, index=True, readonly=True)
    kind = fields.Selection(KINDS, string="Druh", required=True, default="other",
                            help="Odhadne se z ggLeapu; ručně změněný druh synchronizace nepřepíše.")
    kind_manual = fields.Boolean(string="Druh nastaven ručně")
    product_type = fields.Char(string="Typ v ggLeap", readonly=True)
    category_uuid = fields.Char(string="Kategorie v ggLeap", readonly=True)
    price = fields.Float(string="Cena", readonly=True)
    seconds = fields.Integer(string="Herní čas (s)", readonly=True)
    hours = fields.Float(string="Herní čas (h)", compute="_compute_hours")
    in_catalog = fields.Boolean(string="V nabídce ggLeap", readonly=True,
                                help="Vypnuté = produkt už v ggLeap není, známe ho jen z dřívějších prodejů.")
    active = fields.Boolean(default=True)

    _sql_constraints = [("uuid_uniq", "unique(uuid)", "Produkt z ggLeapu už existuje.")]

    @api.depends("seconds")
    def _compute_hours(self):
        for rec in self:
            rec.hours = (rec.seconds or 0) / 3600.0

    def write(self, vals):
        if "kind" in vals and not self.env.context.get("ggleap_sync"):
            vals = dict(vals, kind_manual=True)
        return super().write(vals)
