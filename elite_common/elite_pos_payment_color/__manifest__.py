{
    "name": "Elite - barvy a rozložení plateb v pokladně",
    "version": "18.0.1.0.0",
    "category": "Sales/Point of Sale",
    "summary": "Barva tlačítka platby v pokladně a volba, zda tlačítka plateb rozložit po výšce, nebo řadit za sebou.",
    "description": """
Elite - barvy a rozložení plateb v pokladně
===========================================

Ve formuláři a seznamu platebních metod pokladny přibude pole „Barva tlačítka v pokladně“. Na obrazovce
platby má pak tlačítko platební metody pozadí vybrané barvy; písmo je bílé nebo tmavé podle toho, co
je na dané barvě čitelné. Metody bez barvy vypadají jako dosud. V nastavení pokladny jde zapnout
„Rozložit tlačítka plateb“ (mezery po celé výšce panelu místo řazení za sebou). Popis je v README.md.
""",
    "author": "Michal Varys",
    "website": "https://www.michalvarys.eu",
    "license": "LGPL-3",
    "depends": ["point_of_sale"],
    "data": [
        "views/pos_payment_method_views.xml",
        "views/res_config_settings_views.xml",
    ],
    "assets": {
        "point_of_sale._assets_pos": [
            "elite_pos_payment_color/static/src/payment_color.js",
            "elite_pos_payment_color/static/src/payment_color.xml",
            "elite_pos_payment_color/static/src/payment_color.scss",
        ],
    },
    "installable": True,
    "application": False,
}
