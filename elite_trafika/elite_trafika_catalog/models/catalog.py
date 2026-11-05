import re

from odoo import api, fields, models

DEFAULT_SOURCE = "web"


class EliteTrafikaCatalogItem(models.Model):
    _name = "elite.trafika.catalog.item"
    _description = "Výrobek v katalogu trafiky"
    _inherit = ["image.mixin"]
    _order = "sequence, id"

    name = fields.Char("Název", required=True)
    kind = fields.Selection([("flower", "Květy"), ("herbal", "Bylinné směsi"), ("stick", "Aroma tyčinky")],
                            "Druh", required=True)
    pack = fields.Char("Balení", help="Zobrazí se na kartě výrobku, např. 1 g.")
    aroma = fields.Char("Vůně", help="Krátký popis na kartě výrobku. Nepište účinky ani použití.")
    ean = fields.Char("EAN")
    in_store = fields.Boolean("V prodejně", help="Na kartě se ukáže, že výrobek u nás koupíš už teď.")
    sequence = fields.Integer("Pořadí", default=10)
    active = fields.Boolean("Zveřejněno", default=True)
    like_ids = fields.One2many("elite.trafika.catalog.like", "item_id", "Zájem")
    like_count = fields.Integer("Líbí se", compute="_compute_like_count", store=True)

    @api.depends("like_ids")
    def _compute_like_count(self):
        for item in self:
            item.like_count = len(item.like_ids)

    def set_liked(self, liked, source=None):
        """Records or withdraws one anonymous like; a withdrawal removes the newest like of the source."""
        self.ensure_one()
        source = self.env["elite.trafika.catalog.like"].clean_source(source)
        if liked:
            self.env["elite.trafika.catalog.like"].create({"item_id": self.id, "source": source})
            return
        self.env["elite.trafika.catalog.like"].search(
            [("item_id", "=", self.id), ("source", "=", source)], order="id desc", limit=1).unlink()


class EliteTrafikaCatalogLike(models.Model):
    _name = "elite.trafika.catalog.like"
    _description = "Zájem o výrobek v katalogu"
    _order = "id desc"
    _rec_name = "item_id"

    item_id = fields.Many2one("elite.trafika.catalog.item", "Výrobek", required=True, ondelete="cascade", index=True)
    kind = fields.Selection(related="item_id.kind", store=True, string="Druh")
    source = fields.Char("Zdroj", required=True, default=DEFAULT_SOURCE, index=True)

    @api.model
    def clean_source(self, source):
        """The source comes from the link (?zdroj=instagram), so only a short plain word is kept."""
        source = (source or "").strip().lower()
        return source if re.fullmatch(r"[a-z0-9_-]{1,32}", source) else DEFAULT_SOURCE
