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
- Nikdy se nečtou: licenční klíč `VERZE.REGISTRACE`, rodná čísla, hesla (`HASH`), `KOD_CVK`
  a klinické zápisy `DEKURS`.
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

## Spouštění

| Příkaz | Co dělá |
|---|---|
| `py -m winvet_bridge check` | připojení, verze, otisky, blokované entity (návratový kód 2 = něco je blokováno) |
| `py -m winvet_bridge sync` | jeden běh: první běh plný, další jen změny podle žurnálu WinVetu |
| `py -m winvet_bridge sync --full` | plná synchronizace všeho |
| `py -m winvet_bridge sync --dry-run` | jen načíst a spočítat, nic neposílat |
| `py -m winvet_bridge run` | služba: změny každých `interval_minutes` (15 min), plná synchronizace jednou denně v `full_sync_time` (03:00) |
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

### Varianta B: Windows služba přes NSSM

```
nssm install WinVetBridge "C:\Program Files\Python312\python.exe" "-m winvet_bridge --config C:\WinVetBridge\config.ini run"
nssm set WinVetBridge AppDirectory C:\WinVetBridge
nssm start WinVetBridge
```

Režim `run` si sám hlídá interval i denní plný běh (po výpadku PC plný běh doběhne hned po startu).

## Kontrola verze WinVetu (guard)

Program si u každého běhu přečte číslo verze WinVetu (`VERZE.VERZE`, nyní `2603`) a spočítá
**otisky struktury** tabulek po skupinách. Do otisku patří jen sloupce, které most opravdu čte
(odvozené z jeho SQL), jejich typ a povinnost (ne délka textu) a primární klíč; u skupiny `journal`
navíc kód triggerů, které plní žurnál změn. Nový sloupec nebo změna nečteného sloupce proto nic
neblokuje. Žádná data v otisku nejsou.

| skupina | tabulky | entity, které na ní závisí |
|---|---|---|
| catalog | VARIANTA, VARIANTA_CENIK, KLASIFIKACE_VYROBKU, VARIANTA_TYP, UZIVATEL_NEW | users, items |
| owners | PARTNER, PARTNER_KONTAKT, TYP_KONTAKTU | owners, contacts |
| patients | PACIENT, VAKCINACE_ODCERVENI | patients, vaccinations |
| clinical | PRIPAD, DENNI_ZAZNAM | visits, sale_lines (datum řádku) |
| sales | DOKLAD, DOKLAD_POLOZKA_UM, PLATBA, TYP_DOKLADU, DRUH_DOKLADU | sale_documents, sale_lines, payments |
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
chyby, **nikdy obsah záznamů**. Osobní údaje obsahuje jen ladicí `export` a samozřejmě přenos do
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
