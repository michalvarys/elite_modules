"""18.0.1.2.0 (follow-up 16. 11.)

"Hidden on the website" now also hides the doctor from online booking: the flag is copied to the
service in the reservation calendar (elite.vet.doctor.assignment.hide_on_web). Shifts hidden
before this version get it on their service now.
"""
from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    env["elite.vet.shift"].search([("hide_on_web", "=", True)])._sync_assignments()
