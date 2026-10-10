# -*- coding: utf-8 -*-
"""Dozene opravu osirelych systemovych parametru i tam, kde modul uz bezi."""
from odoo import api, SUPERUSER_ID


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    from odoo.addons.elite_vet_theme import parametry
    parametry.sprav(env)
