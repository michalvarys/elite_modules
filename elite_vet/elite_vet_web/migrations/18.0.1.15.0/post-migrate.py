# -*- coding: utf-8 -*-
"""Jedno spusteni, ktere srovna databazi at uz v ni modul pristal jakkoliv.

Dosud se uklid volal jen z migraci. Migrace ale bezi POUZE pri zvyseni
verze modulu, takze pri cerste instalaci (`-i`) neprobehl vubec -- a prave
na tom spadl ostry web hned po nasazeni.

Nove dela totez i instalacni hak. Tahle migrace je druha polovina: dozene
uklid tam, kde uz modul nainstalovany je, vcetne instalace, pri ktere se
starsi migrace preskocily.
"""
from odoo import api, SUPERUSER_ID


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    from odoo.addons.elite_vet_web import (
        _srovnej_menu, _uklid_starych_stranek, _uklid_zbytku_rucniho_webu)
    # poradi: nejdriv rozbite pohledy, pak stranky, nakonec nabidka
    _uklid_zbytku_rucniho_webu(env)
    _uklid_starych_stranek(env)
    _srovnej_menu(env)
