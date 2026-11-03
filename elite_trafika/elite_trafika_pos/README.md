# Elite Trafika – pokladna

Odoo 18 modul, který připraví pokladnu trafiky pro firmu **Elite Trafika**. Zboží a skupiny jsou převzaté
z dosavadní pokladny Dotykačka: export produktů z 3. 11. 2026 (aktuální, nesmazané; archiv
`Dotykacka_SL_FORTIS_2026_archiv`, soubor `Produkty/01 Produkty – aktuální nesmazané.xlsx`).
Celý seznam zboží s cenami, sazbami DPH a EAN je v [zbozi.csv](zbozi.csv).

## Co modul nastaví

Pro firmu Elite Trafika. Firmu, název pokladny a seznam zboží s DPH 12 % určuje
[data/setup.xml](data/setup.xml), kód je v [models/setup.py](models/setup.py) (stejný postup jako
modul `elite_arena_pos`, bez závislosti na něm).

**Elite Trafika jako pobočka.** Na produkci je Elite Trafika pobočkou firmy Elite. Účetní osnovu, ceny
s DPH a daně má mateřská firma Elite a sdílí je s pobočkami; když je už nastavil modul Elite Arena, modul
je použije. Sklad, zboží, platební metody, pokladní deník a pokladna patří pobočce Elite Trafika.

| Oblast | Nastavení |
|---|---|
| Česká lokalizace | účetní osnova `l10n_cz` a ceny včetně DPH, jen když firma ještě nemá účetnictví; čeština |
| DPH | sazby z Dotykačky: všechno zboží 21 %; zboží s 12 % se doplní do `data/setup.xml` |
| Sklad | sklad firmy; když žádný nemá, založí sklad „Elite Trafika“ (zkratka TRAF) |
| Skupiny | 35 kategorií Dotykačky, v pořadí záložek na pokladně (Cigarety … PYTLÍKY) |
| Zboží | 506 položek, všechno skladové zboží; čárový kód = EAN z Dotykačky (407 položek), bez obrázků |
| Pokladna | „Elite Trafika“: platba Hotově a Kartou, faktura z pokladny do prodejního deníku |

### Co modul nepřepíše

Stejně jako `elite_arena_pos`: ostatní firmy nechá bez účetnictví, u Elite Trafika a mateřské firmy
nastaví osnovu, ceny s DPH a výchozí daň jen firmě bez účetnictví, existující sklad, deníky a platební
metody stejného jména použije beze změny a pokladnu založí jen jednou. Zboží a skupiny se nahrávají jen
při instalaci (`noupdate`); při aktualizaci modulu se znovu nastaví jen sazby DPH zboží z modulu.

## Nasazení na produkci

Stejný postup jako u `elite_arena_pos` (README v `elite_arena/elite_arena_pos`). Navíc musí být složka `/mnt/modules/elite_trafika` v `addons_path` v konfiguraci Odoo na serveru (v tomto repozitáři `config/odoo.conf`), jinak Odoo modul nenajde. Pak: záloha, **vypnout demo data** a pak instalace.

```bash
docker compose exec db pg_dump -U odoo -Fc odoo > odoo_pred_trafikou.dump
docker compose exec db psql -U odoo -d odoo -c "UPDATE ir_module_module SET demo = false WHERE demo;"
cd elite_modules && git pull
docker compose exec odoo odoo -d odoo -i elite_trafika_pos --stop-after-init --no-http
docker compose restart odoo
```

Vyzkoušeno na kopii produkce (Elite s pobočkami Elite Trafika, Elite Arena, Elite Vet; Elite Game Arena
samostatně; demo data zapnutá do kroku 2): Arena i Trafika nainstalované spolu, testy obou modulů prošly,
Elite Game Arena zůstala bez účetnictví.

## Co je potřeba zkontrolovat

- **DPH.** V Dotykačce má všech 506 položek 21 %, i čokolády, sušenky, lízátka, gumové bonbony
  a sladkosti TYSON. Modul to přebírá beze změny. Jestli mají potraviny mít 12 % (u výrobků
  s kanabinoidy rozhoduje celní zařazení), potvrdí účetní; pak stačí doplnit `reduced_vat`
  v `data/setup.xml` a aktualizovat modul.
- **Sdílené EAN.** Odoo nedovolí jeden čárový kód u dvou produktů. Kde má v Dotykačce víc produktů
  stejný EAN (hašiš MILKDRY, LaMousse a Black afgan, některé vapy, tři bongy, VUSE Watermelon Mint
  a jeho kopie), dostal ho jen první produkt; ostatní jsou v `zbozi.csv` bez EAN.
- **Stejně pojmenované produkty** (MAD-CROC 3×, TYSON Bites 4×, SYX POD 3×, popelnik 4× …) jsou
  i v Dotykačce samostatné produkty, modul je přebírá tak, jak jsou.
- Věk 18+ (21 produktů v Dotykačce) Odoo pokladna nehlídá; je jen ve sloupci „18+“ v `zbozi.csv`.

## Testy

Testy potřebují databázi s firmou „Elite Trafika“ a nesmí běžet na produkci. Postup je jako
v README `elite_arena_pos`, jen s firmou Elite Trafika a modulem:

```bash
O="docker exec odoo odoo --addons-path=/mnt/modules/elite_vet,/mnt/modules/elite_arena,/mnt/modules/elite_trafika,/usr/lib/python3/dist-packages/odoo/addons --http-port 8091 --stop-after-init"
$O -d trafika_pos_prodlike -i elite_trafika_pos --test-tags /elite_trafika_pos
```

Testy porovnávají zboží v databázi se [zbozi.csv](zbozi.csv). CSV i XML generuje
`scripts/gen_data.py` z exportu Dotykačky (`python3 scripts/gen_data.py "<archiv>/Produkty/01 Produkty –
aktuální nesmazané.xlsx" .`, potřebuje openpyxl); ručně je měňte spolu.

Prodeje a sklad z Dotykačky nahrává modul `elite_trafika_dotykacka`.
