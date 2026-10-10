from odoo import SUPERUSER_ID, api

from odoo.addons.elite_vet_web import _nastav_seo, _priradit_stranky_k_webu


def migrate(cr, version):
    """Rozjede novou stranku /o-nas i na databazi, kde modul uz bezi.

    Instalacni hook se pri upgradu nespousti, takze by stranka zustala prazdna
    a bez odkazu v menu — a navic obecna, tedy viditelna na vsech webech.
    """
    env = api.Environment(cr, SUPERUSER_ID, {})
    _priradit_stranky_k_webu(env)
    _nastav_seo(env)
