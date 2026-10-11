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
