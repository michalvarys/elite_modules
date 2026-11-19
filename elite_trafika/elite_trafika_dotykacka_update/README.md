# Elite Trafika – prodeje z Dotykačky (doplnění)

Doplní do pokladny „Elite Trafika“ prodeje z novějšího exportu Dotykačky. Navazuje na modul
`elite_trafika_dotykacka` (archiv z 3. 11. 2026) a nahrává stejně: uzavřené směny a objednávky
„Dotykačka 2026…“, které jsou ve výkazech pokladny, bez účetních zápisů a bez skladových pohybů.

## Co se nahraje

Export SL FORTIS za 1. 1. – 19. 11. 2026 (`arena-email/Dotykacka_SL_FORTIS_01-01_19-11-2026`).
Do Odoo přibude jen to, co tam ještě není:

| | Celkem v exportu | Nově v Odoo |
|---|---|---|
| Doklady | 6 604, 2 305 000 Kč | 463 (od 3. 11. 19:44 do 19. 11. 19:39), 200 489 Kč |
| Řádky dokladů | 9 285 | 688 |
| Směny | 270 | směny od 3. 11. |
| Archivované zboží | | 4 (BONG shisha, Orbit spearmint, POPRS, Rolling papers filtr smart) |

Kontrola: tržby po dnech sedí na korunu s reportem Dotykačky „Přehled tržeb“. Všech 6 141 dokladů
z archivu je v novém exportu beze změny.

- Doklady, které už v Odoo jsou (podle čísla dokladu), modul přeskočí.
- **Sklad se nemění.** Export stav skladu neobsahuje; sklad trafiky se nastaví inventurou.
- 19 dokladů z 3. 11. do 19:07 zůstává ve směně 2. 11., kam je dal archiv z 3. 11. (ten směnu 3. 11.
  ještě neměl); tržby po dnech to neovlivní.

## Instalace

Pokladna Elite Trafika nesmí mít otevřenou směnu, jinak instalace skončí chybou a nic se nenahraje.

```bash
cd elite_modules && git pull
docker compose exec odoo odoo -d odoo -i elite_trafika_dotykacka_update --stop-after-init --no-http
docker compose restart odoo
```

Modul nepřidává pole; mění jen kód importu v `elite_trafika_dotykacka` (čtení dat z jiného modulu),
ten se projeví restartem.

## Další export

Import běží při instalaci i při každé aktualizaci a nahraje jen chybějící doklady. Novější export
z Dotykačky (reporty „Vystavené doklady“, „Detailní výpis prodejů“, „Pokladní pohyby“, „Směny
a uzávěrky“ od 1. 1.; poslední směna musí být uzavřená):

```bash
cd elite_trafika/elite_trafika_dotykacka_update
python3 scripts/gen_data.py "<složka exportu>" \
  "<archiv 3. 11.>/Produkty/55 Produkty – všechny včetně smazaných.xlsx" .
```

(potřebuje `openpyxl`), commitnout a na serveru `-u elite_trafika_dotykacka_update`. Zboží založené
v Dotykačce po 3. 11. se nahraje jako archivované „dřívější zboží“; pokud ho chcete mít v pokladně,
přidejte ho nejdřív do `elite_trafika_pos`. Testy počítají s exportem do 19. 11. a je potřeba je
s novým exportem upravit.

## Testy

Na testovací databázi s nainstalovaným `elite_trafika_dotykacka` (ne na produkci):

```bash
$O -d TESTOVACI_DB -i elite_trafika_dotykacka_update --test-tags /elite_trafika_dotykacka_update
```
