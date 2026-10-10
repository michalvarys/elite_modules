from odoo import api, fields, models

# Tituly, ktere se pri skladani inicial preskakuji - z "MVDr. Kateřina Kadavá"
# ma vyjit KK, ne MK.
TITULY = {
    "mvdr", "mudr", "mddr", "judr", "rndr", "phdr", "paeddr", "pharmdr",
    "ing", "bc", "mgr", "dis", "prof", "doc", "ph.d", "phd", "dipecvn",
}


class VetTeamMember(models.Model):
    """Jeden clovek na strance /nas-tym.

    Karta na webu se sklada presne z techto poli, takze co klinika napise sem,
    to je na webu videt - a nic jineho. Fotka je volitelna; kdyz chybi, vykresli
    se kolecko s inicialami, jak to bylo puvodne u vsech.
    """

    _name = "elite.vet.team.member"
    _description = "Člen týmu"
    _inherit = ["image.mixin"]
    _order = "sequence, id"

    name = fields.Char(string="Jméno a titul", required=True)
    section_id = fields.Many2one(
        "elite.vet.team.section",
        string="Sekce",
        required=True,
        ondelete="restrict",
        help="Do které části stránky člověk patří.",
    )
    role = fields.Char(
        string="Pozice",
        translate=True,
        help="Řádek pod jménem, například: Veterinární lékařka · interní medicína.",
    )
    email = fields.Char(
        string="E-mail",
        help="Zobrazí se na kartě jako odkaz. Nechte prázdné, když ho zveřejnit nechcete.",
    )
    badge = fields.Char(
        string="Štítek na kartě",
        translate=True,
        help="Tmavý štítek nad popisem. Napište si do něj cokoliv — Odborná "
             "garantka, Vedoucí lékařka, Novinka v týmu. Když ho necháte "
             "prázdný, na kartě nebude.",
    )
    badge_icon_id = fields.Many2one(
        comodel_name="elite.vet.team.icon",
        string="Ikona štítku",
        ondelete="set null",
        help="Obrázek ve štítku, před textem. Když ho nevyberete, zůstane "
             "tam fajfka jako doteď.",
    )
    badge_icon_image = fields.Image(
        string="Náhled ikony štítku",
        related="badge_icon_id.image",
        readonly=True,
    )

    specialization_ids = fields.Many2many(
        comodel_name="elite.vet.team.specialization",
        relation="elite_vet_team_member_specialization_rel",
        column1="member_id",
        column2="specialization_id",
        string="Specializace",
        help="Na kartě se ukážou jako štítky s ikonou. V rozpisu služeb "
             "se u jména objeví jen samotné ikony, bez popisků.",
    )
    perex = fields.Text(
        string="Popis",
        translate=True,
        help="Odstavec, který je na kartě vidět hned. Delší údaje patří níž do Podrobností.",
    )
    fact_ids = fields.One2many(
        "elite.vet.team.fact", "member_id", string="Podrobnosti",
        default=lambda self: self._default_fact_ids(),
        help="Rozbalovací část karty: Vzdělání, Praxe, Specializace, Jazyky…",
    )
    highlight = fields.Boolean(
        string="Zvýraznit kartu",
        help="Karta dostane světlé pozadí a tmavší kolečko. "
             "Hodí se pro garantku kliniky; nechte na jednom člověku.",
    )
    sequence = fields.Integer(string="Pořadí", default=10)
    active = fields.Boolean(string="Aktivní", default=True)

    initials = fields.Char(string="Iniciály", compute="_compute_initials")
    has_image = fields.Boolean(compute="_compute_has_image")

    @api.depends("name")
    def _compute_initials(self):
        for rec in self:
            pismena = []
            for slovo in (rec.name or "").replace(",", " ").split():
                ocesane = slovo.strip(".").lower()
                if not ocesane or ocesane in TITULY:
                    continue
                pismena.append(slovo[0].upper())
                if len(pismena) == 2:
                    break
            rec.initials = "".join(pismena) or "?"

    @api.depends("image_1920")
    def _compute_has_image(self):
        for rec in self:
            rec.has_image = bool(rec.image_1920)

    def _default_fact_ids(self):
        """Novy clovek dostane rovnou prazdne radky s beznymi popisky.

        Vyplnovat se pak jen dopisuje text vedle, misto aby se u kazdeho
        cloveka znovu vybiralo Vzdelani, Praxe, Jazyky... Ktere popisky se
        predvyplni, urcuje zaskrtavatko Predvyplnit v Popiscich podrobnosti,
        takze si to klinika muze zmenit sama. Radek bez textu se na web
        nedostane, takze prebyvajici nevadi.
        """
        labels = self.env["elite.vet.team.fact.label"].search(
            [("is_default", "=", True)], order="sequence, id"
        )
        return [
            (0, 0, {"label_id": label.id, "sequence": (i + 1) * 10})
            for i, label in enumerate(labels)
        ]
