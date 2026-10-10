# Překlad domovské stránky po úpravě v editoru

## Proč to je potřeba

Domovská stránka je poskládaná ze stavebních bloků, aby šla přepisovat ručně.
Její obsah proto **neleží v modulu, ale ve stránce** — a jakmile ji někdo
upraví v editoru, Odoo si založí vlastní kopii pohledu a uloží do ní obsah
**ve všech jazycích stejně**, tedy česky.

Od té chvíle je německá i ruská verze česká, dokud se překlad nedoplní.
PO soubory s tím nepomůžou, ty řídí jen šablony v modulu.

## Postup

```bash
docker cp nasazeni/prelozit-stranku.json <kontejner>:/tmp/prelozit-stranku.json
docker cp nasazeni/prelozit-stranku.py   <kontejner>:/tmp/prelozit.py
docker exec -i <kontejner> odoo shell -c /etc/odoo/odoo.conf -d <databaze> --no-http <<'PY'
exec(open("/tmp/prelozit.py").read())
PY
docker restart <kontejner>
```

Skript vypíše, kolik termínů zůstalo bez překladu. Značka, adresa, telefon,
e-mail, Instagram a Facebook se nepřekládají — těch devět je v pořádku.
Cokoliv dalšího znamená, že v `prelozit-stranku.json` chybí dvojice.

## Když přibude nový text

Nový text napsaný v editoru žádný slovník nezná. Doplň ho do
`prelozit-stranku.json` jako:

```json
"česká podoba": { "en_US": "...", "de_DE": "...", "ru_RU": "..." }
```

Klíč je česky, protože zdrojem stránky je čeština. Mezery se při hledání
normalizují, takže na odsazení nezáleží.

## Kontrola

Stáhni `/`, `/de`, `/ru` a porovnej s češtinou. Pozor: **nestačí hledat
angličtinu** — na německé stránce bývá čeština, ne angličtina. Porovnávej
přímo s českou verzí a ignoruj slova, která jsou v obou jazycích stejná
(Chirurgie, Dermatologie, Kontakt).
