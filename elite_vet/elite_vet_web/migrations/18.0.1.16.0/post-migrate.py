# -*- coding: utf-8 -*-
"""Uklidi domovskou stranku, kterou na "/" zalozilo tema.

theme_elite_vet mel zaznam theme.website.page na "/", takze pri kazde
aktualizaci tematu vznikla na domovske adrese dalsi stranka se starou
podobou webu. Zaznam uz v tematu neni, ale stranky, ktere podle nej
vznikly, je potreba srovnat.
"""
from odoo import api, SUPERUSER_ID


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    from odoo.addons.elite_vet_web import _uklid_starych_stranek
    _uklid_starych_stranek(env)
