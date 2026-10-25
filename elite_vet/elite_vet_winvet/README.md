# WinVet data

Odoo 18 modul. Přijímá data, která z WinVetu posílá most `elite_vet/winvet_bridge`
(rozhraní: `winvet_bridge/CONTRACT.md`), plní z nich kartotéku a analytické tabulky.

## Nastavení

1. Aplikace **WinVet data → Konfigurace → API klíč** → **Vygenerovat nový klíč**.
   Klíč se ukáže jen jednou – zkopírujte ho do nastavení mostu. Odoo ukládá jen jeho
   otisk SHA-256 (`ir.config_parameter` `elite_vet_winvet.api_key_hash`).
2. Most volá `POST /winvet/api/v1/status` a `/winvet/api/v1/push` s hlavičkou
   `Authorization: Bearer <klíč>`.

## Menu (WinVet data)

Tržby (Tržby podle položek, Úkony, Léky a zboží) · Doklady · Platby · Návštěvy · Očkování ·
Kalendář z WinVetu (Záznamy; Kalendáře → ordinace, Činnosti → úkony, Zapnout / vypnout jen
Vedení) · Ceník · Uživatelé WinVet · Stav synchronizace · Konfigurace → API klíč.
Tržby, doklady, platby, ceník, uživatelé a stav vidí **Správce rezervací**; návštěvy
a očkování (i na kartě mazlíčka) vidí i **Recepce**.

## Pravidla importu

- Vše se páruje podle ID z WinVetu (`winvet_ref`), zapisují se jen změněné hodnoty.
- **Majitelé** = kontakty. Osoba je *Klient kliniky*; firma jen když má pacienty; skupina nikdy.
- **Propojení s klientem z webu:** nově založená osoba z WinVetu se při nejbližším příjmu
  kontaktů (téhož běhu) porovná s existujícími aktivními *klienty kliniky bez ID z WinVetu*
  – nejdřív podle e-mailu, pak podle posledních 9 číslic telefonu/mobilu. Při shodě dostane
  ID a údaje z WinVetu stávající klient, záznamy se přepojí k němu a nově založený duplikát
  se smaže. Klient, který už má jiné ID z WinVetu, se nikdy nespojuje.
- **Kontakty:** WinVet je hlavní pro e-mail, mobil a telefon – první kontakt daného typu
  přepíše hodnotu v Odoo; chybějící typ hodnotu v Odoo nemaže. Všechny kontakty jsou na
  kartě kontaktu v záložce *WinVet*.
- **Pacienti** = mazlíčci. Druh se mapuje z textu WinVetu (pes, kočka, králík, hlodavci,
  ptáci, plazi), jinak *Jiné* + původní text. Bez jména → „Bez jména“. Neaktivní ve WinVetu
  → archivován; uhynulý zůstává viditelný s příznakem *Uhynulý*. Poznámka z WinVetu je ve
  vlastním poli, poznámku recepce nepřepisuje. Pacient bez známého majitele patří dočasně
  k archivovanému kontaktu „WinVet – neznámý majitel“ a sám se přepojí, až majitel přijde.
- **Smazání ve WinVetu:** kmenová data (uživatelé, ceník, majitelé, kontakty, pacienti) se
  archivují, analytické řádky (doklady, položky, platby, návštěvy, očkování) se mažou.
  Plná synchronizace navíc archivuje/maže to, co v celém běhu nepřišlo.
- **Souběh s WinVetem (smlouva v2):** u majitelů a pacientů se pole z WinVetu zapíšou jen
  u nového záznamu nebo když se změnil ve WinVetu (příchozí `modified` ≠ uložené
  `winvet_modified`). Úprava v Odoo tak vydrží, dokud záznam ve WinVetu někdo nezmění. Bez
  `modified` (prázdné / neplatné) se porovnávají hodnoty jako dřív. Archivace smazaných
  a sesouhlasení plného běhu platí beze změny.
- **Sloučení majitelů v Odoo** (standardní průvodce): cíl si nechá své ID z WinVetu (nebo
  převezme první ID sloučených), ostatní ID se uloží do `winvet_alias_refs`. Most pak sloučené
  majitele znovu nezakládá ani nepřepisuje a jejich pacienty, kontakty a doklady přiřadí k cíli.
- **Ceník** má cenu s DPH, bez DPH a sazbu DPH (ceník „Ordinace“ ve WinVetu); **návštěvy**
  text dekurzu (`notes`) a **vitální hodnoty** (`elite.vet.visit.vital`: čas, teplota, tep,
  dech, hmotnost, tlak) – smazané ve WinVetu se mažou.
- Nesmyslná data (např. rok 0218) se uloží prázdná a vypíšou ve *Stavu synchronizace*.
- **Upozornění:** změna verze WinVetu nebo zablokované oblasti → červený pruh na Stavu
  synchronizace, zpráva a aktivita pro správce. Stejné zablokování se hlásí jen jednou.

## Kalendář z WinVetu (kontrakt v4)

Most 4.0.0 posílá i kalendář WinVetu: kalendáře (`calendar_resources`), činnosti
(`calendar_activities`) a záznamy (`calendar_events`, okno od včerejška na 60 dní, opakované
záznamy rozložené na výskyty). Jen jedním směrem – Odoo do WinVetu nikdy nezapisuje.

- **Modely:** `elite.vet.winvet.calendar.resource` (kalendář → ordinace `room_id`),
  `elite.vet.winvet.calendar.activity` (činnost → úkon `procedure_id`),
  `elite.vet.winvet.calendar.event` (jeden výskyt, klíč `key`, jen pro čtení – zápis a mazání mimo
  synchronizaci odmítne). Záznamy nemají chatter, neposílají e-maily, nemají připomínky, nepočítají
  se do Nedorazil, Historie rezervací ani přehledů rezervací (jsou mimo `elite.vet.reservation`).
- **Mapování** (menu **WinVet data → Kalendář z WinVetu**, Vedení): kalendář dostane ordinaci se
  stejným názvem („ORDINACE 1“ = „Ordinace 1“, „Sál“ = „SAL“; velikost písmen, diakritika
  a mezery se nerozlišují), skrytý kalendář WinVetu (ZOBRAZIT = N, např. „Georgiana - sál“)
  zůstane bez ordinace. Činnost dostane aktivní úkon stejného názvu (cs nebo en). Ručně zvolená
  ordinace / úkon se už synchronizací nemění (příznak *Nastaveno ručně*; vyprázdnění = zase
  automaticky).
- **Klient a zvíře** se párují podle ID z WinVetu kartotéky (`res.partner.winvet_ref`,
  `elite.vet.pet.winvet_ref`); bez shody zůstane jen text z WinVetu (TITULEK).
- **Tabule** (backend i pokladna): záznam s časem v namapované ordinaci = šedá šrafovaná karta
  s proužkem v barvě WinVetu a štítkem **WinVet**, název = zvíře (majitel) z kartotéky, jinak text
  z WinVetu; nejde přetáhnout, nemá akce (v backendu se klikem otevře jen pro čtení). Celodenní
  záznamy jsou štítky **WinVet · …** v hlavičce ordinace a nic neblokují.
- **Obsazení termínu:** záznam s časem v namapované ordinaci obsadí termín pro všechna objednávání
  v Odoo (web, chat, průvodce recepce, Objednat v pokladně, přetažení na tabuli, každé uložení) –
  přes `elite.vet.reservation._busy_external`, druhou půlku jediného pravidla obsazenosti vedle
  `_busy_domain`. Blokace (oběd, porada) jde přes záznam z WinVetu vložit.
- **Mazání:** poslední dávka běhu smaže záznamy okna, které ve WinVetu už nejsou; starší
  záznamy mimo okno zůstanou.
- **Vypnutí** (WinVet data → Kalendář z WinVetu → Zapnout / vypnout, Vedení): *Vypnout kalendář
  z WinVetu* = záznamy zmizí z tabule a z Dnes, nic neblokují a nové záznamy z mostu se neukládají
  (most je dál posílá, Odoo odpoví ok a započítá je jako přeskočené). Pro přechod na objednávání
  v Odoo. *Smazat přenesené záznamy* smaže všechny přenesené záznamy (ve WinVetu zůstanou; zapnutý
  kalendář okno další běh mostu znovu naplní). Přepínač je `ir.config_parameter`
  `elite_vet_winvet.calendar_enabled` (chybí = zapnuto).
- **Dnes v pokladně** (`elite_vet_reception`): dnešní záznamy se zvířetem z kartotéky jsou
  v Přicházejí se štítkem WinVet a jdou přijmout (návštěva v namapované ordinaci).

## Rozšíření o další entity

Seznam přijímaných entit a jejich modely, popisky, kmenová data a dodatečné propojení jsou
metody `elite.vet.winvet.sync` (`_winvet_entities`, `_winvet_entity_models`,
`_winvet_entity_labels`, `_winvet_master_entities`, `_winvet_fixups`); jiný modul je rozšíří
a doplní `_push_<entita>` (takto `elite_vet_clinic` přidává `bundles`, `bundle_lines`,
`phrases`). Zápisy mostu mají v kontextu `winvet_sync=True`.

## Testy

`bash elite_vet/nasazeni/testy-winvet.sh` (poprvé), dál `bash elite_vet/nasazeni/testy-winvet.sh "" update`.
