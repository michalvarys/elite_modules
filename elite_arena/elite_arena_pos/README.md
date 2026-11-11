# Elite Arena – pokladna

Odoo 18 modul, který připraví pokladnu herny pro firmu **Elite Arena**. Zboží a skupiny jsou převzaté
z dosavadní pokladny (fotky obrazovky „Zboží“ z 3. 11. 2026), obrázky zboží jsou stažené z webů výrobců
a e-shopů.

## Co modul nastaví

Pro firmu Elite Arena. Firmu, název pokladny a seznam zboží s DPH 12 % určuje
[data/setup.xml](data/setup.xml), kód je v [models/setup.py](models/setup.py).

**Elite Arena jako pobočka.** Na produkci je Elite Arena pobočkou (značkou) firmy Elite. Pobočka v Odoo
nemá vlastní účetnictví, sdílí ho s mateřskou firmou. Účetní osnovu, ceny s DPH a daně proto modul
nastaví **mateřské firmě Elite**; Odoo pak osnovu `cz` zapíše i jejím pobočkám (Elite Arena, Elite
Trafika, Elite Vet). Sklad, zboží, platební metody, pokladní deník a pokladna patří pobočce Elite Arena;
bankovní a prodejní deník jsou mateřské firmy. Když Elite Arena pobočkou není, platí všechno jen pro ni.

| Oblast | Nastavení |
|---|---|
| Česká lokalizace | účetní osnova `l10n_cz` a ceny včetně DPH, jen když firma ještě nemá účetnictví; čeština |
| DPH | 12 % potraviny a jídlo (sladkosti, slanosti, Big Shock tyčinky a hroznový cukr, PANINI, PIZZA, WRAP); 21 % všechny nápoje včetně balené vody, pivo, herní čas a vouchery (GFŘ 916/24/7100-30116-050822) |
| Sklad | sklad firmy; když žádný nemá, založí sklad „Elite Arena“ (zkratka ARENA) |
| Skupiny | skupiny pokladny (BIG Shock!, GAME, NEALKO NÁPOJE, PIVO, Service fee, SLADKOSTI A SLANOSTI, JÍDLO) i podskupiny |
| Zboží | 59 položek, všechny s obrázkem; kód zboží (SKU) je interní reference |
| Obrázky | zboží i všech 14 skupin pokladny; doplní se i při aktualizaci, ale jen tam, kde obrázek chybí |
| Pokladna | „Elite Arena“: platba Hotově a Kartou, faktura z pokladny do prodejního deníku firmy |

Herní čas, passy a vouchery jsou služby (bez skladu). Nápoje, sladkosti a jídlo jsou skladové zboží;
prodej do mínusu pokladna nezablokuje, stejně jako dosud.

### Co modul nepřepíše

- **Ostatní firmy.** Instalace účetnictví by jinak hlavní firmě databáze automaticky založila účetní
  osnovu; modul to vypne. Firmy mimo Elite Arenu a její mateřskou firmu zůstanou bez účetnictví.
- **Existující nastavení Elite Arena (a mateřské firmy).** Účetní osnovu, ceny s/bez DPH a výchozí daň
  nastaví jen firmě bez účetnictví. Když firma už osnovu má, nechá ji být; když účtuje ceny bez DPH, založí si kopie
  daní 21 % a 12 % „cena s DPH“ (se stejnými řádky přiznání). Existující sklad, deníky a platební
  metody stejného jména použije beze změny. Pokladnu založí jen jednou; další aktualizace modulu
  ji nemění.
- **Zboží po instalaci.** Zboží a skupiny se nahrávají jen při instalaci (`noupdate`), opravy v Odoo
  aktualizace nepřepíše. Výjimka: sazby DPH zboží z modulu se při aktualizaci nastaví podle
  `data/setup.xml`.
- Když firma Elite Arena v databázi není (nebo je víckrát), instalace skončí chybou dřív, než modul
  cokoli nastaví.

Co při instalaci udělá samo Odoo (standard, jen přidává): modul Sklad založí sklad první firmě
v databázi, pokud v databázi žádný sklad není.

## Nasazení na produkci

**Produkční databáze má zapnutá demo data** (`base` má příznak demo). Odoo pak při instalaci nových
modulů (Účetnictví, Sklad, Pokladna, …) nahraje i jejich demo data: demo zboží, faktury, pokladnu.
Přepínač `--without-demo` to **nezastaví**, platí jen při zakládání databáze. Demo data se uloží, i když
instalace modulu potom selže. Proto se demo musí vypnout **před** instalací:

```bash
# 1. záloha
docker compose exec db pg_dump -U odoo -Fc odoo > odoo_pred_pokladnou.dump
# 2. vypnout demo data (jen příznak modulů, žádná data se nemažou)
docker compose exec db psql -U odoo -d odoo -c "UPDATE ir_module_module SET demo = false WHERE demo;"
# 3. instalace
cd elite_modules && git pull
docker compose exec odoo odoo -d odoo -i elite_arena_pos --stop-after-init --no-http
docker compose restart odoo
```

Názvy služeb (`db`, `odoo`) a databáze (`odoo`) upravte podle serveru. Na produkci nespouštějte testy.

Postup je vyzkoušený na kopii produkce (databáze s demo daty, firmy Elite, Elite Trafika, Elite Arena,
Elite Game Arena): bez kroku 2 se nahrála demo data účetnictví, skladu, produktů i pokladny, s krokem 2
žádná; ostatní firmy zůstaly bez účetní osnovy a deníků.

## Co je potřeba doplnit

Ceny označené „ggLeap“ jsou z katalogu ggLeapu, celé názvy Big Shock z bigshock.cz a waio.cz.

| SKU | Název v Odoo | Cena | Stav |
|---|---|---|---|
| 16025 | BIG SHOCK SMART Ananas & Passionfruit 500ml | **0** | doplnit cenu |
| 16030, 16032 | BIG SHOCK WAIO Cucumber & Lime / Mango & Lavender | **0** | doplnit cenu |
| 16031 | BIG SHOCK WAIO 16031 | **0** | doplnit cenu; podle waio.cz asi Currant Fusion, „HR…“ ale nesedí |
| 16039, 16040 | BIG SHOCK HROZNOVÝ CUKR Original / Orange | 33 (ggLeap) | příchuť odvozená z řazení a SKU, ověřit |
| 16036, 16038 | BIG SHOCK TYČINKA Original / Čoko | 33 (ggLeap) | příchuť odvozená z řazení a SKU, ověřit |
| 16074 | Big Shock RASPBERRIES | 45 (ggLeap) | dnes se prodává jen Berries, obrázek je Berries |
| 16079 | BigShock CHERRY | 49 (ggLeap) | obrázek je SMART Wild Cherry |
| 16052, 16055 | 1 HODINA, 10 HODIN | 75, 670 (ggLeap) | ověřit |

Obrázek 16032 (WAIO Mango) je špatně oříznutý.

## Obrázky

Herní čas, passy a vouchery nemají obal, proto mají nakreslené dlaždice v barvách značky (černá a zlatá `#f4c430` z elite-arena.cz). Skupiny mají
obrázek typického zboží ze skupiny na černém podkladu (`static/img/categories/`), GAME a Service fee dlaždici. Dlaždice
i obrázky skupin vytvoří znovu `scripts/gen_images.py`. Vlastní obrázek nahraný v Odoo modul nepřepíše.

Zdroj každého obrázku je ve `static/img/products/manifest.csv`. Fotky jídla jsou z Wikimedia Commons:
panini (16067) CC0, pizza (16059) CC BY-SA 4.0, wrap (16066) CC BY-SA 3.0. U CC BY-SA je při
zveřejnění potřeba uvést autora; v pokladně je vidí jen obsluha.

## Testy

Testy potřebují databázi s firmou „Elite Arena“ a nesmí běžet na produkci:

```bash
O="docker exec odoo odoo --addons-path=/mnt/modules/elite_vet,/mnt/modules/elite_arena,/usr/lib/python3/dist-packages/odoo/addons --http-port 8091 --stop-after-init"
$O -d arena_pos_prodlike -i base
docker exec -i odoo odoo shell -d arena_pos_prodlike --no-http <<'EOF'
cz, czk = env.ref("base.cz"), env.ref("base.CZK"); czk.active = True
env.ref("base.main_company").write({"name": "Elite", "country_id": cz.id, "currency_id": czk.id})
env["res.company"].create({"name": "Elite Arena", "country_id": cz.id, "currency_id": czk.id})
env.cr.commit()
EOF
docker exec odoo-db psql -U odoo -d arena_pos_prodlike -c "UPDATE ir_module_module SET demo = false WHERE demo;"
$O -d arena_pos_prodlike -i elite_arena_pos --test-tags /elite_arena_pos
```
