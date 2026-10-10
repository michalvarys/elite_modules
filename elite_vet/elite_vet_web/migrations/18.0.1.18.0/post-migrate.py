# -*- coding: utf-8 -*-
"""Preklad stranek znovu, uz spravne do vsech jazyku.

Prvni pokus zapsal anglictinu jen do zdroje. Jazyky, ktere vlastni hodnotu
nemaji, na zdroj padaji zpatky, takze cely web zacal byt anglicky. Nove se
zapisuji vsechny jazyky vcetne cestiny.
"""
from odoo import api, SUPERUSER_ID


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    from odoo.addons.elite_vet_web.preklad_stranek import prelozit
    prelozit(env)
