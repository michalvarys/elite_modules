from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class RosterMonth(models.Model):
    """Is the month's plan published on /rozpis-lekaru? (request 16. 11., Lucie: the roster
    reached the website while it was still being made.) No record = not published."""

    _name = "elite.vet.roster.month"
    _description = "Published roster month"
    _order = "month desc"
    _rec_name = "month"

    month = fields.Date(string="Month", required=True, help="First day of the month.")
    published = fields.Boolean(string="Published on the website")
    published_on = fields.Datetime(string="Published on", readonly=True)
    published_by = fields.Many2one("res.users", string="Published by", readonly=True)

    _sql_constraints = [
        ("month_unique", "unique(month)", "There is one record per month."),
    ]

    @api.constrains("month")
    def _check_month(self):
        for rec in self:
            if rec.month.day != 1:
                raise ValidationError(_("A month is stored as its first day."))

    @api.model
    def is_published(self, month):
        return bool(self.sudo().search_count([("month", "=", month), ("published", "=", True)]))

    @api.model
    def _set_published(self, month, published):
        """Called by the planner after its manager check (sudo here)."""
        rec = self.sudo().search([("month", "=", month)])
        vals = {"published": published}
        if published:
            vals.update(published_on=fields.Datetime.now(), published_by=self.env.uid)
        if rec:
            rec.write(vals)
        else:
            self.sudo().create(dict(vals, month=month))
