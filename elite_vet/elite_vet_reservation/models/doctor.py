from odoo import fields, models


class VetDoctor(models.Model):
    """Seznam v Rozpisu služeb obsahuje celý tým (i sestry a recepci), protože
    se z něj skládá veřejný rozpis. Rezervace ale smí dostat jen lékařka -
    proto vlastní příznak, ne nový seznam lidí.
    """

    _inherit = "elite.vet.doctor"

    prijima_rezervace = fields.Boolean(
        string="Lékařka – přijímá rezervace",
        help="Zaškrtněte jen u veterinárních lékařek. Jen ty jde zapsat do Rozpisu "
             "lékařů a jen ty se klientům nabízejí na webu. Které úkony dělá, plyne "
             "ze specializací na její kartě v Náš tým.")

    barva = fields.Char(
        string="Barva v kalendáři",
        help="Barva jejích rezervací a služeb na tabuli. Když ji nevyberete, "
             "přidělí se automaticky – každá lékařka má jinou.")

    def vyplnit_barvy(self):
        """Lékařkám bez vybrané barvy zapíše tu automatickou, aby ji bylo vidět
        ve výběru barvy a šla jen upravit."""
        from .reservation import barva_lekarky
        for rec in self.filtered(lambda d: d.prijima_rezervace and not d.barva):
            rec.barva = barva_lekarky(rec.id)

    def write(self, vals):
        res = super().write(vals)
        if vals.get("prijima_rezervace"):
            self.vyplnit_barvy()
        return res
