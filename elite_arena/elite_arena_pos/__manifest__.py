{
    "name": "Elite Arena - pokladna",
    "version": "18.0.1.0.0",
    "category": "Sales/Point of Sale",
    "summary": "Pokladna Elite Arena: zboží a skupiny z pokladny, sklad, česká účetní osnova a DPH.",
    "description": """
Elite Arena - pokladna
======================

Nastaví Odoo pokladnu pro firmu Elite Arena: skupiny a zboží převzaté z dosavadní pokladny
(s obrázky), sklad, českou účetní osnovu (l10n_cz) s cenami včetně DPH, DPH 12 % / 21 %,
platby hotově a kartou a fakturaci z pokladny. Ostatní firmy v databázi nechává být
a u existující firmy nic nepřepisuje. Popis je v README.md.
""",
    "author": "Michal Varys",
    "website": "https://www.michalvarys.eu",
    "license": "LGPL-3",
    "depends": [
        "point_of_sale",
        "stock",
        "account",
        "l10n_cz",
    ],
    "data": [
        "data/product_category_data.xml",
        "data/product_data.xml",
        "data/setup.xml",
    ],
    "installable": True,
    "application": False,
    "auto_install": False,
}
