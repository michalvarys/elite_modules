"""18.0.1.5.0: doctors get a stored calendar color (previously computed from the id only)."""
from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    env["elite.vet.doctor"].with_context(active_test=False).search([]).fill_calendar_colors()
