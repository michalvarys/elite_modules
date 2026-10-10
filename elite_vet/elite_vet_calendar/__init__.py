import logging

_logger = logging.getLogger(__name__)

from . import models


def _seed_defaults(env):
    """Zaklada vychozi typy smen a jmena lekarek pri prvni instalaci.

    Zamerne se to nedela pres XML zaznamy v data/. XML zaznam ma svoje
    ir.model.data id, takze kdyz ho klinika v Odoo smaze, upgrade modulu ho
    zalozi znovu. Takhle vzniknou zaznamy jen jednou a od te chvile patri
    klinice - co smaze, to je smazane.
    """
    _seed_shift_types(env)
    _seed_doctors(env)
    _priradit_k_webu(env, "elite_vet_calendar.rozpis_lekaru_page")
    _uklidit_cizi_polozky_menu(env, "/rozpis-lekaru")
    _zalozit_polozku_menu(env, "Rozpis služeb", "/rozpis-lekaru")


def _seed_shift_types(env):
    Type = env["elite.vet.shift.type"]
    if Type.search_count([]):
        return
    # Zdrojovy jazyk je anglictina, stejne jako u sablon — cestina, nemcina
    # a rustina se dopisuji jako preklady. Kdyby se zakladalo cesky, byla by
    # cestina zdroj a anglicky preklad by ho prepsal.
    PREKLADY = {
        "Morning shift":   ("Ranní služba",     "Vormittagsdienst", "Утренняя смена"),
        "Afternoon shift": ("Odpolední služba", "Nachmittagsdienst", "Дневная смена"),
        "Night shift":     ("Noční služba",     "Nachtdienst",      "Ночная смена"),
        "Weekend shift":   ("Víkendová služba", "Wochenenddienst",  "Смена в выходные"),
        "Closed":          ("Zavřeno",          "Geschlossen",      "Закрыто"),
    }
    zaznamy = Type.create([
        {"name": "Morning shift",   "sequence": 10, "time_from": 8.0,  "time_to": 14.0, "color": "green"},
        {"name": "Afternoon shift", "sequence": 20, "time_from": 14.0, "time_to": 20.0, "color": "orange"},
        {"name": "Night shift",     "sequence": 30, "time_from": 20.0, "time_to": 8.0,  "color": "purple"},
        {"name": "Weekend shift",   "sequence": 40, "time_from": 10.0, "time_to": 18.0, "color": "pink"},
        {"name": "Closed",          "sequence": 90, "color": "red", "is_note": True},
    ])
    # Zapisuji se jen jazyky, ktere databaze zna — jinak Odoo instalaci
    # shodi hlaskou "Invalid language code".
    jazyky = _nainstalovane_jazyky(env)
    for zaznam in zaznamy:
        cesky, nemecky, rusky = PREKLADY[zaznam.name]
        for kod, text in (("cs_CZ", cesky), ("de_DE", nemecky), ("ru_RU", rusky)):
            if kod in jazyky:
                zaznam.with_context(lang=kod).name = text


def _nainstalovane_jazyky(env):
    """Kody jazyku, ktere databaze opravdu zna.

    Zapis prekladu do jazyka, ktery nainstalovany neni, Odoo odmitne
    hlaskou "Invalid language code" a shodi celou instalaci modulu.
    """
    return set(env["res.lang"].search([("active", "=", True)]).mapped("code"))


def _seed_doctors(env):
    Doctor = env["elite.vet.doctor"]
    if Doctor.search_count([]):
        return
    Doctor.create([
        {"name": "MVDr. Dominika Pražáková"},
        {"name": "MVDr. Sandra Mrázová"},
        {"name": "MVDr. Kateřina Kadavá"},
        {"name": "MVDr. Georgiana Chihaia"},
        {"name": "Silvie Tranta, DiS."},
        {"name": "Nikola Hejdová"},
        {"name": "Bc. Michala Dvořáková Szmigielská"},
        {"name": "Lucie Svobodová"},
    ])


def _zvol_web(env):
    """Vybere web, kteremu stranky projektu patri.

    Telo se presunulo do elite_vet_theme/web.py, protoze ho potrebuje uz
    nastaveni jazyku, ktere bezi driv nez tenhle modul. Tady zustava,
    aby volajici nemuseli menit import.
    """
    from odoo.addons.elite_vet_theme.web import zvol_web
    return zvol_web(env)


def _priradit_k_webu(env, xml_id_stranky, xml_id_menu=None):
    """Priradi stranku (a volitelne polozku menu) ke konkretnimu webu.

    Bez toho je stranka spolecna pro vsechny weby v databazi a objevi se
    i na domenach, kam nepatri.
    """
    web = _zvol_web(env)
    if not web:
        return

    stranka = env.ref(xml_id_stranky, raise_if_not_found=False)
    if stranka:
        stranka.website_id = web.id

    if xml_id_menu:
        polozka = env.ref(xml_id_menu, raise_if_not_found=False)
        if polozka:
            polozka.website_id = web.id
            if web.menu_id:
                polozka.parent_id = web.menu_id.id

    _logger.info("Stranka %s prirazena k webu '%s'.", xml_id_stranky, web.name)


def _zalozit_polozku_menu(env, nazev, url):
    """Zalozi polozku v menu jednoho webu.

    Zamerne se to nedela XML zaznamem. Polozka bez prirazeneho webu je
    "obecna" a Odoo ji samo rozkopiruje do menu vsech webu v databazi -
    takze by odkaz na rozpis visel i na Arene, trafice a dalsich. Dodatecne
    nastaveni website_id uz kopie neodstrani.
    """
    web = _zvol_web(env)
    if not web or not web.menu_id:
        return

    Menu = env["website.menu"]
    if Menu.search_count([("url", "=", url), ("website_id", "=", web.id)]):
        return

    Menu.create({
        "name": nazev,
        "url": url,
        "parent_id": web.menu_id.id,
        "website_id": web.id,
        "sequence": 50,
    })
    _logger.info("Polozka menu %s zalozena na webu '%s'.", url, web.name)


def _uklidit_cizi_polozky_menu(env, url):
    """Smaze odkaz z menu webu, kam nepatri.

    Resi databaze, kde uz modul bezel a obecna polozka se stihla rozkopirovat
    do vsech webu.
    """
    web = _zvol_web(env)
    if not web:
        return
    cizi = env["website.menu"].search([("url", "=", url), ("website_id", "!=", web.id)])
    if cizi:
        _logger.info("Mazu %s polozek menu %s z cizich webu.", len(cizi), url)
        cizi.unlink()
