{
    "name": "IMI Restaurant - pokladna",
    "version": "18.0.1.0.0",
    "category": "Sales/Point of Sale",
    "summary": "Pokladna IMI Restaurant v režimu restaurace: lístek (IMI-menu-web.pdf, 16. 11. 2026), sklad, česká účetní osnova a DPH.",
    "description": """
IMI Restaurant - pokladna
=====================

Pokladna restaurace IMI Restaurant se sálem a stoly, zboží a skupiny podle jídelního lístku (zbozi.csv,
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
