# -*- coding: utf-8 -*-
"""Schova rucne delane stranky na adresach, ktere prebiraji moduly.

Dve zverejnene stranky na jedne adrese jsou to, na cem padal dev:
`/rozpis-lekaru` vracelo 500 a editor hlasil "Expected singleton".
Stara stranka se odpublikuje, ne smaze -- vratit se da zaskrtnutim.
Domovske stranky se to netyka, tu resi _nastav_homepage.
"""
from odoo import api, SUPERUSER_ID


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    from odoo.addons.elite_vet_web import _uklid_starych_stranek
    _uklid_starych_stranek(env)
