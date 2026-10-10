from odoo import SUPERUSER_ID, api

from odoo.addons.elite_vet_calendar import (
    _priradit_k_webu,
    _uklidit_cizi_polozky_menu,
    _zalozit_polozku_menu,
)


def migrate(cr, version):
    """Prirad stranku a odkaz v menu jen k webu Elite Vet.

    Instalacni hook se pri upgradu nespousti, takze u databazi, kde modul uz
    bezi, by stranka i odkaz zustaly na vsech webech.
    """
    env = api.Environment(cr, SUPERUSER_ID, {})
    _priradit_k_webu(env, "elite_vet_calendar.rozpis_lekaru_page")
    _uklidit_cizi_polozky_menu(env, "/rozpis-lekaru")
    _zalozit_polozku_menu(env, "Rozpis služeb", "/rozpis-lekaru")
