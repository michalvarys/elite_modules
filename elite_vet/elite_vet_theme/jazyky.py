# -*- coding: utf-8 -*-
"""Jazyky webu si nastavi modul sam.

Klinika ma web ve ctyrech jazycich. Kdyz jazyk neni zapnuty a prideleny
webu, `/de` a `/ru` vraceji 404 -- vypada to jako rozbite nasazeni, pritom
jde jen o nastaveni, na ktere se pri instalaci zapomnelo.

Bezi z modulu elite_vet_theme, protoze ten se z celeho projektu instaluje
jako prvni. Zalezi na tom: ostatni moduly pri instalaci zapisuji preklady
a do jazyka, ktery jeste neni zapnuty, zapsat nejdou -- takovy preklad by
se tise ztratil.

Nic neprepisuje. Jazyk, ktery uz zapnuty je, se nechava byt, a kdyz ma web
jazyku vic nez cekame, ty navic zustavaji.
"""
import logging

_logger = logging.getLogger(__name__)

# Poradi je zamerne: cestina prvni, protoze je to vychozi jazyk kliniky.
JAZYKY = ("cs_CZ", "de_DE", "en_US", "ru_RU")
VYCHOZI = "cs_CZ"


def nastav(env):
    """Zapne jazyky kliniky a pridelí je jejímu webu."""
    from .web import zvol_web

    Jazyk = env["res.lang"].with_context(active_test=False)
    chtene = Jazyk.search([("code", "in", list(JAZYKY))])
    if not chtene:
        _logger.warning("Zadny z jazyku %s neni v databazi znamy.", ", ".join(JAZYKY))
        return

    web = zvol_web(env)

    nezapnute = chtene.filtered(lambda j: not j.active)
    chybejici_na_webu = chtene - web.language_ids if web else chtene

    if not nezapnute and not chybejici_na_webu:
        _logger.info("Jazyky uz jsou zapnute a pridelene webu, neni co delat.")
    else:
        # Oficialni pruvodce: zapne jazyk vcetne nacteni prekladu modulu
        # a rovnou ho prideli webu. Rucni prepnuti `active` by preklady
        # nenacetlo.
        pruvodce = env["base.language.install"].create({
            "lang_ids": [(6, 0, chtene.ids)],
            "website_ids": [(6, 0, web.ids)] if web else [(6, 0, [])],
        })
        pruvodce.lang_install()
        _logger.warning(
            "Jazyky webu srovnany. Zapnuto: %s. Pridano k webu '%s': %s.",
            ", ".join(nezapnute.mapped("code")) or "nic",
            web.name if web else "-",
            ", ".join(chybejici_na_webu.mapped("code")) or "nic")

    if not web:
        return

    vychozi = chtene.filtered(lambda j: j.code == VYCHOZI)
    if vychozi and web.default_lang_id != vychozi:
        web.default_lang_id = vychozi[:1].id
        _logger.warning("Vychozi jazyk webu '%s' nastaven na %s.", web.name, VYCHOZI)
