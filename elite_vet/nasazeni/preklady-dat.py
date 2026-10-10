# Doplni preklady OBSAHU, ktery zadava klinika v Odoo: texty u clenu tymu,
# nazvy sekci, popisky udaju, typy smen a specializace.
#
# Proc to neni v i18n modulu: tohle nejsou texty sablony, ale zaznamy v databazi.
# Modul je pri instalaci zaklada prazdne nebo cesky a klinika si je pak upravuje,
# takze do PO souboru nepatri a upgrade modulu je nepreklada.
#
# Jak se to pousti (v kontejneru s Odoo):
#
#   docker exec -i <kontejner> odoo shell -c /etc/odoo/odoo.conf -d <databaze> \
#       --no-http < nasazeni/preklady-dat.py
#
# Skript je bezpecny pustit opakovane: paruje podle aktualni hodnoty, takze co uz
# je prelozene, necha byt. Nic nemaze a nic nezaklada.
#
# POZOR na zdrojovy slot: en_US neni "jeden z jazyku", ale ZDROJ, podle ktereho
# se paruji vsechny ostatni. Proto se zapisuje jako prvni a cestina hned po nem
# jako samostatny preklad — jinak by cestina zdedila anglictinu.

import json
import os

def _nacti_preklady():
    """Najde preklady vedle skriptu, nebo v pracovnim adresari.

    Pri spousteni pres `odoo shell < skript.py` skript svoji cestu nezna
    (__file__ vubec neexistuje), proto ta druha varianta.
    """
    mista = []
    try:
        mista.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'preklady-dat.json'))
    except NameError:
        pass
    mista += ['preklady-dat.json', 'nasazeni/preklady-dat.json',
              '/mnt/modules/elite.vet/nasazeni/preklady-dat.json']
    for cesta in mista:
        if os.path.exists(cesta):
            with open(cesta, encoding='utf-8') as f:
                return json.load(f)
    raise SystemExit('preklady-dat.json nenalezen, hledal jsem v: %s' % ', '.join(mista))


PREKLADY = _nacti_preklady()

podle_modelu = {}
for radek in PREKLADY:
    podle_modelu.setdefault(radek['model'], []).append(radek)

celkem, preskoceno, chybejici_model = 0, 0, []

for model, radky in sorted(podle_modelu.items()):
    if model not in env:
        chybejici_model.append(model)
        continue
    Model = env[model]
    # klic = (pole, soucasna hodnota ve zdrojovem slotu)
    hledane = {(r['pole'], r['cs']): r for r in radky}
    for zaznam in Model.search([]):
        for (pole, cesky), radek in list(hledane.items()):
            soucasna = (zaznam.with_context(lang='en_US')[pole] or '').strip()
            if soucasna != cesky:
                continue
            zaznam.with_context(lang='en_US')[pole] = radek['en']
            zaznam.with_context(lang='cs_CZ')[pole] = radek['cs']
            if radek.get('de'):
                zaznam.with_context(lang='de_DE')[pole] = radek['de']
            if radek.get('ru'):
                zaznam.with_context(lang='ru_RU')[pole] = radek['ru']
            celkem += 1

preskoceno = len(PREKLADY) - celkem
env.cr.commit()

print('prelozeno hodnot: %s' % celkem)
if preskoceno:
    print('nezmeneno (uz prelozene nebo text v Odoo upraveny): %s' % preskoceno)
if chybejici_model:
    print('modely, ktere v teto databazi nejsou: %s' % ', '.join(chybejici_model))
