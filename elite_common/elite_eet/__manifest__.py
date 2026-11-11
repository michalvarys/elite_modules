{
    "name": "Elite - EET 2.0",
    "version": "18.0.1.0.0",
    "category": "Accounting/Localizations",
    "summary": "Evidence tržeb EET 2.0: nastavení pokladen, podpis a odeslání zpráv, fronta a upozornění.",
    "description": """
Elite - EET 2.0
===============

Jádro evidence tržeb EET 2.0 (zákon č. 180/2026 Sb.): nastavení EET pro každou pokladnu, certifikát,
sestavení a podpis datové zprávy, odeslání, záznam tržeb a pokusů, fronta s opakováním, hromadné
odeslání, ověření spojení a hlídání platnosti certifikátu. Napojení na pokladnu Odoo je v modulu
elite_eet_pos. Popis je v README.md.
""",
    "author": "Michal Varys",
    "website": "https://www.michalvarys.eu",
    "license": "LGPL-3",
    "depends": ["base", "mail"],
    "data": [
        "security/elite_eet_security.xml",
        "security/ir.model.access.csv",
        "data/cron.xml",
    ],
    "installable": True,
    "application": False,
}
