from odoo import api, fields, models

from odoo.addons.elite_vet_team.models.team_member import TITULY
from odoo.addons.elite_vet_reservation.models.reservation import doctor_color

STAFF_ROLES = [
    ("doctor", "Lékař"),
    ("nurse", "Sestra"),
    ("reception", "Recepce"),
    ("helper", "Výpomoc / stáž"),
]


def name_initials(name):
    """'MVDr. Kateřina Kadavá' -> 'KK' (titles skipped), the same way as Náš tým."""
    letters = []
    for word in (name or "").replace(",", " ").split():
        bare = word.strip(".").lower()
        if not bare or bare in TITULY:
            continue
        letters.append(word[0].upper())
        if len(letters) == 2:
            break
    return "".join(letters) or "?"


class VetDoctor(models.Model):
    """Staff profile for planning: the roster list already holds the whole team
    (doctors, nurses, reception), so it gets the role, contract hours and initials."""

    _inherit = "elite.vet.doctor"

    staff_role = fields.Selection(STAFF_ROLES, string="Role", default="nurse", required=True,
                                  help="Podle role se lidé řadí v Plánování a v Požadavcích na směny.")
    weekly_hours = fields.Float(string="Úvazek (h/týden)", default=40.0,
                                help="Z úvazku se počítá denní fond (úvazek / 5) a měsíční fond "
                                     "(pracovní dny měsíce bez svátků × denní fond).")
    initials = fields.Char(string="Zkratka", compute="_compute_initials", store=True, readonly=False,
                           help="Štítek v Plánování. Spočítá se ze jména, jde přepsat (např. DPI).")
    vacation_days = fields.Float(string="Dovolená na rok (dny)", default=20.0)
    vacation_taken = fields.Float(string="Vyčerpáno letos (dny)", compute="_compute_vacation")
    vacation_left = fields.Float(string="Zbývá (dny)", compute="_compute_vacation")
    planning_sequence = fields.Integer(string="Pořadí v plánu", default=10)
    in_planning = fields.Boolean(string="V plánování", default=True,
                                 help="Odškrtněte u lidí, kteří se neplánují (např. jen web).")
    planning_color = fields.Char(string="Barva štítku", compute="_compute_planning_color")

    @api.depends("name")
    def _compute_initials(self):
        for rec in self:
            rec.initials = name_initials(rec.name)

    @api.depends("calendar_color")
    def _compute_planning_color(self):
        for rec in self:
            rec.planning_color = doctor_color(rec)

    def _compute_vacation(self):
        today = fields.Date.context_today(self)
        counts = dict.fromkeys(self.ids, 0)
        if self.ids:
            groups = self.env["elite.vet.staff.request"].sudo()._read_group(
                [("member_id", "in", self.ids), ("code", "=", "D"),
                 ("date", ">=", today.replace(month=1, day=1)), ("date", "<=", today.replace(month=12, day=31))],
                ["member_id"], ["__count"])
            counts.update({member.id: count for member, count in groups})
        for rec in self:
            rec.vacation_taken = counts.get(rec.id, 0)
            rec.vacation_left = rec.vacation_days - rec.vacation_taken

    @api.onchange("accepts_bookings")
    def _onchange_accepts_bookings_role(self):
        if self.accepts_bookings:
            self.staff_role = "doctor"
