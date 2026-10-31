{
    "name": "Elite Arena - dotazník spokojenosti",
    "version": "18.0.1.0.0",
    "category": "Marketing",
    "summary": "Pár dní po první návštěvě přijde e-mail s dotazníkem spokojenosti; kdo ho vyplní, "
               "dostane na konci odkaz na odměnu.",
    "description": """
Elite Arena - dotazník spokojenosti
===================================

Přidá do automatických e-mailů krok "E-mail s dotazníkem": hráč dostane osobní odkaz
na dotazník (Odoo Dotazníky). U dotazníku jde nastavit odměnu; kdo ho dokončí, uvidí
na konci tlačítko "Pro vyzvednutí odměny klikni zde" a odměnu si vyzvedne na webu.
Obsahuje dotazník "Jak se ti u nás líbilo?" a vypnutou sérii "Dotazník spokojenosti".
""",
    "author": "Michal Varys",
    "website": "https://www.michalvarys.eu",
    "license": "LGPL-3",
    "depends": ["elite_arena_mail_sequence", "survey"],
    "data": [
        "data/survey.xml",
        "data/data.xml",
        "views/views.xml",
        "views/survey_templates.xml",
    ],
    "installable": True,
    "application": False,
    "auto_install": False,
}
