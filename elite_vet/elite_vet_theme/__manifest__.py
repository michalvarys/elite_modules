# -*- coding: utf-8 -*-
{
    "name": "Elite Vet - vzhled webu",
    "version": "18.0.1.3.0",
    "post_init_hook": "_pri_instalaci",
    "summary": "Spolecna hlavicka a paticka webu kliniky",
    # Hlavicka a paticka byly drive v sesti kopiich, na kazde strance jedna.
    # Zmena menu se tak musela delat sestkrat a pokazde se na neco zapomnelo.
    # Tenhle modul je drzi na jednom miste; vsechny ostatni moduly kliniky
    # na nem stoji, proto nesmi zaviset na zadnem z nich.
    #
    # Zamerne to NENI modul s prefixem theme_: takovy modul si Odoo nacita
    # vlastni cestou (website.theme_id, _theme_load) a na produkci uz jeden
    # theme_elite_vet existuje.
    "category": "Website",
    "license": "LGPL-3",
    "author": "Michal Varys",
    "depends": ["website"],
    "data": [
        "views/layout.xml",
        "views/bloky.xml",
        "views/oznameni.xml",
        "views/nadpis.xml",
        "views/text.xml",
        "views/snippets.xml",
    ],
    # Styl bloku se nacita na vsech strankach. Inline <style> uvnitr
    # domovske stranky by se na blok pretazeny jinam nevztahoval.
    "assets": {
        "web.assets_frontend": [
            "elite_vet_theme/static/src/css/bloky.css",
            "elite_vet_theme/static/src/css/banner.css",
            "elite_vet_theme/static/src/css/nadpis.css",
            "elite_vet_theme/static/src/css/text.css",
            "elite_vet_theme/static/src/css/mapa.css",
            "elite_vet_theme/static/src/css/kotvy.css",
        ],
    },
    "installable": True,
    "application": False,
}
