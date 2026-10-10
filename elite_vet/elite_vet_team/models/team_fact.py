from odoo import fields, models


class VetTeamFactLabel(models.Model):
    """Ciselnik popisku: Vzdelani, Praxe, Specializace...

    Popisky jsou samostatny zaznam, aby se u kazdeho cloveka vybiraly ze
    seznamu misto prepisovani. Odpadaji tim preklepy a nesourode varianty
    ("Vzdelani" vs "Vzdělání"), a preklad do ciziho jazyka se dela jednou
    pro popisek, ne u kazdeho cloveka znovu.
    """

    _name = "elite.vet.team.fact.label"
    _description = "Popisek podrobnosti"
    _order = "sequence, id"

    name = fields.Char(string="Popisek", required=True, translate=True)
    sequence = fields.Integer(string="Pořadí v nabídce", default=10)
    is_default = fields.Boolean(
        string="Předvyplnit",
        help="U nového člověka se tenhle řádek nabídne rovnou prázdný, aby se "
             "jen dopsal text. Nevyplněné řádky se na web nedostanou.",
    )
    active = fields.Boolean(string="Aktivní", default=True)

    _sql_constraints = [
        ("name_unique", "unique(name)", "Takový popisek už v seznamu je."),
    ]


class VetTeamFact(models.Model):
    """Jeden radek v rozbalovaci casti karty.

    Je to samostatny model, protoze kazdy clovek jich ma jiny pocet a jine
    popisky - nedaji se natvrdo pojmenovat sloupci.
    """

    _name = "elite.vet.team.fact"
    _description = "Údaj o členovi týmu"
    _order = "sequence, id"

    member_id = fields.Many2one(
        "elite.vet.team.member", string="Člen týmu", required=True, ondelete="cascade"
    )
    label_id = fields.Many2one(
        "elite.vet.team.fact.label",
        string="Popisek",
        required=True,
        ondelete="restrict",
        help="Vyberte ze seznamu. Když tam něco chybí, napište to a Odoo nabídne "
             "založení nového popisku.",
    )
    value = fields.Text(string="Text", translate=True)
    sequence = fields.Integer(string="Pořadí", default=10)
