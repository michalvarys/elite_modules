{
    "name": "Elite Vet - Recepce",
    "version": "18.0.1.18.0",
    "category": "Sales/Point of Sale",
    "summary": "Recepce v pokladně: dnešní příchody, čekárna, účty k zaplacení a stavy návštěvy.",
    "description": """
Elite Vet - Recepce
===================

Pracoviště recepce v pokladně Odoo: přijetí objednaných i neobjednaných klientů, stavy návštěvy
(Čeká / V ordinaci) a přehled dne. Popis je v README.md.
""",
    "author": "Michal Varys",
    "website": "https://www.michalvarys.eu",
    "license": "LGPL-3",
    "depends": [
        "elite_vet_sale",
        "pos_hr",
        "auth_signup",
    ],
    "data": [
        "security/ir.model.access.csv",
        "data/room_board.xml",
        "data/home_actions.xml",
        "data/menus.xml",
        "views/res_users_views.xml",
        "views/account_wizard_views.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "elite_vet_reception/static/src/patient_card_patch/*",
            "elite_vet_reception/static/src/room_board/*",
            # task 30: Spárovat… of the screen Ordinace opens the Kartotéka dialog of the till
            "elite_vet_reception/static/src/pos/reception_api.js",
            "elite_vet_reception/static/src/pos/reception.scss",
            "elite_vet_reception/static/src/pos/card_index_dialog/*",
        ],
        "point_of_sale._assets_pos": [
            # task 25: the move dialog of the boards (date, time, room, e-mail checkbox)
            "elite_vet_reservation/static/src/move_dialog/*",
            "elite_vet_reception/static/src/pos/**/*",
        ],
    },
    "post_init_hook": "post_init_hook",
    "installable": True,
    "application": False,
    "auto_install": False,
}
