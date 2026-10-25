from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


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
             "v rozpisu v bublině u jména ukážou ikony jeho specializací. Samotné "
             "specializace se nastavují na kartě, tady se nic nepřepisuje.",
    )
    specialization_ids = fields.Many2many(
        comodel_name="elite.vet.team.specialization",
        string="Specializace",
        related="member_id.specialization_ids",
        readonly=True,
    )

    # Task 23: the account of the team member (one account per person, not tied to a room).
    user_id = fields.Many2one(
        "res.users",
        string="Účet",
        ondelete="set null",
        index="btree_not_null",
        copy=False,
        domain=[("share", "=", False)],
        help="Přihlašovací účet tohoto člena týmu. Podle něj se pozná, kdo je přihlášený: "
             "Moji pacienti dnes, obrazovka Ordinace a kdo pacienta převzal. Jeden účet patří "
             "nejvýš jednomu členovi týmu.",
    )

    # Task 27: printed under the doctor's name on the visit report for the owner.
    kvl_number = fields.Char(
        string="Číslo KVL",
        help="Číslo osvědčení Komory veterinárních lékařů. Tiskne se ve zprávě z vyšetření "
             "u jména ošetřující lékařky. Nepovinné.",
    )

    _sql_constraints = [
        ("user_unique", "unique(user_id)", "Tento účet už je propojený s jiným členem týmu."),
    ]

    @api.constrains("user_id")
    def _check_user_internal(self):
        for doctor in self:
            if doctor.user_id and doctor.user_id.share:
                raise ValidationError(_("Účet člena týmu musí být interní uživatel (ne portál): %s.")
                                      % doctor.user_id.name)
