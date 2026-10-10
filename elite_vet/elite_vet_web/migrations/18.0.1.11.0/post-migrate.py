# -*- coding: utf-8 -*-
"""Uklid zbytku po webu psanem rucne. Telo lezi v elite_vet_web/uklid.py,
aby stejny uklid probehl i pri cerste instalaci -- migrace bezi jen pri
upgradu, takze samotna by ostry web neopravila.
"""
from odoo import api, SUPERUSER_ID


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    from odoo.addons.elite_vet_web.uklid import (
        smaz_dvojniky_pohledu, vypni_zbytky_s_mrtvym_xpath)
    vypni_zbytky_s_mrtvym_xpath(env)
    smaz_dvojniky_pohledu(env)
