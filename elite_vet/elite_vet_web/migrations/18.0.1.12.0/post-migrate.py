# -*- coding: utf-8 -*-
"""Doplni sekce ceniku, ktere v uz bezici databazi chybi.

Cenik se zaklada jen pri prvni instalaci, aby upgrade nikdy neprepsal to,
co si klinika mezitim zmenila. Sekce "Vikendove a pohotovostni priplatky"
ale pribyla do modulu az potom, takze na devu ani na ostrem webu nikdy
nevznikla -- a na strance chybela.

Doplni se jen sekce, jejichz nazev v databazi neni v zadnem jazyce.
Co uz tam je, zustava presne tak, jak to je.
"""
from odoo import api, SUPERUSER_ID


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    from odoo.addons.elite_vet_web import _doplnit_chybejici_sekce_ceniku
    _doplnit_chybejici_sekce_ceniku(env)
