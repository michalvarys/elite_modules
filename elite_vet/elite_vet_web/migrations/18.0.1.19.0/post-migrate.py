# -*- coding: utf-8 -*-
"""Preklad stranek potreti, uz podporovanym rozhranim.

Primy zapis arch_db bere Odoo jako zmenu zdroje a ostatni jazyky pritom
zahodi, takze kazdy dalsi zapis smazal ten predchozi. Nove se preklady
zapisuji pres update_field_translations, tedy po terminech.
"""
from odoo import api, SUPERUSER_ID


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    from odoo.addons.elite_vet_web.preklad_stranek import prelozit
    prelozit(env)
