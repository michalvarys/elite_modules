"""18.0.1.5.0: lékařky dostanou uloženou barvu v kalendáři (dřív se počítala jen z id)."""
from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    env["elite.vet.doctor"].with_context(active_test=False).search([]).vyplnit_barvy()
