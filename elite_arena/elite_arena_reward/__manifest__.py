{
    "name": "Elite Arena - odměny k vyzvednutí",
    "version": "18.0.1.0.0",
    "category": "Marketing",
    "summary": "Odměny (herní passy) s osobním odkazem: pass se do ggLeapu přidá až po vyzvednutí na webu.",
    "description": """
Elite Arena - odměny k vyzvednutí
================================

Odměna je herní pass z ggLeapu (např. hodina zdarma). Hráč dostane osobní odkaz
/odmena/<kód>, na webu klikne na "Vyzvednout" a teprve tehdy se mu pass přidá na účet.
Stránka je běžná stránka webu, takže na ní funguje retargeting (pixel) webu.
Odkazy vytvářejí automatické e-maily a dotazník spokojenosti.
""",
    "author": "Michal Varys",
    "website": "https://www.michalvarys.eu",
    "license": "LGPL-3",
    "depends": ["elite_arena_ggleap", "website"],
    "data": [
        "security/ir.model.access.csv",
        "data/data.xml",
        "views/reward_views.xml",
        "views/claim_templates.xml",
    ],
    "installable": True,
    "application": False,
    "auto_install": False,
}
