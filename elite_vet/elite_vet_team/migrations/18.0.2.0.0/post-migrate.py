from odoo import SUPERUSER_ID, api

from odoo.addons.elite_vet_team import _priradit_k_webu


def migrate(cr, version):
    """Prirad stranku Nas tym ke konkretnimu webu.

    Instalacni hook se pri upgradu nespousti, takze u databazi, kde uz modul
    bezi, by stranka zustala spolecna pro vsechny weby.
    """
    env = api.Environment(cr, SUPERUSER_ID, {})
    _priradit_k_webu(env, "elite_vet_team.nas_tym_page")
