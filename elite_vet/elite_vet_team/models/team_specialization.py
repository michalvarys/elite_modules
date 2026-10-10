from odoo import fields, models


class TeamSpecialization(models.Model):
    """Specializace lekare — nazev plus ikona.

    Co je tady, to je na webu. Klinika prida zaznam a objevi se ve
    vysvetlivkach rozpisu; smaze ho a zmizi. Stejne se chovaji typy smen,
    takze to drzi jednu logiku.
    """

    _name = "elite.vet.team.specialization"
    _description = "Specializace lékaře"
    _order = "sequence, name"

    name = fields.Char(string="Název", required=True, translate=True)
    sequence = fields.Integer(string="Pořadí", default=10)
    active = fields.Boolean(string="Aktivní", default=True)

    icon_id = fields.Many2one(
        comodel_name="elite.vet.team.icon",
        string="Ikona",
        required=True,
        ondelete="restrict",
        help="Obrázek u názvu. Ikony se spravují v Náš tým → Ikony, kde si "
             "je můžete přejmenovat nebo nahrát vlastní.",
    )

    icon_image = fields.Image(
        string="Obrázek",
        related="icon_id.image",
        readonly=True,
        help="Náhled vybrané ikony. Mění se výběrem v poli Ikona.",
    )

    member_ids = fields.Many2many(
        comodel_name="elite.vet.team.member",
        relation="elite_vet_team_member_specialization_rel",
        column1="specialization_id",
        column2="member_id",
        string="Lékaři",
    )

    _sql_constraints = [
        ("name_uniq", "unique(name)", "Specializace s tímhle názvem už existuje."),
    ]
