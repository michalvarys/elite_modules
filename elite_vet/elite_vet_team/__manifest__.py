{
    "name": "Elite Vet - Nas tym",
    "version": "18.0.2.5.0",
    "category": "Website",
    "summary": "Stranka /nas-tym se spravuje v Odoo: lide, fotky, sekce a podrobnosti.",
    "description": """
Elite Vet - Nas tym
===================

Prida aplikaci **Nas tym** a verejnou stranku **/nas-tym**.

Cely obsah stranky je v Odoo, ne v kodu. Klinika si sama pridava a odebira lidi,
nahrava fotky, prepisuje pozice a popisy a mysli pořadí. Kdo odejde, nemusi se
mazat - staci ho archivovat a karta ze stranky zmizi.

Fotka je volitelna. Kdyz chybi, vykresli se kolecko s inicialami, ktera se
spocitaji ze jmena (tituly se preskakuji).

Vsechny texty krome jmen a e-mailu jsou prelozitelne pres bezny prekladovy
rezim Odoo, takze nemecka, anglicka a ruska verze stranky se resi na miste.
""",
    "author": "Michal Varys",
    "website": "https://www.michalvarys.eu",
    "license": "LGPL-3",
    "depends": ["website", "elite_vet_theme"],
    "data": [
        "security/groups.xml",
        "security/ir.model.access.csv",
        "views/team_fact_label_views.xml",
        "views/team_section_views.xml",
        "views/team_icon_views.xml",
        "views/team_specialization_views.xml",
        "views/team_member_views.xml",
        "views/menus.xml",
        "views/specialization_icons.xml",
        "views/nas_tym_page.xml",
        "data/icons.xml",
        "data/specializations.xml",
    ],
    "post_init_hook": "_seed_team",
    "installable": True,
    "application": True,
    "auto_install": False,
}
