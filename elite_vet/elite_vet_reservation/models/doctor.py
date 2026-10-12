from odoo import fields, models


class VetDoctor(models.Model):
    """Seznam v Rozpisu služeb obsahuje celý tým (i sestry a recepci), protože
    se z něj skládá veřejný rozpis. Rezervace ale smí dostat jen lékařka -
    proto vlastní příznak, ne nový seznam lidí.
    """

    _inherit = "elite.vet.doctor"

    accepts_bookings = fields.Boolean(
        string="Lékařka – přijímá rezervace",
        help="Zaškrtněte jen u veterinárních lékařek. Jen ty jde zapsat do Rozpisu "
             "lékařů a jen ty se klientům nabízejí na webu. Které úkony dělá, plyne "
             "ze specializací na její kartě v Náš tým.")

    calendar_color = fields.Char(
        string="Barva v kalendáři",
        help="Barva jejího proužku na kartách rezervací a její služby na tabuli. Když ji nevyberete, "
             "přidělí se automaticky – každá lékařka má jinou.")

    def fill_calendar_colors(self):
        """Lékařkám bez vybrané barvy zapíše tu automatickou, aby ji bylo vidět
        ve výběru barvy a šla jen upravit."""
        from .reservation import doctor_color
        for rec in self.filtered(lambda d: d.accepts_bookings and not d.calendar_color):
            rec.calendar_color = doctor_color(rec.id)

    def write(self, vals):
        res = super().write(vals)
        if vals.get("accepts_bookings"):
            self.fill_calendar_colors()
        return res
