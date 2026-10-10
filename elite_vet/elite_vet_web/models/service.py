from odoo import api, fields, models


class EliteVetService(models.Model):
    """Sluzba, ktera se vypisuje na domovske strance.

    Zamerne to neni jen text v sablone: klinika si sluzby pridava, prejmenovava
    a preskladava sama v Odoo, vcetne prekladu. Co tady neni, na webu nebude.
    """

    _name = "elite.vet.service"
    _description = "Elite Vet - sluzba na webu"
    _order = "sequence, id"

    name = fields.Char("Název", required=True, translate=True)
    description = fields.Text("Popis", translate=True,
                              help="Text pod nazvem. Na mobilu se ukaze po rozkliknuti.")
    sequence = fields.Integer("Pořadí", default=10)
    active = fields.Boolean("Aktivní", default=True,
                            help="Vypnuta sluzba na webu zmizi, ale zustane v seznamu.")

    # Vychozi obrazkova sada stranky. Kdyz klinice zadna nesedi, nahraje si
    # vlastni ikonu v Nas tym -> Ikony a vybere ji v poli nize.
    icon_code = fields.Selection(
        selection=[
            ("prevence", "Prevence (fajfka)"),
            ("chirurgie", "Chirurgie (křížek)"),
            ("interni", "Interní medicína (srdce)"),
            ("diagnostika", "Diagnostika (slunce)"),
            ("stomatologie", "Stomatologie (zub)"),
            ("oftalmologie", "Oftalmologie (oko)"),
            ("dermatologie", "Dermatologie (zámek)"),
            ("ultrazvuk", "Ultrazvuk (křivka)"),
        ],
        string="Kreslená ikona", default="prevence",
        help="Jednoduchá čárová ikona v barvě webu. Použije se, pokud není vybrán vlastní obrázek.")
    icon_id = fields.Many2one(
        "elite.vet.team.icon", string="Vlastní ikona", ondelete="set null",
        help="Barevný obrázek ze sady ikon. Má přednost před kreslenou ikonou.")
    icon_image = fields.Image("Náhled", related="icon_id.image", readonly=True)

    @api.model
    def sluzby_na_web(self):
        """Sluzby pro sablonu. Neaktivni se do vypisu nedostanou."""
        return self.sudo().search([])
