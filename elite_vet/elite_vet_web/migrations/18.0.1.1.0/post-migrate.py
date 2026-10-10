from odoo import SUPERUSER_ID, api

from odoo.addons.elite_vet_web import _nastav_homepage, _priradit_stranky_k_webu


def migrate(cr, version):
    """Prisije stranky /cenik a /rezervacni-system k webu Elite Vet.

    Instalacni hook se pri upgradu nespousti, takze u databazi, kde modul uz
    bezi, by stranky zustaly obecne — a tim viditelne na vsech webech
    v databazi (Arena, trafika, Jack, IMI).
    """
    env = api.Environment(cr, SUPERUSER_ID, {})
    _priradit_stranky_k_webu(env)
    _nastav_homepage(env)
