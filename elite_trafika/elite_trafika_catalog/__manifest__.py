{
    "name": "Elite Trafika - katalog",
    "version": "18.0.1.0.0",
    "category": "Website",
    "summary": "Veřejný katalog T9HC s bránou 18+: lidé označí, co se jim líbí, a trafika vidí zájem podle zdroje.",
    "description": """
Elite Trafika - katalog
=======================

Stránka /katalog ukazuje výrobky za bránou 18+. Návštěvník klepnutím na srdíčko označí, co se mu líbí;
Odoo ukládá jen výrobek, zdroj návštěvy a čas, žádné osobní údaje. Podle počtů se trafika rozhoduje,
co naskladní. Rezervace ani prodej na webu nejsou. Popis je v README.md.
""",
    "author": "Michal Varys",
    "website": "https://www.michalvarys.eu",
    "license": "LGPL-3",
    "depends": ["website"],
    "data": [
        "security/ir.model.access.csv",
        "data/config.xml",
        "data/catalog_data.xml",
        "views/item_views.xml",
        "views/catalog_templates.xml",
    ],
    "assets": {
        "web.assets_frontend": [
            "elite_trafika_catalog/static/src/catalog.scss",
            "elite_trafika_catalog/static/src/catalog.js",
        ],
    },
    "installable": True,
    "application": False,
    "auto_install": False,
}
