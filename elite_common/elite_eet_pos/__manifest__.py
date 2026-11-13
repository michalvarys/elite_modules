{
    "name": "Elite - EET 2.0 pro pokladnu",
    "version": "18.0.1.0.0",
    "category": "Sales/Point of Sale",
    "summary": "Tržby z pokladny Odoo do EET 2.0 při zaplacení, nastavení EET pro každou pokladnu.",
    "description": """
Elite - EET 2.0 pro pokladnu
============================

Napojení modulu elite_eet na pokladnu Odoo: každá pokladna má vlastní nastavení EET, zaplacená
objednávka z obrazovky pokladny se při zaplacení odešle do EET a dostane POK. U způsobu platby jde
vypnout evidenci (interní záznamy), u produktu označit předplacený kredit nebo voucher. Popis je
v README.md.
""",
    "author": "Michal Varys",
    "website": "https://www.michalvarys.eu",
    "license": "LGPL-3",
    "depends": ["elite_eet", "point_of_sale"],
    "data": [
        "security/elite_eet_pos_security.xml",
        "views/eet_views.xml",
        "views/pos_views.xml",
        "views/res_config_settings_views.xml",
        "views/menus.xml",
    ],
    "installable": True,
    "application": False,
}
