# -*- coding: utf-8 -*-
"""Doplneni banneru do slovniku prekladu stranek."""
from odoo import api, SUPERUSER_ID


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    from odoo.addons.elite_vet_web.preklad_stranek import prelozit
    prelozit(env)
