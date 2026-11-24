# Elite Vet – Plánování služeb

Rozšiřuje **Rozpis služeb** (`elite_vet_calendar`) a **Rezervace** (`elite_vet_reservation`).
Nic nového vedle rozpisu nevzniká: každé přiřazení v plánu je směna v Rozpisu služeb
(`elite.vet.shift`) s odkazem na směnu plánu (`planning_slot_id`).

## Kde co je

| Menu | Kdo | Co |
|---|---|---|
| Rozpis služeb › Plánování | Správce rozpisu | Rozpis místností (měsíc × úseky) s panelem Požadavky na směny nad ním, přehled po lidech, bilance hodin, export CSV, PDF, zveřejnění na webu |
| Rozpis služeb › Personál | Správce rozpisu | role, zkratka, úvazek, barva, dovolená, účet |
| Rozpis služeb › Dostupnost a absence | Správce rozpisu | seznam všech záznamů (filtry Absence, Dovolená) |
| Rozpis služeb › Úseky plánu | Správce rozpisu | úseky (Recepce, Ordinace 1, …), jejich směny a časy, ordinace v rezervacích |
| Moje směny › Moje dostupnost | každý interní účet propojený s členem týmu | zaklikání dnů Můžu / Jen ráno / Jen odpoledne / Nemůžu, vlastní směny |

## Propisování

* Lékařka v úseku s ordinací → směna dostane ordinaci → Rezervace z ní udělají službu
  v kalendáři rezervací (`models/shift.py` v `elite_vet_reservation`).
* Ranní + odpolední směna téže lékařky ve stejné ordinaci v jeden den = **jedna** služba
  (8–16 + 12–20 → 8–20). Slučují se jen směny z plánu; ručně zadané překrývající se směny
  dál hlásí kolizi jako dřív.
* Sestry, recepce a výpomoc se do rezervací nepropisují a na webu /rozpis-lekaru se nezobrazují
  (`web_visible`). Ručně zadané směny a celodenní poznámky se zobrazují jako dřív.
* Na webu je u směny čas jejího **typu** (Typy směn), ne čas z plánu.
* **Typ směny** v Rozpisu služeb se bere podle času směny, ne ze směny plánu: vyhraje aktivní typ,
  jehož Od–Do je času nejblíž (8–16 → Ranní 8–14, 12–20 → Odpolední 14–20, 8–20 → Celodenní).
  Při shodě rozhodne typ nastavený u směny plánu. Změna času v plánu typ přepočítá.
* **Skrýt na webu** (oko v dialogu buňky, pole „Skryto na webu“ / `hide_on_web` u směny v Rozpisu
  služeb): služba lékařky zůstane v rozpisu i v kalendáři rezervací, jen ji web neukáže. /rozpis-lekaru
  ji nevypíše a online objednávání lékařku k té službě nenabídne (ani v seznamu lékařů, ani ve volných
  termínech); objednat k ní jde jen přes recepci. Slouží třeba k posílení víkendu druhou lékařkou.
  Ranní + odpolední sloučené do jedné služby: stačí skrýt jednu z nich a skrytá je celá služba.
* **Zveřejnění měsíce** (tlačítko Zveřejnit na webu, model `elite.vet.roster.month`): směny z plánu
  jdou na /rozpis-lekaru, až když je měsíc zveřejněný. Do té doby se dá plánovat, aniž by to klienti
  viděli. Ručně zadané směny v Rozpisu služeb a celodenní poznámky se zobrazují jako dřív. Při
  aktualizaci na 18.0.1.1.0 se zveřejní měsíce, které už směny z plánu mají, aby z webu nic nezmizelo.
* V buňce plánu jsou lékařky na prvním řádku, sestry a ostatní na druhém. V úsecích pro lékaře (Role nahoře
  v nabídce obsahuje `doctor`, nebo tam má lékař v měsíci aspoň jednu směnu) jsou oba řádky vždy, i když tam
  lékař není (prázdný řádek s pomlčkou, i v PDF).

## Přehled po lidech a PDF

* Pod plánem a bilancí hodin je tabulka člověk × den: `R-Ord1` = ranní v Ordinaci 1, `O-Rec` = odpolední na recepci,
  `C · 12h` = ranní a odpolední v jeden všední den (12 h a víc), jinak úsek a čas (`Ord1 10–18`),
  absence zkratkou (D, NV, L, PN, Š). Počítá server (`_people_overview`).
* Tlačítko **PDF** stáhne A4 na šířku: plán po úsecích, bilance, přehled po lidech. PDF dělá server
  (wkhtmltopdf, report `elite_vet_planning.report_roster`). Tisk z prohlížeče do PDF dával soubor,
  který nešel otevřít.

## Bilance

* Fond = pracovní dny měsíce (po–pá bez státních svátků) × úvazek / 5.
* Odpracováno = hodiny směn (překryv v jednom dni se počítá jednou) + D a L v pracovní den × úvazek / 5.
* NV, PN a Š se do odpracovaných hodin nepočítají (Š od 16. 11.). Saldo = odpracováno − fond.
* Celodenní = všední den s 12 h a více; víkend = so + ne.

## Jazyky

Zdrojový jazyk textů je angličtina, čeština je v `i18n/cs_CZ.po`. Odoo totiž překlady kódu do
`en_US` nedělá, s českým zdrojem by anglická verze nešla. Názvy obrazovek z modulů, které jsou zatím
česky (Rozpis lékařů, Rozpis služeb › Lékařky), zůstávají česky i v anglických textech. Názvy úseků a
směn jsou data, ne překlady; dny a měsíce formátuje prohlížeč podle jazyka uživatele.

Účty s jazykem English (US) dostanou rozhraní v English (UK), pokud je ten jazyk aktivní
(`res.users.context_get` v `elite_vet_calendar`). Nastavení účtu zůstává `en_US`.

Po změně textu: `odoo -d <db> -u elite_vet_planning --i18n-overwrite --stop-after-init`.

## Testy

```
odoo -d <db> --test-tags /elite_vet_planning --stop-after-init
```
