{
    "name": "Elite Vet - Plánování služeb",
    "version": "18.0.1.0.0",
    "category": "Website",
    "summary": "Měsíční plán služeb po úsecích, dostupnost a absence personálu, bilance hodin.",
    "description": """
Elite Vet - Plánování služeb
============================

Rozšiřuje Rozpis služeb (elite_vet_calendar) a Rezervace (elite_vet_reservation):

* **Plánování** - měsíční tabulka úseků (Recepce, Ordinace 1, Ordinace 2, Sál,
  Stáž / výpomoc) a jejich směn. Každé přiřazení je směna v Rozpisu služeb;
  služba lékařky v úseku s ordinací se sama propíše do kalendáře rezervací.
* **Požadavky na směny** - dostupnost a absence (D, NV, L, PN, Š) po dnech,
  součty dovolené a NV, poznámky.
* **Bilance hodin** - fond z pracovních dnů měsíce bez svátků, odpracováno,
  ranní / odpolední / celodenní / víkendy, absence a saldo.
* **Moje dostupnost** - lékařky a sestry si samy zaklikají dny, kdy můžou pracovat.
""",
    "author": "Michal Varys",
    "website": "https://www.michalvarys.eu",
    "license": "LGPL-3",
    "depends": ["elite_vet_reservation"],
    "data": [
        "security/ir.model.access.csv",
        "views/planning_row_views.xml",
        "views/doctor_views.xml",
        "views/staff_request_views.xml",
        "views/planner_actions.xml",
        "views/menus.xml",
        "views/rozpis_page.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "elite_vet_planning/static/src/planner/*",
            "elite_vet_planning/static/src/my_availability/*",
        ],
    },
    "post_init_hook": "_post_init",
    "installable": True,
    "application": False,
    "auto_install": False,
}
