from odoo import api, fields, models


class TeamIcon(models.Model):
    """Obrazek, ktery se da priradit specializaci.

    Ikony jsou zamerne zaznamy, ne pevny seznam v kodu. Klinika si je muze
    prejmenovat, zmenit poradi, schovat nebo nahrat vlastni obrazek — a nemusi
    kvuli tomu nikdo sahat do modulu.

    Modul jich pri instalaci zaklada 25 (3D emoji z Microsoft Fluent Emoji,
    MIT licence). Zaklada se jen jednou, takze upgrade nikdy neprepise to,
    co si klinika prejmenovala.
    """

    _name = "elite.vet.team.icon"
    _description = "Ikona specializace"
    _order = "sequence, name"

    name = fields.Char(
        string="Název",
        required=True,
        help="Jak se ikona jmenuje v nabídce. Slouží jen k tomu, abyste ji "
             "našli — na webu se ukazuje název specializace, ne tenhle.",
    )
    image = fields.Image(
        string="Obrázek",
        required=True,
        max_width=256,
        max_height=256,
        help="Čtvercový obrázek s průhledným pozadím. Ideálně PNG 256×256.",
    )
    sequence = fields.Integer(string="Pořadí", default=10)
    active = fields.Boolean(string="Aktivní", default=True)

    specialization_ids = fields.One2many(
        comodel_name="elite.vet.team.specialization",
        inverse_name="icon_id",
        string="Specializace",
    )

    # Ikona se da vybrat na peti mistech, ne jen u specializaci. Drive sloupec
    # ukazoval pouze je, takze vetsina ikon vypadala nepouzite i kdyz byly.
    pouziti = fields.Char(
        string="Používá se u",
        compute="_compute_pouziti",
        help="Kde všude je obrázek vybraný. Prázdné znamená, že ho zatím nikdo nepoužil.",
    )
    je_pouzita = fields.Boolean(
        string="Použitá", compute="_compute_pouziti", store=False, search="_search_je_pouzita")

    # model -> (pole s ikonou, jak tomu rikat v prehledu)
    KDE_SE_POUZIVA = [
        ("elite.vet.team.specialization", "icon_id", "specializace"),
        ("elite.vet.team.member", "badge_icon_id", "štítek"),
        ("elite.vet.service", "icon_id", "služba"),
        ("elite.vet.price.item", "icon_id", "ceník"),
        ("elite.vet.species", "icon_id", "druh"),
    ]

    def _najdi_pouziti(self):
        """Vrati {id ikony: [popis, ...]} napric vsemi misty, kde jde vybrat."""
        nalezy = {zaznam.id: [] for zaznam in self}
        for model, pole, popis in self.KDE_SE_POUZIVA:
            if model not in self.env:
                continue          # sesterský modul nemusi byt nainstalovany
            for uzivatel in self.env[model].sudo().search([(pole, "in", self.ids)]):
                nalezy[uzivatel[pole].id].append("%s: %s" % (popis, uzivatel.display_name))
        return nalezy

    @api.depends("specialization_ids")
    def _compute_pouziti(self):
        nalezy = self._najdi_pouziti()
        for zaznam in self:
            seznam = nalezy.get(zaznam.id) or []
            zaznam.pouziti = ", ".join(seznam)
            zaznam.je_pouzita = bool(seznam)

    def _search_je_pouzita(self, operator, hodnota):
        vsechny = self.search([])
        nalezy = vsechny._najdi_pouziti()
        pouzite = [i for i, seznam in nalezy.items() if seznam]
        kladne = (operator == "=") == bool(hodnota)
        return [("id", "in" if kladne else "not in", pouzite)]
