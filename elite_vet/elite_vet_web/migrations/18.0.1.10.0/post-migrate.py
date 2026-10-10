# -*- coding: utf-8 -*-
"""Sprava domovske stranky na databazich s vice weby.

Na adrese "/" mohly zustat dve OBECNE stranky: Odoo vlastni a jedna
ukazujici na sablonu tohohle modulu. Obsluha "/" si pak vybrala spatnou
a misto homepage presmerovala na prvni polozku menu.
"""
from odoo import api, SUPERUSER_ID


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    from odoo.addons.elite_vet_web import _nastav_homepage
    _nastav_homepage(env)
