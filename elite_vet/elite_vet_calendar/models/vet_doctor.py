from odoo import fields, models


class VetDoctor(models.Model):
    """Seznam lekarek pro vyber pri zadavani smeny.

    Vlastni model schvalne, ne res.partner: v nabidce maji byt jen lekarky
    kliniky, ne vsechny kontakty ze systemu.
    """

    _name = "elite.vet.doctor"
    _description = "Lékařka"
    _order = "name"

    name = fields.Char(string="Jméno", required=True)
    active = fields.Boolean(string="Aktivní", default=True)

    member_id = fields.Many2one(
        comodel_name="elite.vet.team.member",
        string="Karta v týmu",
        ondelete="set null",
        help="Propojení na kartu člověka na stránce Náš tým. Díky němu se "
             "v rozpisu u jména ukážou ikony jeho specializací. Samotné "
             "specializace se nastavují na kartě, tady se nic nepřepisuje.",
    )
    specialization_ids = fields.Many2many(
        comodel_name="elite.vet.team.specialization",
        string="Specializace",
        related="member_id.specialization_ids",
        readonly=True,
    )
