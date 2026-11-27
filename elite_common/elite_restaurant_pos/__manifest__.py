{
    "name": "Elite - restaurační pokladna (základ)",
    "version": "18.0.1.0.0",
    "category": "Sales/Point of Sale",
    "summary": "Společný základ restauračních pokladen: firma, sklad, česká účetní osnova, DPH, pokladna se sálem a stoly.",
    "description": """
Elite - restaurační pokladna (základ)
=====================================

Kód, který z lístku restaurace (zbozi.csv a skupiny.csv v modulu restaurace) připraví firmu nebo pobočku,
její sklad, českou účetní osnovu, sazby DPH pro stravovací služby a pokladnu v režimu restaurace se
sálem a stoly. Restaurace samotné jsou datové moduly (elite_imi_pos, elite_jack_pos). Popis je v README.md.
""",
    "author": "Michal Varys",
    "website": "https://www.michalvarys.eu",
    "license": "LGPL-3",
    "depends": [
        "point_of_sale",
        "pos_restaurant",
        "stock",
        "account",
        "l10n_cz",
    ],
    "data": [
        "data/data.xml",
    ],
    "installable": True,
    "application": False,
    "auto_install": False,
}
