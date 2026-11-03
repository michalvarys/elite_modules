from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

# Codes of the request table, in the order of the picker. Short labels are what the cell shows.
REQUEST_CODES = [
    ("can", "Můžu"),
    ("morning", "Jen ráno"),
    ("afternoon", "Jen odpoledne"),
    ("off", "Nemůžu / volno"),
    ("D", "Dovolená"),
    ("NV", "Náhradní volno"),
    ("L", "Lékař"),
    ("PN", "Nemoc (PN)"),
    ("S", "Školení / kongres"),
]
SHORT = {"can": "✓", "morning": "R", "afternoon": "O", "off": "×", "D": "D", "NV": "NV",
         "L": "L", "PN": "PN", "S": "Š"}
# What a team member may enter for herself; absences are decided by the management.
SELF_CODES = ("can", "morning", "afternoon", "off")
ABSENCE_CODES = ("D", "NV", "L", "PN", "S")
# Absences counted as worked time (a daily fond each working day). NV is time off for overtime
# already worked, PN is excused but not worked - both 0 h.
CREDITED_CODES = ("D", "L", "S")


class StaffRequest(models.Model):
    """One day of one team member: availability (her own wish) or absence (management)."""

    _name = "elite.vet.staff.request"
    _description = "Dostupnost a absence"
    _order = "date, member_id"

    member_id = fields.Many2one("elite.vet.doctor", string="Člen týmu", required=True, ondelete="cascade",
                                index=True)
    date = fields.Date(string="Datum", required=True, index=True)
    code = fields.Selection(REQUEST_CODES, string="Záznam", required=True)
    note = fields.Char(string="Poznámka")
    is_absence = fields.Boolean(string="Absence", compute="_compute_is_absence", store=True)
    entered_by_member = fields.Boolean(string="Zadal(a) sám/sama", readonly=True,
                                       help="Zaklikl(a) si v Moje dostupnost.")

    _sql_constraints = [
        ("member_date_unique", "unique(member_id, date)", "Jeden člověk má na jeden den jen jeden záznam."),
    ]

    @api.depends("code")
    def _compute_is_absence(self):
        for rec in self:
            rec.is_absence = rec.code in ABSENCE_CODES

    @api.depends("member_id", "date", "code")
    def _compute_display_name(self):
        labels = dict(REQUEST_CODES)
        for rec in self:
            rec.display_name = "%s · %s · %s" % (rec.member_id.initials or rec.member_id.name or "",
                                                  rec.date and rec.date.strftime("%d. %m.") or "",
                                                  labels.get(rec.code, ""))


class StaffMonthNote(models.Model):
    """Long note at the end of a member's row in Požadavky na směny, one per month."""

    _name = "elite.vet.staff.month.note"
    _description = "Poznámka k měsíci"

    member_id = fields.Many2one("elite.vet.doctor", string="Člen týmu", required=True, ondelete="cascade")
    month = fields.Date(string="Měsíc", required=True, help="1. den měsíce.")
    note = fields.Text(string="Poznámka")

    _sql_constraints = [
        ("member_month_unique", "unique(member_id, month)", "Na měsíc je jedna poznámka."),
    ]

    @api.constrains("month")
    def _check_month(self):
        for rec in self:
            if rec.month.day != 1:
                raise ValidationError(_("Měsíc se ukládá jako jeho 1. den."))
