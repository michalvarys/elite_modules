{
    "name": "Elite Arena - automatické e-maily",
    "version": "18.0.1.0.0",
    "category": "Marketing",
    "summary": "Série e-mailů, do kterých se hráč zařadí sám podle návštěv (dlouho nebyl, nový hráč) "
               "a které mu v odstupech pošlou e-maily s odměnou k vyzvednutí.",
    "description": """
Elite Arena - automatické e-maily
=================================

Série (např. "Hráči, kteří dlouho nebyli") má podmínku a kroky. Každou hodinu se do ní
zařadí kontakty, které podmínku nově splnily, a ve dnech podle kroků dostanou e-mail.
E-mail může nést osobní odkaz na odměnu (modul Elite Arena - odměny); pass se přidá až
po vyzvednutí na webu. Série se zastaví, když hráč přijde nebo se odhlásí.
Po instalaci jsou všechny série vypnuté.
""",
    "author": "Michal Varys",
    "website": "https://www.michalvarys.eu",
    "license": "LGPL-3",
    "depends": ["elite_arena_reward", "mail"],
    "data": [
        "security/ir.model.access.csv",
        "data/data.xml",
        "views/sequence_views.xml",
        "views/unsubscribe_templates.xml",
    ],
    "installable": True,
    "application": False,
    "auto_install": False,
}
