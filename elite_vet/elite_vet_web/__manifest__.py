{
    "name": "Elite Vet - Web",
    "version": "18.0.1.22.0",
    "category": "Website",
    "summary": "Domovska stranka a stranka rezervace kliniky Elite Vet.",
    "description": """
Elite Vet - Web
===============

Verejne stranky kliniky, ktere driv zily jako archy vkladane rucne v editoru
webu:

* **/** domovska stranka (letak, galerie kliniky, sluzby, kontakt)
* **/rezervacni-system** rezervace terminu pres WinVet

Zdrojovy jazyk sablon je **anglictina**, cestina / nemcina / rustina jsou
preklady v ``i18n/*.po``. Uprava textu v sablone tedy meni jen zdroj a preklady
ostatnich jazyku zustavaji — presne kvuli tomu, aby uz nikdy nezmizely.

Obrazky jsou staticke soubory modulu (``static/src/img``), ne prilohy v
databazi. Stranka tim prestala viset na ID priloh, ktere se na kazde instalaci
lisi. Vymena fotky = vymena souboru v modulu.
""",
    "author": "Michal Varys",
    "website": "https://www.michalvarys.eu",
    "license": "LGPL-3",
    "depends": ["website", "elite_vet_calendar"],
    "data": [
        "security/ir.model.access.csv",
        "views/service_views.xml",
        "views/service_icon.xml",
        "views/obsah_views.xml",
        "views/galerie.xml",
        "views/sekce.xml",
        "views/homepage.xml",
        "views/rezervace.xml",
        "views/cenik.xml",
        "views/o_nas.xml",
    ],
    # Styly jedne stranky. Kazda sablona si svuj bundle nacte do <head>,
    # takze se na jine strance neuplatni; spolecne styly jsou v elite_vet_theme.
    "assets": {
        # Blok Galerie jde pretahnout na kteroukoliv stranku, proto globalne.
        "web.assets_frontend": [
            "elite_vet_web/static/src/css/galerie.css",
            "elite_vet_web/static/src/js/galerie.js",
        ],
        "elite_vet_web.stranka_homepage": ["elite_vet_web/static/src/css/homepage.css"],
        "elite_vet_web.stranka_rezervace": ["elite_vet_web/static/src/css/rezervace.css"],
        "elite_vet_web.stranka_cenik": ["elite_vet_web/static/src/css/cenik.css"],
        "elite_vet_web.stranka_o_nas": ["elite_vet_web/static/src/css/o_nas.css"],
    },
    "post_init_hook": "_pri_instalaci",
    "installable": True,
    "application": True,
    "auto_install": False,
}
