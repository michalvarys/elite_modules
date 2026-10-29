{
    "name": "Elite Arena - ggLeap data",
    "version": "18.0.1.0.0",
    "category": "Services",
    "summary": "Automatická synchronizace z ggLeapu (herna): hráči, návštěvy, prodeje, produkty, PC a rezervace; "
               "propojení hráčů s kontakty a přehled tržeb a návštěvnosti.",
    "description": """
Elite Arena - ggLeap data
=========================

Odoo samo stahuje data z ggLeap Public API (cron, ggLeap nemá webhooky) a plní z nich
analytické tabulky (hráči, návštěvy, prodeje a jejich položky, produkty, PC, rezervace).
Hráči s e-mailem se propojí s kontakty, které dostanou skupinu podle toho, jak chodí
(chodí pravidelně, přestává chodit, ztracený, přišel jen jednou...), takže jdou rovnou
použít v e-mailingu. Přehled ukazuje tržby, návštěvy, vytížení podle hodin a odchod hráčů.
Data tečou jen jedním směrem: Odoo do ggLeapu nic nezapisuje.
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
