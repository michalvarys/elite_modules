{
    "name": "Jack Grill Bar - pokladna",
    "version": "18.0.1.0.0",
    "category": "Sales/Point of Sale",
    "summary": "Pokladna Jack Grill Bar v režimu restaurace: lístek (jack-jidelni-listek, 5. 7. 2026), sklad, česká účetní osnova a DPH.",
    "description": """
Jack Grill Bar - pokladna
=====================

Pokladna restaurace Jack Grill Bar se sálem a stoly, zboží a skupiny podle jídelního lístku (zbozi.csv,
skupiny.csv), vlastní sklad, česká účetní osnova a DPH stravovacích služeb. Nastavení dělá společný
modul elite_restaurant_pos. Popis je v README.md.
""",
    "author": "Michal Varys",
    "website": "https://www.michalvarys.eu",
    "license": "LGPL-3",
    "depends": [
        "elite_restaurant_pos",
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
