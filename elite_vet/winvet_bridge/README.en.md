# WinVet bridge

A standalone Python program that **only reads** the WinVet database (Firebird) and sends the data to
Odoo (module `elite_vet_winvet`). The data format and the transfer rules are defined, as a binding
document, in [`CONTRACT.md`](CONTRACT.md). The current bridge version is 6.1.0 (contract v6).

This folder **is not an Odoo module** (it has no `__manifest__.py`), so Odoo ignores it.

## Safety – why WinVet cannot be damaged

- Every query runs in a transaction opened in **READ ONLY** mode (Firebird itself rejects any
  INSERT/UPDATE/DELETE; verified by a test). Transactions are never committed, they always end with
  ROLLBACK.
- On top of that the program only lets through plain `SELECT` queries from tables (no views, no
  stored procedures; WinVet uses UDF libraries that may not be available).
- Never read: the licence key `VERZE.REGISTRACE`, personal ID numbers, passwords (`HASH`) and
  `KOD_CVK`. Clinical notes `DENNI_ZAZNAM.DEKURS` are read and sent as `visits.notes` since version
  2.0.0 (contract v2). They are **health data**, transfer them over HTTPS only.
- Transactions are short (one per entity, SNAPSHOT isolation, reading in chunks).
- On every connection WinVet writes a row to its own `DBLOG` table (its own trigger). This is normal
  and the program has no influence on it.

## Installation (the Windows PC with WinVet)

1. Install **Python 3.10+** from python.org (tick "Add python.exe to PATH").
2. Copy this folder, for example to `C:\WinVetBridge\`.
3. In the command prompt:
   ```
   cd C:\WinVetBridge
   py -m pip install -r requirements.txt
   copy config.example.ini config.ini
   ```
4. Edit `config.ini`:
   - `[firebird] dsn` – path to the WinVet database, e.g. `localhost/3050:C:\WinVet\Data\WINVET.FDB`
   - password: either `password = …`, or (better) `password_env = WINVET_FB_PASSWORD` with the password
     stored in a system environment variable. A filled-in `password_env` takes precedence: if that
     variable does not exist, the bridge stops with a configuration error even when `password` is
     filled in. For a password directly in the file, empty the `password_env` line (the sample
     `config.ini` has it filled in),
   - `fb_client_library` – path to `fbclient.dll` (installed with Firebird, e.g.
     `C:\Program Files\Firebird\Firebird_3_0\fbclient.dll`). If empty, the driver looks for it itself.
     The bitness of the library (32/64 bit) must match Python.
   - `[odoo] url` and the API key (generate it in Odoo: **WinVet data → Konfigurace → API klíč →
     Vygenerovat nový klíč** (WinVet data → Configuration → API key → Generate a new key); `api_key_env`
     is recommended, the same rule applies as for the password),
   - `[bridge] source = live` (production database) or `backup` (a restored backup).
5. Verification:
   ```
   py -m winvet_bridge --config config.ini check
   py -m winvet_bridge --config config.ini sync --full --dry-run
   ```
   `check` prints the WinVet version, the schema fingerprints and the blocked entities (it does not
   contact Odoo). `--dry-run` only reads the data and counts the batches, it sends nothing and saves no
   state.

## What is transferred (contract v2, bridge 2.0.0; v3 stock, v4 calendar, v5 deposits, v6 stock movements)

Entity order: `users, items, owners, contacts, patients, vaccinations, visits, vitals,
sale_documents, sale_lines, payments, bundles, bundle_lines, phrases, stock_lots, stock_totals,
calendar_resources, calendar_activities, calendar_events, deposits, deposit_uses, stock_moves` (details
in `CONTRACT.md`).

New in v2:

- `items` + `price`, `price_untaxed`, `vat_rate` – the price from price list 1 "Ordinace"
  (`VARIANTA_CENIK`, with several rows the first by `ID_VARIANTA_CENIK`), the VAT rate from
  `VARIANTA.DPH_PRODEJ`.
- `visits` + `notes` – the text of the clinical note. WinVet stores it as a TRichView (RVF) document;
  the bridge extracts only the text paragraphs (images and binary parts are dropped), see
  `winvet_bridge/rvf.py`. Tables with several columns (lab results) stay row by row: one table row =
  one line of text, cells separated by a tab (since 4.0.1); Odoo shows them as a table in the card and
  in the report. Single-column tables (frames around text) are plain paragraphs. An unreadable note →
  `null`, the run never stops.
- `vitals` – measurements during a visit (`DENNI_ZAZNAM_HODNOTA`: temperature, pulse, breathing,
  weight, blood pressure).
- `bundles`, `bundle_lines` – procedure templates (`SABLONA_VYKONU`, `SABLONA_VYKONU_POLOZKA`). They are
  not in the journal → sent in full on every run (like `users` and `contacts`).
- `phrases` – text phrases (`FRAZE`, text converted from RVF the same way as the clinical note).
- A price change (`VARIANTA_CENIK` in the journal) re-sends the affected item; deleting a price list row
  does not delete the item.
- When Odoo answers `unknown entity` (e.g. the clinic module is missing for `bundles`/`phrases`), the
  bridge skips the entity in this run with a warning and carries on.

## WinVet calendar (contract v4, bridge 4.0.0)

The bridge also reads the WinVet calendar (`KALENDAR_NEW`, calendars `KALENDAR_NEW_KALENDAR`, activities
`ORD_CINNOST`) and sends it to Odoo as `calendar_resources`, `calendar_activities` and
`calendar_events`. It only reads; it never writes anything to WinVet, and bookings are made where they
have always been made.

- **Window:** every run reads a window from yesterday to 60 days ahead (`[bridge] calendar_days_back`,
  `calendar_days_ahead`). The calendar is not in the change journal, so the whole window is always read;
  Odoo deletes the records of the window that are no longer in WinVet. Older records stay in Odoo.
- **Recurring records** are expanded by the bridge into single occurrences (it respects WinVet's changed
  and deleted occurrences). The format of the binary columns (`OPAKOVANI_INFO`, `ZDROJ_INFO`) is
  described in `winvet_bridge/scheduler.py`.
- **Time:** WinVet stores the start and end in `KALENDAR_NEW` one hour earlier than it shows them (in
  summer and in winter: a reservation at 10:00 has 09:00 in the column). The bridge adds the hour since
  version 5.0.1; older bridges sent all calendar times one hour early.
- **All-day records** (WinVet stores them from 23:00 of the previous day) are aligned to midnight.
- **Not read:** `ZPRAVA` (notes), reminders, Google ID. `TITULEK` contains client names. This is personal
  data and is never written to the log (the log has counts only).
- **A faster schedule for the calendar only:** `py -m winvet_bridge sync --only calendar` (the journal,
  the cursor and the daily full run do not change). In service mode (`run`) this happens by itself every
  `calendar_interval_minutes` (default 5, 0 = only with the normal run).
- **Version check:** a new fingerprint group `calendar` (3 tables); a structure change blocks only the
  calendar. Bridge 4.0.0 with an older `verified.json` (without the `calendar` group) blocks only the
  calendar until the new version is verified (`approve`). In the repository the group is verified for
  WinVet 2603.
- **Older Odoo** (without the calendar) answers `unknown entity`; the bridge skips the calendar and carries on.

## Running

| Command | What it does |
|---|---|
| `py -m winvet_bridge check` | connection, version, fingerprints, blocked entities (exit code 2 = something is blocked; the same for `sync`; 1 = error, 3 = configuration error) |
| `py -m winvet_bridge sync` | one run: the first run is full, later ones only changes from the WinVet journal |
| `py -m winvet_bridge sync --full` | full synchronisation of everything |
| `py -m winvet_bridge sync --dry-run` | only read and count, send nothing |
| `py -m winvet_bridge sync --only calendar` | only the WinVet calendar (window yesterday … +60 days), no journal; suitable every 5 minutes. `--only` also takes names of entities that are always sent in full (e.g. `stock_moves`); it cannot be combined with `--full` |
| `py -m winvet_bridge run` | service: changes every `interval_minutes` (15 min), the calendar every `calendar_interval_minutes` (5 min) in between, a full synchronisation once a day at `full_sync_time` (03:00) |
| `py -m winvet_bridge schema-diff` | lists all structure differences against the approved snapshot (`--json` for machine-readable output) |
| `py -m winvet_bridge approve --yes` | approves the current WinVet version (see below) |
| `py -m winvet_bridge export --entity owners --out owners.json` | debug export of one entity – **contains personal data**, delete it after use |

Instead of `--config` the configuration can be given with the environment variable `WINVET_BRIDGE_CONFIG`.

### As a service – option A: Task Scheduler (recommended, simpler)

The task starts one run every 15 minutes:

```
schtasks /Create /TN "WinVet bridge" /SC MINUTE /MO 15 /RU SYSTEM ^
  /TR "\"C:\Program Files\Python312\python.exe\" -m winvet_bridge --config C:\WinVetBridge\config.ini sync"
```

In the task "Settings" choose "If the task is already running: Do not start a new instance" and the
working folder `C:\WinVetBridge`. For the daily full synchronisation add a second task
(`/SC DAILY /ST 03:00`, command `sync --full`).

The WinVet calendar (bridge 4.0.0) goes with every run. For new WinVet appointments to appear in the
Odoo calendar within a few minutes, add a third task for the calendar only (every 5 minutes, the same
"Do not start a new instance" setting):

```
schtasks /Create /TN "WinVet bridge - kalendar" /SC MINUTE /MO 5 /RU SYSTEM ^
  /TR "\"C:\Program Files\Python312\python.exe\" -m winvet_bridge --config C:\WinVetBridge\config.ini sync --only calendar"
```

A `--only calendar` run does not read the journal and does not change the cursor. If it meets a run of
the main task, nothing breaks (each reloads the state and changes only its own part).

### Option B: Windows service with NSSM

```
nssm install WinVetBridge "C:\Program Files\Python312\python.exe" "-m winvet_bridge --config C:\WinVetBridge\config.ini run"
nssm set WinVetBridge AppDirectory C:\WinVetBridge
nssm start WinVetBridge
```

The `run` mode takes care of the interval and the daily full run itself (after a PC outage the full run
catches up right after the start) and sends the calendar every `calendar_interval_minutes` (default 5)
between runs, so no third task is needed here.

## Client deposits (contract v5, bridge 5.0.0)

- `deposits` – deposits (`PARTNER_ZALOHA`): client, date, amount, how it was received, used, refunded
  (+ date), balance, a short note. The table is in the change journal → incremental like the others.
- `deposit_uses` – use of deposits in documents (`PARTNER_ZALOHA_CERPANI`), not in the journal → sent in
  full on every run.
- `sale_documents` + `method` – the payment method written on the document (`DOKLAD.FORMA_UHRADY`); on a
  refund (VRAT) it says how the money was returned.
- A received deposit is **not a payment** (`PLATBA`) in WinVet; its use appears in the payment of the
  document as "from deposit". A deposit refund has no payment method in WinVet, it is kept as a cash
  movement.
- **Version check:** a new fingerprint group `deposits`; the fingerprints `sales` (`DOKLAD.FORMA_UHRADY`
  is read) and `journal` (journal triggers on `PARTNER_ZALOHA`) changed too. Bridge 5.0.0 with an old
  `verified.json` would block sales and deposits – **always replace `verified.json` together with the
  bridge** (in the repository it is verified for WinVet 2603).
- **Older Odoo** (without deposits) answers `unknown entity`; the bridge skips the deposits and carries
  on, and an old Odoo ignores the new document key.

## Stock (contract v3, bridge 3.0.0; stock movements contract v6, bridge 6.0.0 and 6.1.0)

- `stock_lots` – stock layers, one per receipt line (`DOKLAD_POLOZKA_SK` with `ZNAMENKO = 1`): item, lot,
  expiry, receipt date, remaining quantity (receipt minus the issues linked to it), unit price, VAT rate
  and supplier (`DOKLAD.PARTNER_NAZEV`).
- `stock_totals` – the stock level of an item (`VARIANTA_SKLAD_STAV`).
- `stock_moves` – all stock movements (receipts and issues from `DOKLAD_POLOZKA_SK`), the source of the
  Regleta skladu (stock report) in Odoo. Since 6.1.0 also `item_vat_rate`: the purchase VAT rate of the
  item (`VARIANTA.ID_DPH_NAKUP` → `DPH.DPH`), or the sale rate `DPH_PRODEJ` when it is not set.
- None of these tables is in the journal → all three are sent in full on every run.
- **Version check:** 6.0.0 changed the `stock` fingerprint, 6.1.0 the `catalog` fingerprint (the table
  `DPH` joined the group). A bridge with an old `verified.json` would block the affected entities –
  **always replace `verified.json` together with the bridge**.
- **Older Odoo** (without stock movements) answers `unknown entity`; the bridge skips the entity and
  carries on, and an old Odoo ignores the new key `item_vat_rate`.

## Updating the bridge

For a new version replace the package `winvet_bridge\`, `verified.json` and `schema_baseline.json` at the
same time (and `requirements.txt` if needed). Leave `config.ini` and the state file where they are,
otherwise the next run would be a full one. If you have run `approve` on this PC, replacing the files
overwrites your approval. After the replacement run `py -m winvet_bridge check`; if something is blocked,
follow the section below.

## WinVet version check (guard)

On every run the program reads the WinVet version number (`VERZE.VERZE`, currently `2603`) and computes
**structure fingerprints** of the tables, by groups. A fingerprint covers only the columns the bridge
really reads (derived from its SQL), their type and nullability (not the text length) and the primary
key; the `journal` group also covers the code of the triggers that fill the change journal. A new column
or a change of a column that is not read therefore blocks nothing. A fingerprint contains no data.

| group | tables | entities that depend on it |
|---|---|---|
| catalog | VARIANTA, VARIANTA_CENIK, KLASIFIKACE_VYROBKU, VARIANTA_TYP, UZIVATEL_NEW, DPH | users, items (incl. prices), stock_moves (purchase rate of the item) |
| owners | PARTNER, PARTNER_KONTAKT, TYP_KONTAKTU | owners, contacts |
| patients | PACIENT, VAKCINACE_ODCERVENI | patients, vaccinations |
| clinical | PRIPAD, DENNI_ZAZNAM, DENNI_ZAZNAM_HODNOTA | visits, vitals, sale_lines (line date) |
| sales | DOKLAD, DOKLAD_POLOZKA_UM, PLATBA, TYP_DOKLADU, DRUH_DOKLADU | sale_documents, sale_lines, payments, stock_lots (supplier column), stock_moves (document number and date) |
| templates | SABLONA_VYKONU, SABLONA_VYKONU_POLOZKA, FRAZE | bundles, bundle_lines, phrases |
| stock | DOKLAD_POLOZKA_SK, VARIANTA_SKLAD_STAV | stock_lots, stock_moves (both also DOKLAD from the sales group), stock_totals |
| calendar | KALENDAR_NEW, KALENDAR_NEW_KALENDAR, ORD_CINNOST | calendar_resources, calendar_activities, calendar_events |
| deposits | PARTNER_ZALOHA, PARTNER_ZALOHA_CERPANI | deposits, deposit_uses |
| journal | ZURNAL, VERZE | incremental synchronisation |

Verified versions and their fingerprints are in `verified.json`.

### Watching structure changes table by table

Besides the fingerprints, on every run the bridge compares the **whole WinVet structure** (all tables,
columns, keys, indexes, triggers, views and procedures) with the approved snapshot `schema_baseline.json`
and sends every difference to Odoo (**WinVet data → Změny struktury WinVetu** (WinVet data → WinVet
structure changes)) with a severity:

| severity | when | what happens |
|---|---|---|
| blocking | a table/column that is read was removed or changed type, a primary key changed | the affected entities are not read |
| journal | a trigger that fills the change journal for synchronised tables was changed or disabled | a full run instead of an incremental one |
| warning | another change in a table that is read (new column, text length, index…) | a warning only, reading continues |
| information | anything else (tables not read, views, procedures) | a record only |

`py -m winvet_bridge schema-diff` lists all differences (`--json` for machine-readable output).
`approve --yes` saves a new snapshot together with the fingerprints.

- **Unknown WinVet version** → everything is blocked, nothing is read. Odoo receives only the status
  (`status`) with the list of blocked entities and shows a warning.
- **Known version but a changed group fingerprint** → only the entities that read the tables of that group
  are blocked, the others keep synchronising. A change of the `journal` group switches incremental runs
  to full ones.
- Blocked entities are sent once in full after they are unblocked (a full synchronisation).

### What to do when a WinVet update blocks something

1. `py -m winvet_bridge check` shows the new version, which groups changed and the first 20 structure
   changes; `py -m winvet_bridge schema-diff` shows all of them (the same list is also in Odoo).
2. Pass the information to the integration administrator. They check on a copy of the database that the
   columns that are read (see `winvet_bridge/entities.py`) still exist and mean the same (`sync --dry-run`,
   or the tests).
3. Only then: `py -m winvet_bridge approve` (shows the changes) and `py -m winvet_bridge approve --yes`
   (writes them to `verified.json` and `schema_baseline.json`). The next run synchronises the blocked
   entities again in full.

Do not run `approve` without verification. The point of the check is that data read from a changed
structure must never reach Odoo.

## Logs and personal data

The log (`log_file`, rotates 5 × 5 MB) and the output on stderr contain only record counts, batch numbers
and errors, **never the content of records** (not even the text of clinical notes). Personal data is
contained only in the debug `export` and, of course, in the transfer to Odoo (use an HTTPS URL).

## State file

`state_file` (JSON) holds `journal_cursor` (the last processed `ZURNAL.ID_ZURNAL`), the date of the last
full run, the time of the last successful run and the entities waiting for a full synchronisation. The
cursor moves only when Odoo has accepted all batches of the run. Deleting the file = the next run is
full. A run is also full when the WinVet journal is shorter than the cursor (the journal started again).

## Development and tests

```
cd winvet_bridge
LD_LIBRARY_PATH=/path/to/fbclient/lib python3 -m unittest discover -s tests -v
```

Integration tests use a local analysis copy of WinVet (variables `WINVET_TEST_DSN`, `WINVET_TEST_USER`,
`WINVET_TEST_PASSWORD`, `WINVET_TEST_FBCLIENT`); when it is not available, they are skipped.

## Daily import of database backups over SFTP on the Odoo server

A finished ZIP with an FBK can be restored automatically on our server and synchronised with the existing
bridge. The complete guide (in Czech), the worker, the restricted SFTP account, Docker Compose and the
systemd timer are in [`deploy/sftp/README.md`](deploy/sftp/README.md).
