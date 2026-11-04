{
    "name": "Elite - pokladna na mobilu",
    "version": "18.0.1.0.0",
    "category": "Sales/Point of Sale",
    "summary": "Kategorie pokladny se dají posouvat a na mobilu nezakryjí produkty.",
    "description": """
Elite - pokladna na mobilu
==========================

Starší sestavení Odoo 18 nemá u kategorií pokladny omezenou výšku ani posuvník, takže při větším počtu
kategorií nejde dojet k produktům. Modul to opravuje jen stylem. Popis je v README.md.
""",
    "author": "Michal Varys",
    "website": "https://www.michalvarys.eu",
    "license": "LGPL-3",
    "depends": ["point_of_sale"],
    "assets": {
        "point_of_sale._assets_pos": [
            "elite_pos_mobile/static/src/category_list.scss",
        ],
    },
    "installable": True,
    "application": False,
    "auto_install": True,
}
