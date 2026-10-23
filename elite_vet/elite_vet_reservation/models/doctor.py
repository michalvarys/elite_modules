from odoo import fields, models


class VetDoctor(models.Model):
    """The shift roster list contains the whole team (nurses and reception too),
    because the public roster is built from it. Only a doctor may get reservations,
    hence a dedicated flag rather than a new list of people.
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

    default_room_id = fields.Many2one(
        "elite.vet.room", string="Výchozí ordinace", ondelete="set null",
        help="Ordinace, která se jí předvyplní u nové směny v Rozpisu služeb. Směna s ordinací "
             "se sama propíše do Rozpisu lékařů v rezervacích. U směny jde ordinaci změnit "
             "nebo smazat (pak se směna do rezervací nepropíše).")

    def fill_calendar_colors(self):
        """Store the automatic color on doctors without a chosen one, so it shows
        in the color picker and can simply be adjusted."""
        from .reservation import doctor_color
        for rec in self.filtered(lambda d: d.accepts_bookings and not d.calendar_color):
            rec.calendar_color = doctor_color(rec.id)

    def write(self, vals):
        res = super().write(vals)
        if vals.get("accepts_bookings"):
            self.fill_calendar_colors()
        return res
