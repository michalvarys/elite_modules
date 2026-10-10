import json
import os

from odoo import SUPERUSER_ID, api

from odoo.addons import elite_vet_web


def migrate(cr, version):
    """Rozdeli dosavadni blok na hlavicku stranky a sekci s ukony.

    Velky nadpis nema mit tabulku primo pod sebou — ta patri pod nadpis sekce.
    Nova sekce dostane vlastni nazev z data/cenik.json, aby se nadpis na strance
    neopakoval dvakrat pod sebou. U databazi, kde uz hlavicka je, se nic nedeje.
    """
    env = api.Environment(cr, SUPERUSER_ID, {})
    Sekce = env["elite.vet.price.category"].sudo()
    if Sekce.search_count([("typ", "=", "hlavicka")]):
        return

    prvni = Sekce.search([], limit=1, order="sequence, id")
    if not prvni or not prvni.item_ids:
        return                      # neni co delit

    cesta = os.path.join(os.path.dirname(os.path.abspath(elite_vet_web.__file__)),
                         "data", "cenik.json")
    nazvy = {}
    if os.path.exists(cesta):
        with open(cesta, encoding="utf-8") as soubor:
            nazvy = (json.load(soubor).get("sekce_nazev") or {})

    sekce = Sekce.with_context(lang="en_US").create({
        "typ": "sekce",
        "name": nazvy.get("en_US") or prvni.with_context(lang="en_US").name,
        "comment": prvni.with_context(lang="en_US").comment,
        "sequence": prvni.sequence + 1,
    })
    for jazyk in ("cs_CZ", "de_DE", "ru_RU"):
        if nazvy.get(jazyk):
            sekce.with_context(lang=jazyk).name = nazvy[jazyk]
        komentar = prvni.with_context(lang=jazyk).comment
        if komentar:
            sekce.with_context(lang=jazyk).comment = komentar

    prvni.item_ids.write({"category_id": sekce.id})
    prvni.write({"typ": "hlavicka", "comment": False})
