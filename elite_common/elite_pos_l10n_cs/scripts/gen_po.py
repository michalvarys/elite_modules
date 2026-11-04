"""Builds i18n_pos/<module>.po: every term of the .pot of each POS module, with the Czech translation of
Odoo where it has one and scripts/translations.json otherwise.

Run with a copy of the Odoo addons folder after an Odoo update (needs polib):
    python3 scripts/gen_po.py /path/to/addons
New untranslated terms are listed; add them to translations.json and run again.
"""
import json
import os
import sys

import polib

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "i18n_pos")


def pos_modules(addons):
    for name in sorted(os.listdir(addons)):
        manifest = os.path.join(addons, name, "__manifest__.py")
        pot = os.path.join(addons, name, "i18n", name + ".pot")
        if name.startswith("l10n_") or not (os.path.exists(manifest) and os.path.exists(pot)):
            continue  # localisations of other countries are not used here
        with open(manifest, encoding="utf-8") as f:
            text = f.read()
        if name == "point_of_sale" or "point_of_sale" in text or "'pos_" in text or '"pos_' in text:
            yield name


def main(addons):
    with open(os.path.join(HERE, "translations.json"), encoding="utf-8") as f:
        new = json.load(f)
    modules = list(pos_modules(addons))
    odoo = {}
    for name in modules:
        path = os.path.join(addons, name, "i18n", "cs.po")
        if os.path.exists(path):
            for entry in polib.pofile(path):
                if entry.msgstr:
                    odoo.setdefault(entry.msgid, entry.msgstr)
    missing = set()
    for name in modules:
        pot = polib.pofile(os.path.join(addons, name, "i18n", name + ".pot"))
        pot.metadata["Language"] = "cs_CZ"
        pot.metadata["Plural-Forms"] = "nplurals=4; plural=(n == 1 && n % 1 == 0) ? 0 : " \
                                       "(n >= 2 && n <= 4 && n % 1 == 0) ? 1: (n % 1 != 0 ) ? 2 : 3;"
        for entry in pot:
            entry.msgstr = odoo.get(entry.msgid) or new.get(entry.msgid, "")
            if not entry.msgstr:
                missing.add(entry.msgid)
        pot.save(os.path.join(OUT, name + ".po"))
    print(len(modules), "modules,", len(missing), "terms without translation")
    for msgid in sorted(missing):
        print(" ", msgid[:100])


if __name__ == "__main__":
    main(sys.argv[1])
