{
    "name": "Elite Vet - Rezervace",
    "version": "18.0.1.0.0",
    "category": "Website",
    "summary": "Rezervacni kalendar kliniky: ordinace, ukony, rozpis lekaru, online rezervace.",
    "description": """
Elite Vet - Rezervace
=====================

Nahrazuje rezervacni system WinVet. Ordinace, jejich ordinacni doba, sluzby
lekaru, seznam ukonu a rezervace jsou v Odoo; na webu /rezervacni-system
bezi vlastni rezervacni pruvodce misto iframu.
""",
    "author": "Michal Varys",
    "website": "https://www.michalvarys.eu",
    "license": "LGPL-3",
    "depends": ["website", "mail", "payment", "elite_vet_theme", "elite_vet_team",
                "elite_vet_calendar", "elite_vet_web"],
    "data": [
        "security/groups.xml",
        "security/ir.model.access.csv",
        "views/room_views.xml",
        "views/menus.xml",
    ],
    "assets": {},
    "post_init_hook": "_pri_instalaci",
    "installable": True,
    "application": True,
    "auto_install": False,
}
