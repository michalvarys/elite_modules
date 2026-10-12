"""18.0.1.3.0: Nastavení rezervace a Časté dotazy (menu z elite_vet_web) znovu pod Konfigurace.

Samostatný upgrade elite_vet_web je vracel pod kořen Rezervace. Po dalším
samostatném `-u elite_vet_web` je obnoví `-u elite_vet_reservation`.
"""
from odoo import SUPERUSER_ID, api
from odoo.addons.elite_vet_reservation import move_foreign_menus


def migrate(cr, version):
    move_foreign_menus(api.Environment(cr, SUPERUSER_ID, {}))
