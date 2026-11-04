# Elite – čeština pokladny

Sdílený modul pro Arenu, Trafiku i Vet. Nese úplný český překlad modulu `point_of_sale` a všech modulů
`pos_*` (bez lokalizací cizích států `l10n_*`): obrazovky pokladny, hlášení serveru, popisky a nastavení
v administraci. Překlady jsou společné pro celou databázi, stačí ho nainstalovat jednou.

## Proč nestačí překlad z Odoo

- V Odoo není přeložených přes 560 textů modulů pokladny.
- Na produkci (2026-11-04) byla pokladna česky jen u textů, které mají překlad i jiné moduly („Zákazník“,
  „Akce“). Texty, které existují jen v `point_of_sale`, zůstaly anglicky, ačkoli je Odoo přeložené má.
  Proto modul nese překlad celý a funguje i bez původního souboru `point_of_sale/i18n/cs.po`.

## Jak to funguje

| Druh textu | Odkud se bere | Přepisuje |
|---|---|---|
| Texty pokladny (JS) a hlášení serveru (Python) | `i18n_pos/<modul>.po`, napojeno v `models/code_translations.py` | ano, jen češtinu, kód se v databázi neupravuje |
| Popisky, nabídky, pohledy (databáze) | `i18n_pos/<modul>.po`, nahráno v `models/ir_module.py` | ne, doplní jen chybějící; ruční úpravy v Odoo zůstanou |

Modul pokladny doinstalovaný později dostane překlad automaticky. Texty pro zákazníky jsou ve vykání,
stejně jako zbytek české verze Odoo.

## Nasazení

Na serveru je potřeba přidat `/mnt/modules/elite_common` do `addons_path` (v repu je to
v `config/odoo.conf`), jinak Odoo modul nenajde.

```bash
cd elite_modules && git pull
docker compose exec odoo odoo -d NAZEV_DATABAZE -i elite_pos_l10n_cs --stop-after-init --no-http
docker compose restart odoo
```

Modul nepřidává pole ani nemění data; po restartu stačí v pokladně obnovit stránku. Uživatel musí mít
v předvolbách jazyk čeština. Pokladna používá jazyk přihlášeného uživatele.

## Úprava překladů

- Jeden text: v `scripts/translations.json`, nebo u popisků přímo v Odoo.
- Po aktualizaci Odoo: `python3 scripts/gen_po.py <složka addons>` vypíše nové nepřeložené texty a znovu
  vytvoří `i18n_pos/`. Potřebuje knihovnu `polib` a zápis do složky modulu (v kontejneru je `/mnt/modules`
  jen pro čtení, addons je tedy potřeba zkopírovat ven).

## Testy

```bash
docker exec odoo odoo --addons-path=/mnt/modules/elite_common,/mnt/modules/elite_arena,/mnt/modules/elite_trafika,/usr/lib/python3/dist-packages/odoo/addons \
  -d TESTOVACI_DB -i elite_pos_l10n_cs --test-tags /elite_pos_l10n_cs --stop-after-init --http-port 8091
```
