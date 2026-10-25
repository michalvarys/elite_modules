{
    "name": "Elite Vet - Rezervace",
    "version": "18.0.2.9.0",
    "category": "Website",
    "summary": "Rezervacni kalendar kliniky: ordinace, ukony, rozpis lekaru, online rezervace.",
    "description": """
Elite Vet - Rezervace
=====================

Nahrazuje rezervacni system WinVet. Ordinace, jejich ordinacni doba, sluzby
lekaru, seznam ukonu a rezervace jsou v Odoo; na webu /rezervacni-system
bezi vlastni rezervacni pruvodce misto iframu WinVet, podle nastaveni
"Rezervace na webu" (vychozi je WinVet).
""",
    "author": "Michal Varys",
    "website": "https://www.michalvarys.eu",
    "license": "LGPL-3",
    "depends": ["website", "mail", "bus", "payment", "elite_vet_theme", "elite_vet_team",
                "elite_vet_calendar", "elite_vet_web"],
    "data": [
        "security/groups.xml",
        "security/ir.model.access.csv",
        "security/rules.xml",
        "views/room_views.xml",
        "views/procedure_views.xml",
        "views/doctor_views.xml",
        "views/doctor_assignment_views.xml",
        "views/shift_views.xml",
        "views/pet_views.xml",
        "views/reservation_views.xml",
        "views/history_views.xml",
        "views/no_show_views.xml",
        "views/partner_views.xml",
        "views/setting_views.xml",
        "views/board_action.xml",
        "wizard/reservation_wizard_views.xml",
        "wizard/second_room_wizard_views.xml",
        "wizard/restore_wizard_views.xml",
        "views/menus.xml",
        "views/booking_page.xml",
        "views/rozpis_page.xml",
        "data/mail_templates.xml",
        "data/cron.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "elite_vet_reservation/static/src/board/**/*",
            "elite_vet_reservation/static/src/sound/sound.js",
        ],
        "web.assets_frontend": [
            "elite_vet_reservation/static/src/booking/booking.css",
            "elite_vet_reservation/static/src/booking/booking.js",
        ],
    },
    "post_init_hook": "_post_init",
    "installable": True,
    "application": True,
    "auto_install": False,
}
