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
        "views/procedure_views.xml",
        "views/doctor_assignment_views.xml",
        "views/pet_views.xml",
        "views/reservation_views.xml",
        "views/partner_views.xml",
        "views/setting_views.xml",
        "views/board_action.xml",
        "views/menus.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "elite_vet_reservation/static/src/board/**/*",
        ],
    },
    "post_init_hook": "_pri_instalaci",
    "installable": True,
    "application": True,
    "auto_install": False,
}
