{
    "name": "Elite Trafika - prodeje z Dotykačky (doplnění)",
    "version": "18.0.1.0.0",
    "category": "Sales/Point of Sale",
    "summary": "Doplní do pokladny Elite Trafika prodeje z novějšího exportu Dotykačky (teď do 19. 11. 2026).",
    "description": """
Elite Trafika - prodeje z Dotykačky (doplnění)
==============================================

Nahraje doklady z exportu Dotykačky SL FORTIS, které v Odoo ještě nejsou, stejně jako modul
elite_trafika_dotykacka: uzavřené směny a objednávky pokladny Elite Trafika bez účetních zápisů
a bez skladových pohybů. Doklady, které už v Odoo jsou, nechá být. Popis je v README.md.
""",
    "author": "Michal Varys",
    "website": "https://www.michalvarys.eu",
    "license": "LGPL-3",
    "depends": [
        "elite_trafika_dotykacka",
    ],
    "data": [
        "data/product_history_data.xml",
        "data/import.xml",
    ],
    "installable": True,
    "application": False,
    "auto_install": False,
}
