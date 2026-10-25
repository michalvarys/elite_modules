{
    "name": "Elite Vet - Ordinace",
    "version": "18.0.1.2.0",
    "category": "Services",
    "summary": "Karta pacienta a záznam návštěvy: vitální hodnoty, anamnéza, vyšetření, diagnóza, účet, šablony textů a balíčky výkonů.",
    "description": """
Elite Vet - Ordinace
====================

Fáze 1 náhrady WinVetu: zapisovatelná kartotéka s upozorněními na pacientech, záznam
návštěvy v Odoo (elite.vet.clinical.record) s položkami účtu, šablony textů a balíčky
výkonů (z WinVetu přes most, smlouva v2) a JSON API pro kartu pacienta (OWL).
Popis API je v README.md.
""",
    "author": "Michal Varys",
    "website": "https://www.michalvarys.eu",
    "license": "LGPL-3",
    "depends": ["mail", "elite_vet_winvet"],
    "data": [
        "security/groups.xml",
        "security/ir.model.access.csv",
        "views/actions.xml",
        "views/pet_alert_views.xml",
        "views/clinical_record_views.xml",
        "views/text_template_views.xml",
        "views/procedure_bundle_views.xml",
        "views/pet_views.xml",
        "views/partner_views.xml",
        "views/reservation_views.xml",
        "views/menus.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "elite_vet_clinic/static/src/patient_card/*",
            "elite_vet_clinic/static/src/board_patch/*",
        ],
    },
    "installable": True,
    "application": True,
    "auto_install": False,
}
