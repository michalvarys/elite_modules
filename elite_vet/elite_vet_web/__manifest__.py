{
    "name": "Elite Vet - Web",
    "version": "18.0.1.20.0",
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
        "views/sekce.xml",
        "views/homepage.xml",
        "views/rezervace.xml",
        "views/cenik.xml",
        "views/o_nas.xml",
    ],
    "post_init_hook": "_pri_instalaci",
    "installable": True,
    "application": True,
    "auto_install": False,
}
