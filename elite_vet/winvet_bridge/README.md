# WinVet bridge

Samostatný program v Pythonu, který **pouze čte** databázi WinVet (Firebird) a posílá data do Odoo
(modul `elite_vet_winvet`). Formát dat a pravidla přenosu jsou závazně popsána v
[`CONTRACT.md`](CONTRACT.md).

Tato složka **není Odoo modul** (nemá `__manifest__.py`) – Odoo ji ignoruje.

## Bezpečnost – proč WinVet nemůže nic poškodit

- Každý dotaz běží v transakci otevřené v režimu **READ ONLY** (Firebird sám odmítne jakýkoli
  INSERT/UPDATE/DELETE – ověřeno testem). Transakce se nikdy necommitují, vždy končí ROLLBACK.
- Program navíc pustí jen obyčejné `SELECT` dotazy z tabulek (žádné pohledy, žádné uložené
  procedury – WinVet používá UDF knihovny, které nemusí být k dispozici).
- Nikdy se nečtou: licenční klíč `VERZE.REGISTRACE`, rodná čísla, hesla (`HASH`) a `KOD_CVK`.
  Klinické zápisy `DENNI_ZAZNAM.DEKURS` se od verze 2.0.0 (kontrakt v2) čtou a posílají jako
  `visits.notes` – jsou to **zdravotní údaje**, přenos jen přes HTTPS.
- Transakce jsou krátké (jedna na entitu, izolace SNAPSHOT, čtení po dávkách).
- WinVet při každém připojení zapíše řádek do své tabulky `DBLOG` (jeho vlastní trigger) – to je
  normální a program to nijak neovlivňuje.

## Instalace (Windows PC s WinVetem)

1. Nainstalujte **Python 3.10+** z python.org (zaškrtněte „Add python.exe to PATH“).
2. Zkopírujte tuto složku např. do `C:\WinVetBridge\`.
3. V příkazovém řádku:
   ```
   cd C:\WinVetBridge
   py -m pip install -r requirements.txt
   copy config.example.ini config.ini
   ```
4. Upravte `config.ini`:
   - `[firebird] dsn` – cesta k databázi WinVet, např. `localhost/3050:C:\WinVet\Data\WINVET.FDB`
   - heslo: buď `password = …`, nebo (lépe) `password_env = WINVET_FB_PASSWORD` a heslo uložte do
     systémové proměnné prostředí,
   - `fb_client_library` – cesta k `fbclient.dll` (instaluje se s Firebirdem, např.
     `C:\Program Files\Firebird\Firebird_3_0\fbclient.dll`). Pokud je prázdné, ovladač ji hledá sám.
     Bitová verze knihovny (32/64 bit) musí odpovídat Pythonu.
   - `[odoo] url` a API klíč (vygenerujete v Odoo v nastavení modulu; doporučeno přes
     `api_key_env`),
   - `[bridge] source = live` (produkční databáze) nebo `backup` (obnovená záloha).
5. Ověření:
   ```
   py -m winvet_bridge --config config.ini check
   py -m winvet_bridge --config config.ini sync --full --dry-run
   ```
   `check` vypíše verzi WinVetu, otisky schématu a blokované entity (Odoo nekontaktuje).
   `--dry-run` data jen načte a spočítá dávky, nic neodesílá a neukládá stav.

## Co se přenáší (kontrakt v2, most 2.0.0; v3 sklad, v4 kalendář, v5 zálohy)

Pořadí entit: `users, items, owners, contacts, patients, vaccinations, visits, vitals,
sale_documents, sale_lines, payments, bundles, bundle_lines, phrases, stock_lots, stock_totals,
calendar_resources, calendar_activities, calendar_events, deposits, deposit_uses` (podrobně
v `CONTRACT.md`).

Novinky v2:

- `items` + `price`, `price_untaxed`, `vat_rate` – cena z ceníku 1 „Ordinace“ (`VARIANTA_CENIK`,
  při více řádcích první podle `ID_VARIANTA_CENIK`), sazba DPH z `VARIANTA.DPH_PRODEJ`.
- `visits` + `notes` – text dekurzu. WinVet ho ukládá jako dokument TRichView (RVF); most z něj
  vytáhne jen textové odstavce (obrázky a binární části zahodí), viz `winvet_bridge/rvf.py`.
  Tabulky s víc sloupci (laboratorní výsledky) zůstanou po řádcích – jeden řádek tabulky = jeden
  řádek textu, buňky oddělené tabulátorem (od 4.0.1); Odoo je v kartě i ve zprávě ukáže jako
  tabulku. Jednosloupcové tabulky (rámečky kolem textu) jsou obyčejné odstavce. Nečitelný dekurz → `null`, běh se nikdy nezastaví.
- `vitals` – měření během návštěvy (`DENNI_ZAZNAM_HODNOTA`: teplota, tep, dech, hmotnost, tlak).
- `bundles`, `bundle_lines` – šablony výkonů (`SABLONA_VYKONU`, `SABLONA_VYKONU_POLOZKA`), nejsou
  v žurnálu → posílají se při každém běhu celé (jako `users` a `contacts`).
- `phrases` – textové fráze (`FRAZE`, text převeden z RVF stejně jako dekurz).
- Změna ceny (`VARIANTA_CENIK` v žurnálu) znovu pošle dotčenou položku; smazání řádku ceníku
  položku nemaže.
- Když Odoo odpoví `unknown entity` (např. chybí modul kliniky pro `bundles`/`phrases`), most
  entitu v tomto běhu přeskočí s varováním a pokračuje dál.

## Kalendář WinVetu (kontrakt v4, most 4.0.0)

Most čte i kalendář WinVetu (`KALENDAR_NEW`, kalendáře `KALENDAR_NEW_KALENDAR`, činnosti
`ORD_CINNOST`) a posílá ho do Odoo jako `calendar_resources`, `calendar_activities` a
`calendar_events`. Jen čte – do WinVetu nikdy nic nezapisuje, objednává se dál tam, kde dosud.

- **Okno:** při každém běhu se čte okno od včerejška na 60 dní dopředu (`[bridge]
  calendar_days_back`, `calendar_days_ahead`). Kalendář není v žurnálu změn, proto se okno čte vždy
  celé; Odoo smaže záznamy okna, které ve WinVetu už nejsou. Starší záznamy v Odoo zůstanou.
- **Opakované záznamy** most rozloží na jednotlivé výskyty (změněné a smazané výskyty WinVetu
  respektuje). Formát binárních sloupců (`OPAKOVANI_INFO`, `ZDROJ_INFO`) je popsaný v
  `winvet_bridge/scheduler.py`.
- **Čas:** WinVet ukládá začátek a konec v `KALENDAR_NEW` o hodinu dřív, než ho ukazuje (v létě i
  v zimě: rezervace v 10:00 má ve sloupci 09:00). Most od verze 5.0.1 hodinu přičítá; starší most
  posílal všechny časy kalendáře o hodinu dřív.
- **Celodenní záznamy** (WinVet je ukládá od 23:00 předchozího dne) se zarovnají na půlnoc.
- **Nečte se:** `ZPRAVA` (poznámky), připomínky, Google ID. `TITULEK` obsahuje jména klientů – jsou
  to osobní údaje, do logu se nikdy nepíšou (log má jen počty).
- **Rychlejší plán jen pro kalendář:** `py -m winvet_bridge sync --only calendar` (žurnál, kurzor
  ani denní plný běh se nemění). Ve službě (`run`) se to děje samo každých
  `calendar_interval_minutes` (výchozí 5, 0 = jen s normálním během).
- **Kontrola verze:** nová skupina otisků `calendar` (3 tabulky); změna struktury zablokuje jen
  kalendář. Most 4.0.0 se starším `verified.json` (bez skupiny `calendar`) blokuje jen kalendář,
  dokud se nová verze neověří (`approve`). V repozitáři je skupina ověřená pro WinVet 2603.
- **Starší Odoo** (bez kalendáře) odpoví `unknown entity` – most kalendář přeskočí a pokračuje.

## Spouštění

| Příkaz | Co dělá |
|---|---|
| `py -m winvet_bridge check` | připojení, verze, otisky, blokované entity (návratový kód 2 = něco je blokováno) |
| `py -m winvet_bridge sync` | jeden běh: první běh plný, další jen změny podle žurnálu WinVetu |
| `py -m winvet_bridge sync --full` | plná synchronizace všeho |
| `py -m winvet_bridge sync --dry-run` | jen načíst a spočítat, nic neposílat |
| `py -m winvet_bridge sync --only calendar` | jen kalendář WinVetu (okno včera … +60 dní), bez žurnálu; vhodné každých 5 minut |
| `py -m winvet_bridge run` | služba: změny každých `interval_minutes` (15 min), mezi tím kalendář každých `calendar_interval_minutes` (5 min), plná synchronizace jednou denně v `full_sync_time` (03:00) |
| `py -m winvet_bridge approve --yes` | schválí aktuální verzi WinVetu (viz níže) |
| `py -m winvet_bridge export --entity owners --out owners.json` | ladicí export jedné entity – **obsahuje osobní údaje**, po použití smažte |

Konfiguraci lze místo `--config` předat proměnnou prostředí `WINVET_BRIDGE_CONFIG`.

### Jako služba – varianta A: Plánovač úloh (doporučeno, jednodušší)

Úloha každých 15 minut spustí jeden běh:

```
schtasks /Create /TN "WinVet bridge" /SC MINUTE /MO 15 /RU SYSTEM ^
  /TR "\"C:\Program Files\Python312\python.exe\" -m winvet_bridge --config C:\WinVetBridge\config.ini sync"
```

V „Nastavení“ úlohy zvolte „Pokud je úloha již spuštěna: Nespouštět novou instanci“ a pracovní
složku `C:\WinVetBridge`. Pro denní plnou synchronizaci přidejte druhou úlohu
(`/SC DAILY /ST 03:00`, příkaz `sync --full`).

Kalendář WinVetu (most 4.0.0) jde s každým během. Aby se nové objednávky z WinVetu objevily na
tabuli Odoo do pár minut, přidejte třetí úlohu jen pro kalendář (každých 5 minut, stejné
nastavení „Nespouštět novou instanci“):

```
schtasks /Create /TN "WinVet bridge - kalendar" /SC MINUTE /MO 5 /RU SYSTEM ^
  /TR "\"C:\Program Files\Python312\python.exe\" -m winvet_bridge --config C:\WinVetBridge\config.ini sync --only calendar"
```

Běh `--only calendar` nečte žurnál a nemění kurzor; když se potká s během hlavní úlohy, nic se
nepokazí (každý si načte stav znovu a mění jen svou část).

### Varianta B: Windows služba přes NSSM

```
nssm install WinVetBridge "C:\Program Files\Python312\python.exe" "-m winvet_bridge --config C:\WinVetBridge\config.ini run"
nssm set WinVetBridge AppDirectory C:\WinVetBridge
nssm start WinVetBridge
```

Režim `run` si sám hlídá interval i denní plný běh (po výpadku PC plný běh doběhne hned po startu)
a mezi běhy posílá kalendář každých `calendar_interval_minutes` (výchozí 5) – třetí úloha tu není potřeba.

## Zálohy klientů (kontrakt v5, most 5.0.0)

- `deposits` – zálohy (`PARTNER_ZALOHA`): klient, datum, částka, forma přijetí, čerpáno, vráceno
  (+ datum), zůstatek, krátká poznámka. Tabulka je v žurnálu změn → přírůstkově jako ostatní.
- `deposit_uses` – čerpání záloh do dokladů (`PARTNER_ZALOHA_CERPANI`), není v žurnálu → při každém
  běhu celé.
- `sale_documents` + `method` – forma úhrady zapsaná na dokladu (`DOKLAD.FORMA_UHRADY`); u vratky
  (VRAT) říká, jak se peníze vracely.
- Přijatá záloha ve WinVetu **není platba** (`PLATBA`), čerpání se v platbě dokladu objeví jako „ze
  zálohy“. Vrácení zálohy nemá ve WinVetu formu úhrady – vede se jako hotovostní pohyb.
- **Kontrola verze:** nová skupina otisků `deposits`; zároveň se změnily otisky `sales` (čte se
  `DOKLAD.FORMA_UHRADY`) a `journal` (triggery žurnálu u `PARTNER_ZALOHA`). Most 5.0.0 se starým
  `verified.json` by zablokoval tržby a zálohy – **`verified.json` vždy nahradit spolu s mostem**
  (v repozitáři ověřený pro WinVet 2603).
- **Starší Odoo** (bez záloh) odpoví `unknown entity` – most zálohy přeskočí a pokračuje; nový klíč
  dokladu staré Odoo ignoruje.

## Kontrola verze WinVetu (guard)

Program si u každého běhu přečte číslo verze WinVetu (`VERZE.VERZE`, nyní `2603`) a spočítá
**otisky struktury** tabulek po skupinách. Do otisku patří jen sloupce, které most opravdu čte
(odvozené z jeho SQL), jejich typ a povinnost (ne délka textu) a primární klíč; u skupiny `journal`
navíc kód triggerů, které plní žurnál změn. Nový sloupec nebo změna nečteného sloupce proto nic
neblokuje. Žádná data v otisku nejsou.

| skupina | tabulky | entity, které na ní závisí |
|---|---|---|
| catalog | VARIANTA, VARIANTA_CENIK, KLASIFIKACE_VYROBKU, VARIANTA_TYP, UZIVATEL_NEW | users, items (vč. cen) |
| owners | PARTNER, PARTNER_KONTAKT, TYP_KONTAKTU | owners, contacts |
| patients | PACIENT, VAKCINACE_ODCERVENI | patients, vaccinations |
| clinical | PRIPAD, DENNI_ZAZNAM, DENNI_ZAZNAM_HODNOTA | visits, vitals, sale_lines (datum řádku) |
| sales | DOKLAD, DOKLAD_POLOZKA_UM, PLATBA, TYP_DOKLADU, DRUH_DOKLADU | sale_documents, sale_lines, payments, stock_lots (sloupec dodavatele) |
| templates | SABLONA_VYKONU, SABLONA_VYKONU_POLOZKA, FRAZE | bundles, bundle_lines, phrases |
| stock | DOKLAD_POLOZKA_SK, VARIANTA_SKLAD_STAV | stock_lots (také DOKLAD ze skupiny sales), stock_totals |
| calendar | KALENDAR_NEW, KALENDAR_NEW_KALENDAR, ORD_CINNOST | calendar_resources, calendar_activities, calendar_events |
| deposits | PARTNER_ZALOHA, PARTNER_ZALOHA_CERPANI | deposits, deposit_uses |
| journal | ZURNAL, VERZE | přírůstková synchronizace |

Ověřené verze a jejich otisky jsou v `verified.json`.

### Hlídání změn struktury po tabulkách

Vedle otisků most při každém běhu porovná **celou strukturu WinVetu** (všechny tabulky, sloupce,
klíče, indexy, triggery, pohledy a procedury) se schváleným snímkem `schema_baseline.json` a každý
rozdíl pošle do Odoo (WinVet data → Změny struktury WinVetu) se závažností:

| závažnost | kdy | co se stane |
|---|---|---|
| blokující | čtená tabulka/sloupec odebrán nebo změnil typ, změna primárního klíče | dotčené entity se nečtou |
| žurnál | změněn/vypnut trigger, který plní žurnál změn u synchronizovaných tabulek | místo přírůstkové synchronizace plná |
| upozornění | jiná změna ve čtené tabulce (nový sloupec, délka textu, index…) | jen upozornění, čtení běží |
| informace | cokoli jinde (nečtené tabulky, pohledy, procedury) | jen záznam |

`py -m winvet_bridge schema-diff` vypíše všechny rozdíly (`--json` strojově). `approve --yes`
uloží nový snímek spolu s otisky.

- **Neznámá verze WinVetu** → blokuje se všechno, nic se nečte. Odoo dostane jen stav
  (`status`) se seznamem blokovaných entit a zobrazí upozornění.
- **Známá verze, ale změněný otisk skupiny** → blokují se jen entity, které čtou tabulky té skupiny,
  ostatní se synchronizují dál. Změna skupiny `journal` přepne přírůstkové běhy na plné.
- Blokované entity se po odblokování jednou pošlou celé (plná synchronizace).

### Co dělat, když aktualizace WinVetu něco zablokuje

1. `py -m winvet_bridge check` – ukáže novou verzi, které skupiny se změnily a prvních 20 změn
   struktury; `py -m winvet_bridge schema-diff` všechny (stejný seznam je i v Odoo).
2. Předejte informaci správci integrace. Ten na kopii databáze ověří, že čtené sloupce
   (viz `winvet_bridge/entities.py`) stále existují a mají stejný význam (`sync --dry-run`,
   případně testy).
3. Teprve potom: `py -m winvet_bridge approve` (ukáže změny) a `py -m winvet_bridge approve --yes`
   (zapíše je do `verified.json`). Další běh synchronizuje blokované entity znovu celé.

Bez ověření `approve` nespouštějte – smyslem kontroly je, aby se do Odoo nikdy nedostala data
přečtená ze změněné struktury.

## Logy a osobní údaje

Log (`log_file`, rotuje 5 × 5 MB) a výstup na stderr obsahují jen počty záznamů, čísla dávek a
chyby, **nikdy obsah záznamů** (ani text dekurzů). Osobní údaje obsahuje jen ladicí `export` a samozřejmě přenos do
Odoo (používejte HTTPS URL).

## Stavový soubor

`state_file` (JSON) drží `journal_cursor` (poslední zpracované `ZURNAL.ID_ZURNAL`), datum posledního
plného běhu a entity čekající na plnou synchronizaci. Kurzor se posune jen tehdy, když Odoo přijalo
všechny dávky běhu. Smazání souboru = příští běh bude plný.

## Vývoj a testy

```
cd winvet_bridge
LD_LIBRARY_PATH=/cesta/k/fbclient/lib python3 -m unittest discover -s tests -v
```

Integrační testy používají lokální analytickou kopii WinVetu (proměnné `WINVET_TEST_DSN`,
`WINVET_TEST_PASSWORD`, `WINVET_TEST_FBCLIENT`); když není dostupná, přeskočí se.

## Denní příjem záloh přes SFTP na serveru Odoo

Hotový ZIP s FBK lze automaticky obnovovat na našem serveru a synchronizovat
existujícím mostem. Kompletní český návod, worker, omezený SFTP účet, Docker Compose
a systemd timer jsou v [`deploy/sftp/README.md`](deploy/sftp/README.md).
