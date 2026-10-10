# -*- coding: utf-8 -*-
"""Prelozi obsah domovske stranky do de, en a ru.

Spoustet po kazde uprave stranky v editoru.

Obsah zony uz neridi PO soubory: stranka se edituje primo v editoru a Odoo
do ni pri ulozeni zapsalo cestinu do vsech jazykovych slotu. Preklad se proto
zapisuje rovnou do slotu.

Deleni na terminy dela xml_translate — tataz funkce, kterou pouziva Odoo.
Diky tomu se nahrazuje jen text, nikdy znacky.
"""
import json
from odoo.tools.translate import xml_translate

with open("/tmp/prelozit-stranku.json", encoding="utf-8") as soubor:
    SLOVNIK = json.load(soubor)


def norm(s):
    return " ".join(s.replace("&amp;nbsp;", " ").replace(" ", " ").split())


# klice normalizovane, at se trefi i pri jinem odsazeni
MAPA = {norm(k): v for k, v in SLOVNIK.items()}

V = env["ir.ui.view"].sudo()
zona = V.search([("key", "=", "elite_vet_web.homepage_oe_structure_homepage")], limit=1)
if not zona:
    raise SystemExit("ulozena zona nenalezena")

env.cr.execute("SELECT arch_db FROM ir_ui_view WHERE id=%s", (zona.id,))
arch = env.cr.fetchone()[0]
if isinstance(arch, str):
    arch = json.loads(arch)

cesky = arch["cs_CZ"]
nepreloceno = {}


def prelozit(jazyk):
    chybi = []

    def prevod(termin):
        zaznam = MAPA.get(norm(termin))
        if zaznam and zaznam.get(jazyk):
            return zaznam[jazyk]
        if termin.strip():
            chybi.append(termin)
        return termin

    vysledek = xml_translate(prevod, cesky)
    nepreloceno[jazyk] = chybi
    return vysledek


novy = dict(arch)
for jazyk in ("en_US", "de_DE", "ru_RU"):
    novy[jazyk] = prelozit(jazyk)
    print("%-6s prelozeno, bez prekladu zustalo %s terminu"
          % (jazyk, len(set(nepreloceno[jazyk]))))

env.cr.execute("UPDATE ir_ui_view SET arch_db = %s WHERE id = %s",
               (json.dumps(novy), zona.id))
env.cr.commit()
print()
print("zapsano do pohledu", zona.id)

print()
print("=== co zustalo neprelozene (nemcina) ===")
for t in sorted(set(nepreloceno["de_DE"]))[:15]:
    print("   ", norm(t)[:90])
