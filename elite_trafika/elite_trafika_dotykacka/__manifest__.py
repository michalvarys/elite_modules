{
    "name": "Elite Trafika - historie z Dotykačky",
    "version": "18.0.1.0.0",
    "category": "Sales/Point of Sale",
    "summary": "Prodeje trafiky z Dotykačky (od 5. 2. 2026) jako objednávky pokladny a počáteční stav skladu.",
    "description": """
Elite Trafika - historie z Dotykačky
====================================

Nahraje prodeje pokladny Dotykačka (archiv SL FORTIS z 3. 11. 2026) jako uzavřené směny
a objednávky pokladny Elite Trafika, aby byly ve výkazech pokladny. Objednávky nevytvářejí
účetní zápisy ani skladové pohyby. Skladu trafiky nastaví počáteční stav podle Dotykačky.
Popis je v README.md.
""",
    "author": "Michal Varys",
    "website": "https://www.michalvarys.eu",
    "license": "LGPL-3",
    "depends": [
        "elite_trafika_pos",
    ],
    "data": [
        "data/product_history_data.xml",
        "data/import.xml",
    ],
    "installable": True,
    "application": False,
    "auto_install": False,
}
