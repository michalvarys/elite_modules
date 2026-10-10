# -*- coding: utf-8 -*-
"""Dozene nastaveni jazyku i tam, kde uz modul bezi."""
from odoo import api, SUPERUSER_ID


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    from odoo.addons.elite_vet_theme import jazyky
    jazyky.nastav(env)
