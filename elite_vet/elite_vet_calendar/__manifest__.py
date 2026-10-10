{
    "name": "Elite Vet - Rozpis sluzeb",
    "version": "18.0.5.2.0",
    "category": "Website",
    "summary": "Rozpis sluzeb lekaru: jednoducha aplikace v Odoo a mesicni kalendar na webu.",
    "description": """
Elite Vet - Rozpis sluzeb
=========================

Prida vlastni aplikaci **Rozpis sluzeb** a verejnou stranku **/rozpis-lekaru**.

Zadavani je zamerne co nejjednodussi. Jeden radek rozpisu ma tri udaje:

* **Datum**
* **Lekarka** (vyber ze seznamu lekarek kliniky)
* **Smena** (Ranni / Odpoledni / Nocni / Vikendova / Zavreno)

Casy se u smeny nezadavaji, jsou dane jejim typem. Typy smen maji vlastni
seznam, kde jde zmenit cas i barvu, a zmena se hned projevi na webu.

Na webu se z toho vykresli mesicni kalendar na aktualni a nasledujici mesic.
Cisla dnu, prazdne bunky i nazvy mesicu se pocitaji samy.

Navigace stranky se bere z menu webu, takze odkazy jdou menit v Odoo
(Web -> Upravit -> Menu) a nemusi se sahat do kodu.
""",
    "author": "Michal Varys",
    "website": "https://www.michalvarys.eu",
    "license": "LGPL-3",
    "depends": ["website", "elite_vet_team"],
    "data": [
        "security/groups.xml",
        "security/ir.model.access.csv",
        "views/vet_shift_type_views.xml",
        "views/vet_doctor_views.xml",
        "views/vet_shift_views.xml",
        "views/menus.xml",
        "views/rozpis_lekaru_page.xml",
    ],
    "post_init_hook": "_seed_defaults",
    "installable": True,
    "application": True,
    "auto_install": False,
}
