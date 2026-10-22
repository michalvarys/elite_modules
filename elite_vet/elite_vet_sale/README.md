# Prodej a sklad (elite_vet_sale)

Odoo 18 modul, fáze 2+3 náhrady WinVetu: pokladna recepce, nabídky z karty pacienta,
faktury a sklad se šaržemi a expirací
(spec: `docs/superpowers/specs/2026-10-22-phase2-sales-stock-design.md`).
Závisí na `elite_vet_clinic`, `elite_vet_winvet`, `point_of_sale`, `pos_sale`,
`sale_management`, `stock`, `product_expiry` a `l10n_cz`.

Modul obsahuje společné nastavení prodeje a skladu, ceník → produkty, zrcadlo skladu ze WinVetu,
nabídky z karty pacienta, vyrovnání v pokladně, příjem zboží čtečkou a přehled skladu pro sestry.
Návod pro recepci a sestry: [doc/pokladna-a-sklad.md](doc/pokladna-a-sklad.md).

## Modely a API (přehled)

| Model | Co dělá |
|---|---|
| `elite.vet.sale.setup` (abstraktní) | `ensure_setup()`, `tax_for_rate(rate)`, `pos_config()`, `free_product()`, `is_winvet_master()` |
| `elite.vet.winvet.item` (rozšíření) | `product_id`; `_sync_products()` – položka ceníku → produkt |
| `elite.vet.winvet.stock.layer`, `elite.vet.winvet.stock.total` | vrstvy a stavy skladu z mostu; `stock.layer._apply_mirror()` |
| `elite.vet.winvet.status` (rozšíření) | `stock_mirror_warnings`, `stock_mirror_date` (záložka Zrcadlo skladu) |
| `elite.vet.clinical.record` (rozšíření) | `sale_order_id`, `payment_state`; „Hotovo“ → nabídka |
| `sale.order` (rozšíření) | `clinical_record_id`, `pet_id`, `doctor_id`, `reservation_id` |
| `pos.order` (rozšíření) | po zaplacení přepočítá stav platby záznamu a pošle změnu na tabuli |
| `elite.vet.reservation` (rozšíření) | `board_data()` vrací navíc `payment_state` pro štítek na tabuli |
| `elite.vet.goods.receipt` (abstraktní) | API obrazovky Příjem zboží: `init_data`, `scan`, `assign_code`, `search_products`, `suppliers`, `create_supplier`, `validate` |
| `elite.vet.product.code` | další kódy produktů pro čtečku (GTIN, interní kódy) |
| `elite.vet.expense` (rozšíření) | `picking_id` – příjemka, ze které výdaj vznikl |
| `product.product` (rozšíření) | `stock_below_minimum` (hledatelné) – filtr „Dochází“ |

## Nastavení (`elite.vet.sale.setup.ensure_setup`)

Spustí se při instalaci (post-init hook), při aktualizaci modulu na verzi 18.0.1.0.1
(migrace `migrations/18.0.1.0.1/post-migrate.py`) a lze ho bez obav spustit znovu – nic nezdvojí.
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

Zboží (druh „product“), pro které WinVet vede nenulový stav, dostane skladový produkt se
šaržemi a expirací, i když ve WinVetu nemá zapnutou skladovou evidenci (`_has_winvet_stock`);
zrcadlo takový produkt před nastavením stavu vytvoří/převede. Neaktivní položky se stavem
se nepřenášejí (jedno souhrnné upozornění s jejich počtem).

Upozornění („Položka X: rozdíl Y proti stavu WinVetu“, když vrstvy WinVetu nesedí na jeho
stav, oříznutí záporného stavu, souhrn neaktivních položek) se ukládají zvlášť do
`stock_mirror_warnings` / `stock_mirror_date` na Stavu synchronizace (záložka „Zrcadlo
skladu“), ne do chyb pushe – jinak by po každém cyklu přepsala `last_error` a skryla
skutečné chyby jiných oblastí.

## Účet z karty pacienta → nabídka

`action_done` (a `mark_done` z karty) po uzavření záznamu s položkami zavolá
`_sync_sale_order()`: jedna **nabídka** (`sale.order` ve stavu draft, nepotvrzuje se) na záznam
(`clinical_record_id`; na nabídce navíc uložené `pet_id`, `doctor_id`, `reservation_id`).
Zákazník = majitel pacienta, `client_order_ref` = „<pacient> – D. M. RRRR“, řádky = řádky účtu
(produkt položky ceníku – i archivovaný; bez produktu „Volná položka“ s názvem řádku), množství,
cena s DPH z řádku (úprava ceny lékařkou platí), pořadí. Opětovné uzavření řádky nabídky
přepíše (tatáž nabídka); záznam bez položek nabídku nemá (dřívější nezaplacenou smaže).
Zápis nabídky běží přes `sudo()` až po kontrole práva zápisu do záznamu.

`payment_state` (počítaný): **Bez účtu** / **Čeká na platbu** / **Částečně zaplaceno** (některý
zaplacený `pos.order` s řádkem nabídky, ale `amount_unpaid` z `pos_sale` > 0 – záloha nebo vyrovnání
jen části) / **Zaplaceno** (zaplaceno nebo fakturováno a `amount_unpaid` = 0) / **Zrušeno** (zrušený
záznam nebo nabídka). Zaplacený záznam nejde znovu otevřít ani zrušit (`UserError` – vratka
v pokladně), částečně zaplacený také ne („Na účet už je zaplacená záloha…“). Když recepce zaplatí
nabídku, zatímco je záznam znovu otevřený, další „Hotovo“ projde, nabídku nechá, jak je, a do
chatteru záznamu zapíše „Účet už byl zaplacen v pokladně – položky účtu se nezměnily.“ Potvrzená,
ale nezaplacená nabídka (bez platby v pokladně) se zruší, vrátí do stavu nabídky a přepíše; stejně
tak zrušená. Zrušení záznamu zruší nezaplacenou nabídku. API karty (`_record_data`) vrací navíc
`payment_state`, `payment_state_label`, `sale_order_name`.

## Příjem zboží čtečkou (`elite.vet.goods.receipt`)

Klientská akce **„Příjem zboží“** (`elite_vet_sale.action_goods_receipt`, menu Ordinace i Sklad →
Operace, skupina Sestra a výš; API kontroluje skupinu `group_clinic_nurse`, recepce nesmí).
Obrazovka je pro tablet: pole pro čtečku má fokus vždy (po každé akci i po kliknutí mimo pole),
čtečka napíše kód + Enter; Ctrl+] (FNC1 čteček v režimu klávesnice) se vloží jako oddělovač GS.
Skeny se zpracují jeden po druhém, takže druhé pípnutí stejné šarže navýší množství o 1.
Poslední naskenovaný řádek je zvýrazněný.

- **Dodavatel:** `suppliers(term)` – nahoře partneři hotových příjmů (od posledního), pak partneři
  pojmenovaní jako dodavatelé vrstev WinVetu (`stock.layer.supplier`, od nejčastějšího, shoda jména bez
  ohledu na velikost písmen); s hledaným textem i další firmy. `create_supplier(name)` založí firmu
  jen se jménem (existující firmu stejného jména použije).
- **Kód:** `gs1.parse` (`models/gs1.py`, čisté funkce) – AI `01` GTIN, `10` šarže, `17` expirace (den
  `00` = poslední den měsíce), `21` sériové číslo; FNC1 `\x1d`, závorkový zápis, prefixy `]d2`/`]C1`/`]Q3`.
  EAN a jiné kódy zůstanou v `raw`. Produkt se hledá podle `barcode` nebo `elite.vet.product.code`
  v podobách GTIN-14 i EAN-13 (bez úvodní 0) a naopak.
- `scan(code)` → `{product, lot, expiry, known, suggested_cost (standard_price bez DPH), vat_rate}`;
  šarže/expirace z GS1, jinak z posledního hotového příjmu produktu (bez příjmu šarže s nejpozdější
  expirací). Neznámý kód → okno s hledáním produktu (`search_products`) → `assign_code(code, product_id)`
  uloží GTIN (u GS1 bez šarže) nebo celý kód do `elite.vet.product.code` (správce je opraví v Sklad →
  Konfigurace → Produkty → Kódy produktů pro čtečku). Produkt se šaržemi bez šarže → pole šarže
  s fokusem.
- `validate(supplier_id, lines, document_number)` → příjemka na hlavním skladu (typ příjmu skladu),
  hotová, řádky stejného produktu a šarže sečtené; `stock.lot` se založí nebo dostane expiraci (12:00);
  `standard_price` = poslední nákupní cena (u kategorie se standardní cenou nastavená před dokončením,
  aby příjem byl oceněný nákupní cenou); číslo dodacího listu jde do `origin`. **Výdaj**
  `elite.vet.expense` (kategorie Léky a zdravotnický materiál, `picking_id` na příjemku, částka
  = Σ množství × cena × (1 + DPH), sazba = ta s největší částkou, zaokrouhlená na 0/12/21).
  Zboží zdarma (částka 0) výdaj nevytvoří.
- **DPH nákupu:** vlastní nákupní daň produktu, pokud ji někdo nastavil; výchozí nákupní daň
  společnosti (21 %), kterou Odoo dá každému novému produktu, se nebere a použije se prodejní daň
  (sazba položky WinVetu) – jinak by léky s 12 % šly do výdaje s 21 %.

**Zkušební provoz** (ruling R14): dokud je WinVet hlavní (`is_winvet_master()`, `init_data()` to
předá obrazovce), obrazovka ukáže upozornění, příjemka se vytvoří a dokončí, ale **výdaj se
nezapíše** (`expense_id` False, „Ve zkušebním provozu se výdaj nezapisuje.“) – plný běh zrcadla
skladu stav příjmu stejně přepíše stavem WinVetu a nákup je v knihách WinVetu.

Další pravidla: nákupní cena se mění jen z řádků s cenou > 0 (zboží zdarma ji nepřepíše); jeden
pohyb na produkt a řádek pohybu na šarži (Odoo slučuje pohyby stejného produktu – jinak by vznikl
nevyřízený doprodej); prošlá šarže (`scan` vrací `expired`) se přijme, řádek ukáže „Prošlá šarže“;
kód načtený čtečkou do pole šarže (začíná `]`, obsahuje GS nebo `(01)`, nebo ≥ 13 číslic) jde do
fronty skenů místo do šarže.

## Přehled skladu (sestry)

Menu **Sklady → Přehled skladu** (`action_stock_overview`, skupina uživatel skladu = Sestra a výš):
stav po šaržích (`stock.quant`, jen interní lokace, seskupeno podle produktu) jen ke čtení
se sloupci produkt, šarže, expirace, množství. Filtry (ve vyhledávání `stock.quant` i `stock.lot`,
tedy i ve standardních obrazovkách Skladu):

- **Dochází** – `product_id.stock_below_minimum`: stav na lokaci pravidla doplnění
  (`stock.warehouse.orderpoint.qty_on_hand`) je pod jeho minimem, nebo je součet na interních
  lokacích záporný (prodáno bez stavu). Úplně vyprodané zboží bez kvantu v seznamu stavů není
  – to ukáže Sklady → Operace → Doplňování zboží → Doplňování.
- **Expiruje do 30 dní** – expirace od teď do konce dne za 30 dní, jen kladné množství.
- **Prošlé** – expirace už prošla, jen kladné množství.

„Expiruje do 30 dní“ a „Prošlé“ se sčítají (nebo), „Dochází“ s nimi platí současně (a).

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
`ensure_setup()` a nabízí `pos_config`, `tax21`, `tax12`, `tax0`; `settle(quotation, method="card",
invoice=False, order_lines=None)` vyrovná nabídku v pokladně Recepce jako `pos_sale` (`sync_from_ui`) a vrátí `pos.order`.

## Pro správce

**WinVet vede, nebo Odoo?** Systémový parametr `elite_vet_sale.winvet_master` (Nastavení →
Technické → Systémové parametry). `1` (výchozí, zkušební provoz): WinVet vede ceník, ceny a sklad,
Odoo je po každém plném běhu mostu přepíše; příjem zboží výdaj nezapisuje a obrazovka ukazuje
upozornění. `0` (po přechodu z WinVetu): ceník ani sklad se nepřepisují, příjem zboží zapisuje
výdaje. Přepnutí zpět na `1` je možné, ale další plný běh přepíše stav skladu stavem WinVetu.

**Zrcadlo skladu** běží po plném běhu mostu (popsáno výše). Upozornění najdete ve **WinVet data →
Stav synchronizace → záložka Zrcadlo skladu** (čas posledního zrcadla a seznam rozdílů).
Chyby pushe jsou dál na první záložce.

**Přesnost množství.** Nastavení zvýší přesnost „Product Unit of Measure“ na 3 desetinná místa
a zaokrouhlení jednotky „Jednotky“ na 0,001 (léky se prodávají i po desetinách balení). Obojí je
**společné pro celou databázi** (všechny produkty, sklady, nákupy, i jiných modulů).

**Kdy běží nastavení.** `ensure_setup()` se spustí při instalaci a při aktualizaci na verzi
18.0.1.0.1 (migrace). Při běžném `-u` bez změny verze se nespouští. Když budoucí verze nastavení
změní (nová platební metoda, daň, pokladna…), musí přidat migraci `migrations/<verze>/post-migrate.py`,
která `ensure_setup()` zavolá – stejně jako 18.0.1.0.1.

**DPH výdaje z příjmu.** Použije se vlastní nákupní daň produktu, jen pokud ji někdo nastavil
ručně; výchozí nákupní daň společnosti (21 %) se ignoruje a bere se sazba prodejní daně (sazba
položky WinVetu). Výdaj má sazbu podle největší části částky, zaokrouhlenou na 0/12/21 %.

**Sazba 0 %** se mapuje na daň `l10n_cz` „0 % Osvobozeno“ (`l10n_cz_other_transaction_deduction`).
**Musí potvrdit účetní** (osvobozené plnění × plnění mimo předmět daně), před ostrým provozem.

**Známé omezení (jiný modul).** `elite_vet_clinic/security/groups.xml` dává správci rezervací
skupinu Lékařka záznamem `<record id="elite_vet_reservation.group_reservation_manager">`. Ten
záznam patří modulu rezervací a je `noupdate`, takže se použije jen při instalaci kliniky, ne při
`-u`. Kdo vazbu ručně odebere, aktualizací ji nevrátí. Role prodeje a skladu v tomto modulu se
zapisují přes `<function>` a aktualizace je obnoví.
