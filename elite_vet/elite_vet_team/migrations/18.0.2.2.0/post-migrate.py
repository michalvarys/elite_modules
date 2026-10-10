import logging

from odoo import SUPERUSER_ID, api

from odoo.addons.elite_vet_team import PREKLADANA_POLE, PREKLADY

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """Vrati cestinu na ceskou verzi stranky.

    Pri instalaci se zaznamy zalozily cesky, jenze cesky text skoncil ve
    zdrojovem slotu en_US - do sveho slotu cs_CZ se nikdy nezapsal. Naplneni
    prekladu pak do en_US zapsalo anglictinu a cesky web zacal ukazovat
    anglicke texty.

    Tahle migrace to sroubuje zpatky: podle zalohy prekladu dohleda cesky
    original a ulozi ho do cs_CZ, do en_US necha anglictinu.
    """
    env = api.Environment(cr, SUPERUSER_ID, {})

    aktivni = set(env["res.lang"].search([("active", "=", True)]).mapped("code"))
    if "cs_CZ" not in aktivni:
        _logger.info("Cestina neni nainstalovana, neni co opravovat.")
        return

    # anglicky text -> cesky original
    z_anglictiny = {}
    for cesky, preklad in PREKLADY.items():
        anglicky = preklad.get("en_US")
        if anglicky:
            z_anglictiny.setdefault(anglicky, cesky)

    opraveno = 0
    for model, pole in PREKLADANA_POLE.items():
        zaznamy = env[model].with_context(active_test=False).search([])
        for zaznam in zaznamy:
            for nazev_pole in pole:
                preklady = zaznam.get_field_translations(nazev_pole)[0]
                soucasne = {p["lang"]: p["value"] for p in preklady}
                zdroj = soucasne.get("en_US")
                if not zdroj:
                    continue

                cesky = None
                if zdroj in PREKLADY:
                    # ve zdroji je porad cestina; anglictinu tam teprve doplnime
                    cesky = zdroj
                    anglicky = PREKLADY[zdroj].get("en_US")
                    if anglicky and "en_US" in aktivni:
                        zaznam.update_field_translations(nazev_pole, {"en_US": anglicky})
                elif zdroj in z_anglictiny:
                    cesky = z_anglictiny[zdroj]

                if cesky and soucasne.get("cs_CZ") != cesky:
                    zaznam.update_field_translations(nazev_pole, {"cs_CZ": cesky})
                    opraveno += 1

    _logger.info("Cestina doplnena u %s textu.", opraveno)
