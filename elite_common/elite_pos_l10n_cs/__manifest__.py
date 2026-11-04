{
    "name": "Elite - čeština pokladny",
    "version": "18.0.1.0.0",
    "category": "Localization",
    "summary": "Kompletní český překlad pokladny a všech jejích modulů, společný pro Arenu, Trafiku a Vet.",
    "description": """
Elite - čeština pokladny
========================

Nese úplný český překlad modulu point_of_sale a modulů pos_*: texty pokladny (obrazovky, tlačítka),
hlášení serveru i popisky a nastavení v administraci. Překlad je v modulu celý, takže funguje i tam,
kde původní překlad Odoo chybí nebo se nenačte. Ruční úpravy překladů v Odoo nepřepisuje.
Popis je v README.md.
""",
    "author": "Michal Varys",
    "website": "https://www.michalvarys.eu",
    "license": "LGPL-3",
    "depends": ["point_of_sale"],
    "data": ["data/lang.xml"],
    "installable": True,
    "application": False,
    "auto_install": True,
}
