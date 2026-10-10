from odoo import SUPERUSER_ID, api

from odoo.addons.elite_vet_web import _nastav_seo


def migrate(cr, version):
    """Doplni meta popis stranek, ktery Odoo bere ze zaznamu, ne ze sablony.

    Stranky ho dosud nemely v zadnem jazyce — `<t t-set="meta_description">`
    v sablone Odoo tise ignoruje.
    """
    env = api.Environment(cr, SUPERUSER_ID, {})
    _nastav_seo(env)
