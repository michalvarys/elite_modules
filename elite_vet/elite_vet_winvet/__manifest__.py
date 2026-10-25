{
    "name": "Elite Vet - WinVet data",
    "version": "18.0.1.3.0",
    "category": "Services",
    "summary": "Příjem dat z WinVetu (most winvet_bridge): kartotéka, tržby, úkony, léky, platby a jejich analýzy; ruční výdaje a zisk; kalendář WinVetu na tabuli.",
    "description": """
Elite Vet - WinVet data
=======================

Externí most (elite_vet/winvet_bridge) čte databázi WinVetu a posílá data přes
JSON API /winvet/api/v1/*. Modul z nich plní kartotéku (majitelé = kontakty,
pacienti = mazlíčci, očkování, návštěvy) a analytické tabulky (doklady,
položky dokladů, platby) s pohledy kontingenční tabulka / graf / export.
Rozhraní je popsané v elite_vet/winvet_bridge/CONTRACT.md.
""",
    "author": "Michal Varys",
    "website": "https://www.michalvarys.eu",
    "license": "LGPL-3",
    "depends": ["mail", "elite_vet_calendar", "elite_vet_reservation"],
    "data": [
        "security/ir.model.access.csv",
        "data/data.xml",
        "data/expense_data.xml",
        "views/config_views.xml",
        "views/status_views.xml",
        "views/schema_change_views.xml",
        "views/winvet_user_views.xml",
        "views/item_views.xml",
        "views/partner_views.xml",
        "views/pet_views.xml",
        "views/visit_views.xml",
        "views/vaccination_views.xml",
        "views/sale_views.xml",
        "views/payment_views.xml",
        "views/expense_views.xml",
        "views/dashboard_views.xml",
        "views/calendar_views.xml",
        "views/menus.xml",
        "data/filters.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "elite_vet_winvet/static/src/dashboard/*",
        ],
    },
    "installable": True,
    "application": True,
    "auto_install": False,
}
