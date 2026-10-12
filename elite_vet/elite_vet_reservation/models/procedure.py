from odoo import _, api, fields, models
from odoo.exceptions import ValidationError
from odoo.addons.elite_vet_calendar.models.vet_shift_type import COLORS

from .room import COLOR_SELECTION

# Světlé barvy jen pro úkony (karty na tabuli). Ordinace a typy směn mají dál
# jen sytou paletu z elite_vet_calendar, kterou tento modul nemění.
LIGHT_COLORS = {
    "light_blue": ("Světle modrá", "#93c5fd"),
    "light_green": ("Světle zelená", "#86efac"),
    "light_yellow": ("Žlutá", "#fde047"),
    "light_orange": ("Meruňková", "#fdba74"),
    "light_pink": ("Světle růžová", "#f9a8d4"),
    "light_purple": ("Levandulová", "#c4b5fd"),
    "light_teal": ("Mátová", "#5eead4"),
    "light_grey": ("Světle šedá", "#cbd5e1"),
}
PROCEDURE_COLORS = COLOR_SELECTION + [(k, v[0]) for k, v in LIGHT_COLORS.items()]


class VetProcedure(models.Model):
    """Úkon = důvod návštěvy, který si klient vybírá. Nese délku a barvu."""

    _name = "elite.vet.procedure"
    _description = "Úkon"
    _order = "sequence, id"

    name = fields.Char(string="Název", required=True, translate=True)
    duration = fields.Integer(string="Délka (min)", required=True, default=30)
    symbol = fields.Char(string="Zkratka", size=3, help="Písmeno na tabuli, např. V = vakcinace.")
    color = fields.Selection(PROCEDURE_COLORS, string="Barva", required=True, default="green")
    custom_color = fields.Char(
        string="Vlastní barva",
        help="Jakákoli barva podle přání. Když je vybraná, má přednost před barvou ze seznamu; "
             "výběr barvy ze seznamu ji zase smaže.")
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
    performed_by = fields.Char(compute="_compute_kdo_dela", string="Kdo dělá")
    sequence = fields.Integer(string="Pořadí", default=10)
    active = fields.Boolean(string="Aktivní", default=True)

    @api.onchange("color")
    def _onchange_color(self):
        self.custom_color = False

    @api.depends("color", "custom_color")
    def _compute_color_hex(self):
        for rec in self:
            if rec.custom_color:
                rec.color_hex = rec.custom_color
            elif rec.color in LIGHT_COLORS:
                rec.color_hex = LIGHT_COLORS[rec.color][1]
            else:
                rec.color_hex = COLORS.get(rec.color, COLORS["grey"])

    @api.depends("specialization_ids")
    def _compute_kdo_dela(self):
        for rec in self:
            if not rec.specialization_ids:
                rec.performed_by = _("kterákoli lékařka")
                continue
            names = rec.doctors_for_booking().mapped("name")
            rec.performed_by = ", ".join(names) or _("žádná lékařka – zkontrolujte specializace")

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

    def rooms_for_reception(self):
        """Ordinace, kam úkon objedná recepce: všechny aktivní (i ty, které nejsou
        online, např. Sál), omezené seznamem ordinací úkonu. Ordinační dobu
        v daný den hlídá až výpočet volných časů (open_minutes)."""
        self.ensure_one()
        return (self.room_ids or self.env["elite.vet.room"].search([])).filtered("active")

    def doctors_for_booking(self):
        """Lékařky, které úkon dělají.

        Úkon bez specializace zvládne kterákoli lékařka; úkon se specializací jen
        ta, která má na kartě v Náš tým aspoň jednu z nich. Sestry a recepce
        (bez příznaku Přijímá rezervace) nikdy.
        """
        self.ensure_one()
        doctors = self.env["elite.vet.doctor"].search([("accepts_bookings", "=", True)])
        if self.specialization_ids:
            doctors = doctors.filtered(lambda d: d.specialization_ids & self.specialization_ids)
        return doctors
