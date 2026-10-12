"""18.0.1.3.0: booking settings and FAQ menus (from elite_vet_web) back under Configuration.

A standalone upgrade of elite_vet_web moved them back under the Reservations root.
After another standalone `-u elite_vet_web`, `-u elite_vet_reservation` restores them.
"""
from odoo import SUPERUSER_ID, api
from odoo.addons.elite_vet_reservation import move_foreign_menus


def migrate(cr, version):
    move_foreign_menus(api.Environment(cr, SUPERUSER_ID, {}))
