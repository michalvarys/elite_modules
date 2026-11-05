from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

# Codes of the request table, in the order of the picker. Short labels are what the cell shows.
REQUEST_CODES = [
    ("can", "Can work"),
    ("morning", "Morning only"),
    ("afternoon", "Afternoon only"),
    ("off", "Cannot work / off"),
    ("D", "Vacation"),
    ("NV", "Time off in lieu"),
    ("L", "Doctor's visit"),
    ("PN", "Sick leave (PN)"),
    ("S", "Training / congress"),
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
    _description = "Availability and absences"
    _order = "date, member_id"

    member_id = fields.Many2one("elite.vet.doctor", string="Team member", required=True, ondelete="cascade",
                                index=True)
    date = fields.Date(string="Date", required=True, index=True)
    code = fields.Selection(REQUEST_CODES, string="Record", required=True)
    note = fields.Char(string="Note")
    is_absence = fields.Boolean(string="Absence", compute="_compute_is_absence", store=True)
    entered_by_member = fields.Boolean(string="Entered by themselves", readonly=True,
                                       help="Entered in My availability.")

    _sql_constraints = [
        ("member_date_unique", "unique(member_id, date)", "A person has only one record per day."),
    ]

    @api.depends("code")
    def _compute_is_absence(self):
        for rec in self:
            rec.is_absence = rec.code in ABSENCE_CODES

    @api.depends("member_id", "date", "code")
    def _compute_display_name(self):
        labels = dict(self._fields["code"]._description_selection(self.env))
        for rec in self:
            rec.display_name = "%s · %s · %s" % (rec.member_id.initials or rec.member_id.name or "",
                                                  rec.date and rec.date.strftime("%d. %m.") or "",
                                                  labels.get(rec.code, ""))


class StaffMonthNote(models.Model):
    """Long note at the end of a member's row in Požadavky na směny, one per month."""

    _name = "elite.vet.staff.month.note"
    _description = "Month note"

    member_id = fields.Many2one("elite.vet.doctor", string="Team member", required=True, ondelete="cascade")
    month = fields.Date(string="Month", required=True, help="First day of the month.")
    note = fields.Text(string="Note")

    _sql_constraints = [
        ("member_month_unique", "unique(member_id, month)", "There is one note per month."),
    ]

    @api.constrains("month")
    def _check_month(self):
        for rec in self:
            if rec.month.day != 1:
                raise ValidationError(_("A month is stored as its first day."))
