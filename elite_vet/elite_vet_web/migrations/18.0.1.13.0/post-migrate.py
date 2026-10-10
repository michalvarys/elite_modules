# -*- coding: utf-8 -*-
"""Srovna nabidku i na databazi, kde modul uz bezi.

Dve opravy, ktere jsme delali rucne na devu: polozka mirici na kotvu
odpoctu z predstartovni stranky se prepne na domovskou stranku a pod ni
pribude Kontakt, ktery sjede ke kontaktni sekci.
"""
from odoo import api, SUPERUSER_ID


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    from odoo.addons.elite_vet_web import _srovnej_menu
    _srovnej_menu(env)
