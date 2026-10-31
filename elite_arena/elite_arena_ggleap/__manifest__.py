{
    "name": "Elite Arena - ggLeap data",
    "version": "18.0.1.2.0",
    "category": "Services",
    "summary": "Automatická synchronizace z ggLeapu (herna): hráči, návštěvy, prodeje, produkty, PC, rezervace "
               "a herní passy; propojení hráčů s kontakty, přidávání passů a přehled tržeb a návštěvnosti.",
    "description": """
Elite Arena - ggLeap data
=========================

Odoo samo stahuje data z ggLeap Public API (cron, ggLeap nemá webhooky) a plní z nich
analytické tabulky (hráči, návštěvy, prodeje a jejich položky, produkty, PC, rezervace).
Hráči s e-mailem se propojí s kontakty, které dostanou skupinu podle toho, jak chodí
(chodí pravidelně, přestává chodit, ztracený, přišel jen jednou...), takže jdou rovnou
použít v e-mailingu. Přehled ukazuje tržby, návštěvy, vytížení podle hodin a odchod hráčů.
U kontaktu je vidět, jaké hry hráč hraje (filtr pro e-mailing), a přehled ukazuje, co se hraje nejvíc.
U kontaktu jsou vidět herní passy hráče a jde mu přidat nový (např. hodinu zdarma).
Synchronizace jen čte; do ggLeapu Odoo zapíše jedině pass, který někdo přidá.
""",
    "author": "Michal Varys",
    "website": "https://www.michalvarys.eu",
    "license": "LGPL-3",
    "depends": ["mail", "contacts"],
    "external_dependencies": {"python": ["requests"]},
    "data": [
        "security/security.xml",
        "security/ir.model.access.csv",
        "data/data.xml",
        "data/cron.xml",
        "views/config_views.xml",
        "views/status_views.xml",
        "views/player_views.xml",
        "views/visit_views.xml",
        "views/transaction_views.xml",
        "views/product_views.xml",
        "views/machine_views.xml",
        "views/booking_views.xml",
        "views/gamepass_views.xml",
        "views/game_views.xml",
        "views/partner_views.xml",
        "views/dashboard_views.xml",
        "views/menus.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "elite_arena_ggleap/static/src/dashboard/*",
        ],
    },
    "installable": True,
    "application": True,
    "auto_install": False,
}
