# -*- coding: utf-8 -*-
"""Doplni preklady do stranek, ktere se upravovaly v editoru.

Editor ulozi cesky text do vsech jazyku najednou, takze na /de a /ru
zustane cestina i tam, kde modul preklad ma. Podrobnosti a proc to
nespravi PO soubory: elite_vet_web/preklad_stranek.py.
"""
from odoo import api, SUPERUSER_ID


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    from odoo.addons.elite_vet_web.preklad_stranek import prelozit
    prelozit(env)
