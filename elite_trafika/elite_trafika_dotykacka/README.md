# Elite Trafika – historie z Dotykačky

Odoo 18 modul, který převede trafiku z pokladny Dotykačka do Odoo pokladny „Elite Trafika“
(modul `elite_trafika_pos`):

- **Prodeje od 5. 2. 2026** (první účtenka v Dotykačce) jako objednávky pokladny, takže jsou
  ve výkazech Odoo: *Pokladna → Výkazy → Objednávky* (analýza prodejů podle dne, měsíce, produktu,
  kategorie, platby) a v seznamu objednávek a směn.
- **Počáteční stav skladu** trafiky (sklad TRAF) podle Dotykačky.

Zdroj je archiv Dotykačky SL FORTIS s.r.o. z 3. 11. 2026 (`Dotykacka_SL_FORTIS_2026_archiv`),
převedený do `data/dotykacka/*.csv` skriptem `scripts/gen_data.py`.

## Co se nahraje

| Dotykačka | Odoo | Počet |
|---|---|---|
| Směny a uzávěrky | uzavřené směny pokladny Elite Trafika (otevření, uzavření, hotovost při uzavření) | 251 (2 směny v Dotykačce nemají účtenku) |
| Vystavené doklady | objednávky „Dotykačka 2026…“ (číslo dokladu = reference objednávky, obsluha v poznámce) | 6 141 |
| Detailní výpis prodejů | řádky objednávek s cenou a DPH 21 % | 8 597 |
| Pokladní pohyby | platby Hotově / Kartou (i dvě platby jednoho dokladu a vrácení) | 6 140 |
| Stav skladu ke dni | množství na skladu TRAF, jen kladné stavy | 352 produktů, 3 019 ks |

Kontrola: tržby po měsících v Odoo sedí na korunu s reportem Dotykačky „Tržby dle času“
(celkem 2 104 511 Kč).

Prodeje produktů, které už v Dotykačce nejsou (9 smazaných) nebo se prodávaly pod dřívějším názvem
(26, např. „JOINT 1ks“, „INDOOR švédsko 1g“), jsou na archivovaných produktech v kategorii
*Elite Trafika / Dotykačka – dřívější zboží*. V pokladně se nenabízejí.

## Co se nezmění

- **Účetnictví.** Historické směny jsou rovnou uzavřené, bez uzávěrky Odoo. Proto z nich nevzniknou
  účetní zápisy (tržby jsou zaúčtované z Dotykačky v Money S3) ani faktury.
- **Sklad z prodejů.** Historické objednávky sklad neodečítají. Sklad nastaví jen počáteční stav
  podle Dotykačky; to je inventurní úprava bez účetního zápisu (Dotykačka nemá nákupní ceny).
- Modul nahrává jen při **instalaci**. Aktualizace modulu nic znovu nenahraje a import přeskočí
  doklady, které už v Odoo jsou.
- Pokladna nesmí mít otevřenou směnu, jinak instalace skončí chybou a nic se nenahraje.

První nová směna v Odoo začne s hotovostí z poslední uzávěrky Dotykačky (5 000 Kč).

## Kdy instalovat

Sklad a prodeje jsou ke **3. 11. 2026**. Dokud se prodává v Dotykačce, rozchází se to s Odoo.
Při přechodu na Odoo pokladnu:

1. Uzavřít poslední směnu v Dotykačce a udělat nový export (stejné soubory jako v archivu).
2. Přegenerovat data a commitnout je:
   ```bash
   cd elite_trafika/elite_trafika_dotykacka
   python3 scripts/gen_data.py "<cesta>/Dotykacka_SL_FORTIS_2026_archiv" .
   ```
   (potřebuje `pip install openpyxl`; stejně tak `elite_trafika_pos/scripts/gen_data.py` pro zboží,
   pokud v Dotykačce přibylo zboží).
3. Na serveru nainstalovat podle README `elite_trafika_pos` (záloha, vypnout demo data), pak:
   ```bash
   docker compose exec odoo odoo -d odoo -i elite_trafika_dotykacka --stop-after-init --no-http
   ```

## Testy

Na testovací databázi (ne na produkci), po instalaci `elite_trafika_pos`:

```bash
$O -d trafika_pos_prodlike -i elite_trafika_dotykacka --test-tags /elite_trafika_dotykacka
```

Testy kontrolují počty a součty podle Dotykačky, že historie nemá účetní zápisy ani skladové pohyby,
výkaz pokladny, počáteční sklad a že opakovaný import nic nepřidá.
