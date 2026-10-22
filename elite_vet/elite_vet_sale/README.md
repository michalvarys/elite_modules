# Prodej a sklad (elite_vet_sale)

Odoo 18 modul, fáze 2+3 náhrady WinVetu: pokladna recepce, nabídky z karty pacienta,
faktury a sklad se šaržemi a expirací
(spec: `docs/superpowers/specs/2026-10-22-phase2-sales-stock-design.md`).
Závisí na `elite_vet_clinic`, `elite_vet_winvet`, `point_of_sale`, `pos_sale`,
`sale_management`, `stock`, `product_expiry` a `l10n_cz`.

Tato první část modulu obsahuje jen společné nastavení, na kterém stojí další části
(ceník → produkty, zrcadlo skladu, nabídky, vyrovnání v pokladně, příjem zboží).

## Nastavení (`elite.vet.sale.setup.ensure_setup`)

Spustí se při instalaci (post-init hook) a lze ho bez obav spustit znovu – nic nezdvojí.
Pořadí kroků:

1. **Společnost:** země CZ a měna CZK – jen pokud společnost ještě nemá žádný zaúčtovaný
   doklad; jinak se nechá, jak je, a do logu se zapíše varování.
2. **Účtová osnova** `l10n_cz` (`account.chart.template.try_loading("cz", …)`), pokud ji
   společnost ještě nemá. Obecná osnova, kterou Odoo jinak samo nahraje po instalaci
   účetnictví, se pak už nenahraje.
3. **Ceny včetně DPH** (`company.account_price_include = "tax_included"`), dokud nejsou
   v účetnictví žádné položky (Odoo pak změnu nedovolí).
4. **Sklad:** strategie vyskladnění **FEFO** (nejbližší expirace první) na skladové lokaci
   každého skladu společnosti.
5. **Pokladna „Recepce“** (`elite_vet_sale.pos_config_reception`): platební metody
   **Hotově** (pokladní deník), **Kartou** a **Převodem** (bankovní deník, bez terminálu),
   deník faktur; typ operace výdeje z pokladny nemá zapnuté šarže
   (`use_existing_lots = use_create_lots = False`) → pokladna se na šarži neptá a Odoo ji
   při výdeji rezervuje samo podle FEFO. Faktura z pokladny je v Odoo 18 dostupná vždy,
   když má pokladna deník faktur.
6. **„Volná položka“** (`elite_vet_sale.product_free_line`, služba, v pokladně, daň 21 %) pro
   řádky účtu mimo ceník.

## Daně (`tax_for_rate(rate, company=None)`)

Jediné místo, kde se sazba DPH položky ceníku převádí na prodejní daň:

| Sazba | Daň z `l10n_cz` |
|---|---|
| 21 % | `l10n_cz_21_domestic_supplies` (21 % – tuzemské plnění) |
| 12 % | `l10n_cz_12_domestic_supplies` (12 % – tuzemské plnění) |
| 0 % | `l10n_cz_other_transaction_deduction` (0 % Osvobozeno) |

Jiná sazba (nebo chybějící daň) → vytvoří se prodejní daň „N % DPH (cena s DPH)“ a příště se
použije tatáž. Cena je vždy včetně daně (podle nastavení společnosti; kdyby ho nešlo změnit,
nová daň to má nastavené sama).

## Souběh s WinVetem

`is_winvet_master()` – systémový parametr `elite_vet_sale.winvet_master` (výchozí `1`).
Dokud je `1`, WinVet vede ceník, ceny a stav skladu a Odoo je jen zrcadlí. Po přepnutí
z WinVetu se nastaví na `0`.

## Stav skladu ze WinVetu

Most (kontrakt v3) posílá vždy plně entity `stock_lots` (vrstvy příjmu: řádek příjemky minus
výdeje na něj navázané) a `stock_totals` (stav položky z `VARIANTA_SKLAD_STAV`). Ukládají se
do `elite.vet.winvet.stock.layer` a `elite.vet.winvet.stock.total` (čtení pro správce);
řádky bez položky se přeskočí, záporné množství vrstvy (přeskladněný příjem) se uloží, jak je.

Po poslední dávce plného běhu `stock_totals` (a jen když `is_winvet_master()`) spustí
`elite.vet.winvet.sync._after_full_run` zrcadlo `stock.layer._apply_mirror()` pro každý
skladový produkt položky ceníku:

1. **Šarže:** vrstva → `stock.lot` (název = šarže, bez šarže `WV-<id vrstvy>`; expirace =
   datum expirace ve 12:00). Vrstvy se stejnou šarží se sečtou; záporná vrstva se počítá jako 0.
2. **Dorovnání:** rozdíl `stav − součet vrstev` se přidá na šarži s nejpozdější expirací
   (stav bez vrstev dostane šarži `WV-P<id položky>`); chybějící množství se ubírá od nejpozdější
   expirace dolů. Záporný stav WinVetu se ořízne na 0.
3. **Stav:** `stock.quant` na skladové lokaci skladu se nastaví inventurou
   (`inventory_quantity` + `action_apply_inventory`) přesně na tyto množství; šarže, které už
   ve vrstvách nejsou (a kvanty v podlokacích), se vynulují. Pohyby z Odoo plný běh přepíše.
4. **Nákupní cena** produktu = cena za MJ nejnovější vrstvy bez DPH.

Upozornění („Položka X: rozdíl Y proti stavu WinVetu“, když vrstvy WinVetu nesedí na jeho
stav, a oříznutí záporného stavu) jdou do chyb pushe, tedy do Stavu synchronizace.

## Role

Skupiny POS, Prodeje a Skladu se odvozují ze skupin rezervací (řada Recepce < Sestra <
Lékařka < Správce rezervací, vyšší role dědí nižší):

| | Recepce | Sestra | Lékařka | Správce |
|---|---|---|---|---|
| Pokladna | uživatel | uživatel | uživatel | správce POS |
| Prodej (nabídky) | prodejce, všechny doklady (nabídky zakládá lékařka) | jako recepce | jako recepce | správce prodeje |
| Sklad (příjem zboží, stav) | čtení přes pokladnu | uživatel skladu | uživatel skladu | správce skladu |

## Testy

```
docker compose stop odoo
bash elite_vet/nasazeni/testy-sale.sh            # první běh (instalace)
bash elite_vet/nasazeni/testy-sale.sh "" update  # další běhy
docker compose start odoo
```

`tests/common.py`: `SaleCase` (rozšiřuje `ClinicCase` z `elite_vet_clinic`) – spustí
`ensure_setup()` a nabízí `pos_config`, `tax21`, `tax12`, `tax0`.
