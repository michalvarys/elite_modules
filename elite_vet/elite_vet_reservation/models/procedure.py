from odoo import _, api, fields, models
from odoo.exceptions import ValidationError
from odoo.addons.elite_vet_calendar.models.vet_shift_type import COLORS

from .room import COLOR_SELECTION


class VetProcedure(models.Model):
    """Úkon = důvod návštěvy, který si klient vybírá. Nese délku a barvu."""

    _name = "elite.vet.procedure"
    _description = "Úkon"
    _order = "sequence, id"

    name = fields.Char(string="Název", required=True, translate=True)
    duration = fields.Integer(string="Délka (min)", required=True, default=30)
    symbol = fields.Char(string="Zkratka", size=3, help="Písmeno na tabuli, např. V = vakcinace.")
    color = fields.Selection(COLOR_SELECTION, string="Barva", required=True, default="green")
    color_hex = fields.Char(compute="_compute_color_hex")
    online = fields.Boolean(string="Nabízet online", default=True)
    room_ids = fields.Many2many(
        "elite.vet.room", "elite_vet_procedure_room_rel", "procedure_id", "room_id",
        string="Ordinace", help="Kde se úkon dělá. Prázdné = ve všech ordinacích rezervovatelných online.")
    specialization_ids = fields.Many2many(
        "elite.vet.team.specialization", "elite_vet_procedure_specialization_rel",
        "procedure_id", "specialization_id", string="Specializace",
        help="Kdo úkon dělá: jen lékařky s aspoň jednou z těchto specializací "
             "(na kartě v Náš tým). Prázdné = kterákoli lékařka. Podle toho web "
             "nabízí časy a lékařky.")
    client_note = fields.Text(
        string="Instrukce pro klienta", translate=True,
        help="Ukáže se ve výběru i v potvrzovacím e-mailu, např. „Zvíře musí být nalačno 8–12 hodin“.")
    deposit_required = fields.Boolean(string="Vyžaduje zálohu")
    deposit_amount = fields.Monetary(string="Záloha", currency_field="currency_id")
    currency_id = fields.Many2one("res.currency", default=lambda self: self.env.company.currency_id)
    kdo_dela = fields.Char(compute="_compute_kdo_dela", string="Kdo dělá")
    sequence = fields.Integer(string="Pořadí", default=10)
    active = fields.Boolean(string="Aktivní", default=True)

    @api.depends("color")
    def _compute_color_hex(self):
        for rec in self:
            rec.color_hex = COLORS.get(rec.color, COLORS["grey"])

    @api.depends("specialization_ids")
    def _compute_kdo_dela(self):
        for rec in self:
            if not rec.specialization_ids:
                rec.kdo_dela = _("kterákoli lékařka")
                continue
            names = rec.doctors_for_booking().mapped("name")
            rec.kdo_dela = ", ".join(names) or _("žádná lékařka – zkontrolujte specializace")

    @api.constrains("duration")
    def _check_duration(self):
        for rec in self:
            if rec.duration <= 0 or rec.duration % 5:
                raise ValidationError(_("Délka úkonu musí být kladný násobek 5 minut."))

    @api.constrains("deposit_required", "deposit_amount")
    def _check_deposit(self):
        for rec in self:
            if rec.deposit_required and rec.deposit_amount <= 0:
                raise ValidationError(_("U úkonu se zálohou vyplňte částku zálohy."))

    def rooms_for_booking(self):
        """Ordinace, kam se dá úkon objednat online."""
        self.ensure_one()
        rooms = self.room_ids or self.env["elite.vet.room"].search([])
        return rooms.filtered("online")

    def doctors_for_booking(self):
        """Lékařky, které úkon dělají.

        Úkon bez specializace zvládne kterákoli lékařka; úkon se specializací jen
        ta, která má na kartě v Náš tým aspoň jednu z nich. Sestry a recepce
        (bez příznaku Přijímá rezervace) nikdy.
        """
        self.ensure_one()
        doctors = self.env["elite.vet.doctor"].search([("prijima_rezervace", "=", True)])
        if self.specialization_ids:
            doctors = doctors.filtered(lambda d: d.specialization_ids & self.specialization_ids)
        return doctors
