# WinVet bridge ⇄ Odoo contract (v1 + v2 + v3 + v4, see the sections below)

The bridge (`elite_vet/winvet_bridge`, standalone Python) reads WinVet (Firebird, read-only) and
pushes JSON to the Odoo module `elite_vet_winvet`. This file is the single source of truth for the
payloads; both sides must follow it exactly.

## Transport

- JSON-RPC 2.0 over HTTPS to Odoo `type="json"` routes (body `{"jsonrpc": "2.0", "params": {...}}`,
  answer in `result`).
- Auth: header `Authorization: Bearer <api key>`. The key is generated in Odoo (settings of the
  module); Odoo stores only its SHA-256 hash and compares with `hmac.compare_digest`. Wrong/missing
  key → `{"ok": false, "error": "unauthorized"}` (no detail).
- All dates `YYYY-MM-DD`, datetimes `YYYY-MM-DD HH:MM:SS` (Europe/Prague local time, as stored in
  WinVet), numbers as JSON numbers, empty values `null`. Strings are trimmed; WinVet text BLOBs are
  decoded to text (WIN1250 handled by the driver, connection charset UTF8).

## Routes

### `POST /winvet/api/v1/status`

Sent at the start of every run, before any data.

```json
{"bridge_version": "1.0.0", "source": "live|backup", "winvet_version": "2603",
 "ods": "13.1", "engine": "5.0.1",
 "fingerprints": {"owners": "…16 hex…", "patients": "…", "clinical": "…", "sales": "…", "catalog": "…", "journal": "…"},
 "blocked": ["sales"], "journal_cursor": 13432, "message": "free text or null"}
```

Since bridge 1.0.0 the status also carries the table-level schema watch (optional keys; Odoo
must accept a status without them):

```json
{"schema_hash": "…16 hex…", "schema_baseline_hash": "…16 hex…|null",
 "schema_change_counts": {"breaking": 1, "journal": 1, "warning": 2, "info": 1},
 "schema_changes": [{"object": "column", "table": "PLATBA", "name": "DATUM_VRACENO", "change": "removed",
                     "old": "DATE", "new": null, "severity": "breaking"}, ...]}
```

`schema_changes` = differences between the live schema and the baseline approved in the bridge
(max. 300, most severe first). `object`: table, view, column, primary_key, unique, foreign_key,
index, trigger, procedure, db_trigger; `change`: added, removed, changed; `severity`: breaking
(a read table/column removed or retyped – the entity is blocked), journal (a trigger writing ZURNAL
for a synced table changed – incremental sync replaced by full), warning (other change in a read
table), info (anything else). The same `schema_hash` is reported on every run until the schema
changes again or the change is approved (`approve` stores a new baseline).

`blocked` = entities the bridge refuses to read because the WinVet version or the fingerprint is
not on its verified list. Odoo stores the status, shows it and raises an activity/alert when
`blocked` is not empty or `winvet_version` changed. Answer: `{"ok": true}`.

### `POST /winvet/api/v1/push`

```json
{"entity": "owners", "mode": "full|incremental", "records": [ {...}, ... ], "deleted": [12, 15],
 "batch": 1, "batches": 3, "run_id": "2026-10-15T12:00:00/abc123"}
```

- `records`: upsert by WinVet `id` (stored in Odoo as `winvet_ref`, unique per model).
- `deleted`: WinVet ids deleted in WinVet → Odoo archives (`active=False`) master data, deletes
  analytic rows (sale lines, payments, documents, visits, vaccinations).
- `mode=full` + last batch (`batch == batches`): Odoo archives/deletes rows of that entity whose
  `winvet_ref` did not appear in any batch of this `run_id` (full resync reconciliation).
- Batches ≤ 500 records. Answer: `{"ok": true, "created": n, "updated": n, "deleted": n, "skipped": n}`.
- Push order in a run (dependencies first): `users, items, owners, contacts, patients,
  vaccinations, visits, sale_documents, sale_lines, payments`.
- Unknown referenced id (e.g. patient whose owner is not in Odoo): the record is still stored, the
  link stays empty and the answer counts it in `skipped` only if it cannot be stored at all.

## Entities and record fields

WinVet source in brackets. `id` is always the WinVet primary key.

### users  [UZIVATEL_NEW]
`id, name (UZIVATEL_NAZEV), code (ZKRATKA), active (AKTIVNI='A')`
Never send RODNE_CISLO, HASH, KOD_CVK.

### items  [VARIANTA]  – catalog of services and products
`id, code (VARIANTA), name (VARIANTA_NAZEV), classification, stock_tracked (USE_SKLAD='A'),
tracked_drug (SLEDOVANE_LECIVO='A'), unit (MERNA_JEDNOTKA_VY), barcode (CAROVY_KOD), active (AKTIVNI<>'N')`
`classification` from ID_KLASIFIKACE_VYROBKU: 0 group, 1 product, 2 set, 3 kit, 4 service,
5 operation, 6 alias, 7..11 other → strings `group|product|set|kit|service|operation|alias|other`.

### owners  [PARTNER]
`id, kind (ID_TRIDA_PARTNERA: 0 company, 1 person, 2 group), name (PARTNER_NAZEV), first_name (JMENO),
last_name (PRIJMENI), title (TITUL), street (ULICE), zip (PSC), city (OBEC), country (STAT_NAZEV),
company_reg (IDENTIFIKATOR), vat (DIC), note (POZNAMKA text), important_note (POZNAMKA_DULEZITE='A'),
active (AKTIVNI<>'N'), created (ZALOZENI_ZAZNAMU), modified (POSLEDNI_MODIFIKACE + CAS)`

### contacts  [PARTNER_KONTAKT]  – not in the change journal, always sent in full
`id, owner_id (ID_PARTNER), type (ID_TYP_KONTAKTU: -1 mobile, -2 phone, -3 fax, -4 email, -5 web),
value (PARTNER_KONTAKT), label (PARTNER_KONTAKT_NAZEV)`

### patients  [PACIENT]
`id, owner_id (ID_PARTNER), name (PACIENT_NAZEV), species (DRUH, raw text e.g. "pes"), breed (RASA),
sex (POHLAVI raw text), color (BARVA), birth_date (DATUM_NAROZENI), birth_year (ROK_NAROZENI),
chip (KOD_RID), tattoo (KOD_TETOVACI), passport (CISLO_PASU), weight (HMOTNOST), deceased (UHYN='A'),
death_date (EUTHANAZIE_DATUM), active (AKTIVNI<>'N'), registered (DATUM_REGISTRACE),
next_vaccination (PRISTI_VAKCINACE), next_deworming (PRISTI_ODCERVENI), important (DULEZITE),
note (POZNAMKA text), created, modified`

### vaccinations  [VAKCINACE_ODCERVENI]
`id, patient_id, date (DATUM), next_date (DATUM_PRISTI), item_id (ID_VARIANTA), item_name (VARIANTA_NAZEV),
quantity (MNOZSTVI), unit (MERNA_JEDNOTKA), kind (TYP int, raw)`

### visits  [DENNI_ZAZNAM]  – one clinical record / visit
`id, patient_id, date (DATUM), time (CAS "HH:MM:SS"), case_name (PRIPAD), diagnosis_code (DIAGNOZA),
diagnosis_name (DIAGNOZA_NAZEV), entered_by (ID_ZALOZIL → users.id), document_id (ID_DOKLAD)`
Do not send DEKURS (clinical notes) in v1.

### sale_documents  [DOKLAD where TYP_DOKLADU in ('UM','PODP','FAV','VRAT')]
`id, type (TYP_DOKLADU), number (DOKLAD), parent_id (ID_PREDEK), owner_id (ID_PARTNER), date (DATUM_DOKLADU),
total (CENA), paid (ZAPLACENO), from_deposit (ZE_ZALOHY), state (TABLE_STATUS), entered_by (ID_ZALOZIL)`

### sale_lines  [DOKLAD_POLOZKA_UM]  – one line of an owner account (service or product)
`id, document_id (ID_DOKLAD), visit_id (ID_DENNI_ZAZNAM), item_id (ID_VARIANTA), item_code (VARIANTA),
item_name (VARIANTA_NAZEV), quantity (MNOZSTVI), unit (MERNA_JEDNOTKA), unit_price (CENA_MJ),
amount (CENA – final price, clinic is not a VAT payer), vat_rate (SAZBA_DPH), date (DENNI_ZAZNAM.DATUM,
fallback DOKLAD.DATUM_DOKLADU), entered_by (ID_ZALOZIL)`

### payments  [PLATBA]
`id, document_id (ID_DOKLAD), owner_id (ID_PARTNER), date (DATUM), time (CAS), method (FORMA_UHRADY:
HOT cash, PLATK card, PREV transfer, other codes lower-cased), amount (ZAPLACENO),
from_deposit (ZE_ZALOHY), state (TABLE_STATUS), refunded_date (DATUM_VRACENO)`

## Change journal (incremental mode)

`ZURNAL(ID_ZURNAL, TABULKA, ID_ZAZNAM, AKCE I/U/D)`. The bridge keeps `journal_cursor` (last
processed ID_ZURNAL) in a local state file and maps tables to entities:

| ZURNAL.TABULKA | entity |
|---|---|
| PARTNER | owners (+ contacts are always full) |
| PACIENT | patients |
| VAKCINACE_ODCERVENI | vaccinations |
| DENNI_ZAZNAM | visits |
| DOKLAD | sale_documents |
| DOKLAD_POLOZKA | sale_lines (id looked up in DOKLAD_POLOZKA_UM; ids not found there are ignored, except D) |
| PLATBA | payments |
| VARIANTA | items |

Changed ids are re-read and pushed (`mode=incremental`); `D` ids go to `deleted`. Without a cursor
(first run) the bridge does a full run and sets the cursor to `max(ID_ZURNAL)` read at its start.
`users` and `contacts` are pushed in full on every run (small).

## Clarifications (binding, agreed after both sides were built)

1. `status.blocked` contains **entity names** (e.g. `["sale_documents", "sale_lines", "payments"]`), not
   fingerprint group names; changed groups are described in `status.message`.
2. `status.journal_cursor` = cursor at the start of the run, `null` on the first run (Odoo stores 0).
3. `deleted` ids for `sale_lines` may contain ids Odoo never stored (all DOKLAD_POLOZKA_* tables share
   one id sequence). Odoo ignores unknown deleted ids silently (not counted, never an error).
4. An id is never in both `records` and `deleted` within one push.
5. Foreign keys 0/negative are sent as `null` (owner_id, item_id, document_id, parent_id, entered_by…).
   Some payments reference documents of types that are not synced → the link stays empty.
6. Code values: classification `"other"` for unknown codes; contact type `"other"` for unknown; owner
   `kind` may be `null`; payment `method` = lower-cased code for unknown codes (Odoo: method `other`
   + raw code in `method_code`).
7. Flags are JSON booleans; `created` is a date (`YYYY-MM-DD`); `modified` is `YYYY-MM-DD HH:MM:SS`.
8. Bad dates pass through as-is (e.g. `"0218-10-25"`, typo years). Odoo stores every date/datetime with
   year < 1900 or > 2100 (or unparsable) as empty and notes the affected ids in the sync status
   (`last_error`); the record itself is stored.
9. `sale_lines.amount` = raw CENA (already the final price).
10. `deleted` ids are batched like records (≤ 500 per batch). A full push of an empty entity still sends
    one empty batch (`batch=1, batches=1`) so reconciliation runs. Incremental entities with no changes
    are not pushed at all. `users` and `contacts` are pushed with `mode=full` on every run.
11. Request body is `{"jsonrpc": "2.0", "method": "call", "params": {...}, "id": n}` (standard Odoo
    `type="json"`); `ok: false` or a JSON-RPC error stops the bridge run.
12. Real dataset sizes: users 11, items 715, owners 648, contacts 1192, patients 759, vaccinations 114,
    visits 968, sale_documents 1692, sale_lines 5356, payments 846. Measured in Odoo (Docker, synthetic
    data of these sizes): first full run ≈ 52 s in total, slowest 500-record batch ≈ 5.4 s; an unchanged
    repeated full run ≈ 7.5 s, slowest batch ≈ 0.5 s.

### Odoo-side notes (do not change the payloads)

- Database selection: the routes are `auth="none"`; Odoo picks the database from `dbfilter` / the only
  database on the server. With several databases, run the bridge against an Odoo whose `dbfilter`
  resolves to exactly one database for the bridge's host name.
- Full-mode reconciliation runs only when all batches `1..batches` of the `run_id` arrived; otherwise it
  is skipped and noted in the sync status.
- `ok: false` answers besides `unauthorized`: `"unknown entity"`, `"unknown mode"`, `"server error"`
  (the whole push call is rolled back; details in the Odoo log and the sync status).
- A patient whose owner is unknown is stored with the archived placeholder owner "WinVet – neznámý
  majitel" (the Odoo pet model requires an owner) and relinked automatically when the owner arrives.


## v2 additions (phase 1 – patient card, 2026-10-15)

Bridge version 2.0.0. All additions are new keys or new entities; v1 receivers ignore nothing
mandatory. Push order v2: `users, items, owners, contacts, patients, vaccinations, visits, vitals,
sale_documents, sale_lines, payments, bundles, bundle_lines, phrases`.

**Forward compatibility:** if Odoo answers a push with `{"ok": false, "error": "unknown entity"}`,
the bridge logs a warning, skips that entity for the run (does not stop, does not count it as a
failure, keeps it out of `pending_full`) and continues. This lets a bridge v2 talk to an Odoo
without the clinic module.

### items (+3 keys)
`price` (VARIANTA_CENIK.CENA_S_DPH of the price list ID_CENIK = 1 "Ordinace", price incl. VAT per
sales unit), `price_untaxed` (VARIANTA_CENIK.CENA, same row), `vat_rate` (VARIANTA.DPH_PRODEJ).
Null when the item has no row in price list 1. If several rows exist (per stock), the first by
ID_VARIANTA_CENIK.

### visits (+1 key)
`notes`: plain text of DENNI_ZAZNAM.DEKURS. DEKURS is a TRichView RVF document (WIN1250 text):
lines `<type> <count> …` start a record; for type `0` (text) the next `<count>` lines are text
paragraphs; all other records (negative types: tables, controls, `TPF0` binary blobs) are skipped.
Paragraphs are joined with `\n`, runs of empty lines collapsed to one, trimmed. Null when empty.

### vitals  [DENNI_ZAZNAM_HODNOTA] – measurements during a visit (journaled table)
`id, visit_id (ID_DENNI_ZAZNAM), time (CAS "HH:MM:SS"), temperature (TEPLOTA), heart_rate (TEP),
respiratory_rate (DECH), weight (HMOTNOST), bp_systolic (TLAK_SYS), bp_diastolic (TLAK_DIA)`

### bundles  [SABLONA_VYKONU] – procedure templates (not journaled → always full)
`id, code (SABLONA_VYKONU), name (SABLONA_VYKONU_NAZEV), description (POPIS text)`

### bundle_lines  [SABLONA_VYKONU_POLOZKA] (not journaled → always full)
`id, bundle_id (ID_SABLONA_VYKONU), item_id (ID_VARIANTA), item_name (VARIANTA_NAZEV),
quantity (MNOZSTVI), unit (MERNA_JEDNOTKA), sequence (PORADI)`

### phrases  [FRAZE] – text templates (journaled table FRAZE → incremental)
`id, name (FRAZE), group (PREDEK), text (TEXT converted from RVF like visits.notes, plain TEXT
blobs passed through)`

### Journal mapping additions
| ZURNAL.TABULKA | entity |
|---|---|
| DENNI_ZAZNAM_HODNOTA | vitals |
| FRAZE | phrases |
| VARIANTA_CENIK | items (the changed price row's ID_VARIANTA is re-read; `D` of a price row re-reads the item, never deletes it) |

`bundles` and `bundle_lines` are added to the always-full set (with users, contacts).

### Odoo side
- `elite_vet_winvet` handles `items` prices, `visits.notes`, `vitals`.
- `elite_vet_clinic` (phase 1) handles `bundles`, `bundle_lines`, `phrases` by extending the sync
  model; without it Odoo answers `unknown entity` for them (see forward compatibility).
- Owners/patients: synced fields are written only when the incoming `modified` differs from the
  stored `winvet_modified` (record changed in WinVet) or the record is new – edits made in Odoo
  survive until WinVet changes the same record. Full reconciliation (archiving missing ids) is
  unchanged.

### v2 clarifications (bridge side, binding)

1. `status.fingerprints` has a new group `templates` (SABLONA_VYKONU, SABLONA_VYKONU_POLOZKA,
   FRAZE); `DENNI_ZAZNAM_HODNOTA` belongs to `clinical`, `VARIANTA_CENIK` to `catalog`. A change of
   `clinical` therefore blocks `visits, vitals, sale_lines`; of `templates` `bundles, bundle_lines,
   phrases`. `status.blocked` stays a list of entity names.
2. `items.price` / `price_untaxed` come from the row of price list `ID_CENIK = 1` with the lowest
   `ID_VARIANTA_CENIK`; both are `null` when the item has no such row (30 of 715 items on the
   analysis copy). `vat_rate` (DPH_PRODEJ, e.g. `21.0`, `12.0`) is independent and may be `null`.
   All three are JSON numbers (floats).
3. VARIANTA_CENIK journal rows: the item id is `ZURNAL.IDKEY` (the WinVet triggers write
   `KEYFIELD = 'ID_VARIANTA'`, `IDKEY = NEW/OLD.ID_VARIANTA`, also for `D`; verified on 100 % of the
   rows). Any action marks the item as changed (incremental re-read) unless the item itself is
   deleted in the same journal window – then it stays in `deleted`. A VARIANTA_CENIK row without
   IDKEY makes the bridge push `items` with `mode=full` in that run.
4. `visits.notes`: only text items (style ≥ 0, save type 0) are taken, at any nesting depth – the text
   of table cells (e.g. the "Čas / Hmotnost / Teplota" header table WinVet puts at the top) is part
   of the notes, in document order. Styled runs that continue a paragraph (ParaNo `-1` / option
   `rvioSameAsPrev`) are appended to the previous line without a line break. Control characters and
   bytes undefined in WIN1250 are removed, tabs become spaces, trailing spaces of every line are
   cut. Lines that look like binary (contain `TPF0`/RVF class names, or ≥ 10 % control characters)
   are dropped. Conversion failures give `null`, never an error. `notes` can be long (up to ~15 000
   characters on the analysis copy) – Odoo must store it as `Text`.
5. `phrases.text` and `bundles.description`: values starting with the RVF header (`-8 <n> <n>`) are
   converted like `visits.notes`, anything else is passed through as plain text (CRLF → `\n`,
   trimmed). `phrases.group` is the raw text of FRAZE.PREDEK (a group label, not an id) or `null`.
6. `vitals`: values are passed as stored (WinVet uses `null`, not `0`, for "not measured");
   `temperature` and `weight` are floats, `heart_rate`, `respiratory_rate`, `bp_systolic`,
   `bp_diastolic` integers; `visit_id` 0/negative → `null`. A vitals row may reference a visit that
   does not exist (1 orphan on the analysis copy) – keep it with an empty link.
7. `bundle_lines.item_id` 0/negative → `null`; `sequence` (PORADI) is often `null`.
8. Unknown entity: only the exact answer `{"ok": false, "error": "unknown entity"}` triggers the skip;
   the first refused batch ends that entity for the run (remaining batches are not sent), the
   journal cursor still advances. Journal changes of a skipped incremental entity (`phrases`) are
   therefore not replayed later – the next full run (daily) sends the complete entity. Every other
   `ok: false` still stops the run (v1 clarification 11).
9. Real dataset sizes v2 (analysis copy): items 715 (685 with price), visits 968 (922 with notes),
   vitals 365, bundles 12, bundle_lines 138, phrases 10.


## Contract v3 additions (phase 2 – sales and stock)

Bridge version 3.0.0. Two new entities, appended to the push order (v3): `users, items, owners,
contacts, patients, vaccinations, visits, vitals, sale_documents, sale_lines, payments, bundles,
bundle_lines, phrases, stock_lots, stock_totals`. Both are not journaled and always sent in full
(`mode=full`, full reconciliation of ids). **v2 receivers answer `{"ok": false, "error": "unknown
entity"}` -> the bridge skips the entity** (see v2 forward compatibility); nothing else changes.

### stock_lots  [DOKLAD_POLOZKA_SK, DOKLAD] – stock layers (one per receipt line)
One record for every line with `ZNAMENKO = 1` (all receipt lines of any document type, also the
fully issued ones and lines whose document has no type; Odoo ignores `quantity` 0).
`id` (ID_DOKLAD_POLOZKA of the receipt line), `item_id` (ID_VARIANTA, 0/negative -> `null`),
`lot` (trimmed VYROBNI_CISLO, empty -> `null`), `expiry` (DATUM_EXPIRACE, `YYYY-MM-DD` or `null`),
`received` (DATUM_DOKLADU of the receipt document, `YYYY-MM-DD` or `null`), `quantity` (float:
MNOZSTVI minus the sum of MNOZSTVI of lines with `ZNAMENKO = -1` and
`ID_DOKLAD_POLOZKA_PRIJEM = id`), `unit_cost` (CENA_MJ or `null`), `vat_rate` (SAZBA_DPH, e.g. `21.0`,
or `null`), `cost_includes_vat` (bool, S_DPH = 'A': `unit_cost` includes VAT), `supplier`
(DOKLAD.PARTNER_NAZEV or `null`).

### stock_totals  [VARIANTA_SKLAD_STAV] – current stock per item
`id` (ID_VARIANTA_SKLAD_STAV), `item_id` (ID_VARIANTA), `total` (float, STAV_CELKEM).
On the analysis copy the sum of `stock_lots.quantity` per item equals `total` for 493 of 498 items.

### Guard
New fingerprint group `stock` (DOKLAD_POLOZKA_SK, VARIANTA_SKLAD_STAV). `stock_lots` also reads
DOKLAD (column PARTNER_NAZEV), so a change of `sales` blocks it as well; adding the column to the
used set changed the `sales` fingerprint once (re-approved with v3).

Sizes v3 (analysis copy): stock_lots 836, stock_totals 498.


## Contract v4 additions (WinVet calendar → Odoo board, 2026-10-25)

Bridge version 4.0.0. Three new entities, appended to the push order (v4): `…, stock_lots,
stock_totals, calendar_resources, calendar_activities, calendar_events`. None is journaled
(KALENDAR_NEW is not in ZURNAL), all are always sent with `mode=full`. One-way only: the bridge
never writes to WinVet; Odoo keeps the calendar read-only. **v3 receivers answer `{"ok": false,
"error": "unknown entity"}` → the bridge skips the entity** (v2 forward compatibility); nothing else
changes. There is no other version negotiation: `status.bridge_version` is informative only.

### calendar_resources  [KALENDAR_NEW_KALENDAR] – the columns (calendars) of the WinVet scheduler
`id` (ID_KALENDAR_NEW_KALENDAR), `name` (KALENDAR_NAZEV), `color` (BARVA, Delphi TColor →
`"#rrggbb"`, system colours → `null`), `visible` (ZOBRAZIT='A'), `work_from` / `work_to`
(PRACOVNI_DOBA_OD/DO, `"HH:MM:SS"` or `null`), `sequence` (PORADI). Full reconciliation like v1
master data (Odoo archives missing ids).

### calendar_activities  [ORD_CINNOST] – activity types
`id` (ID_ORD_CINNOST), `name` (ORD_CINNOST_NAZEV), `duration` (DOBA, minutes), `color` (BARVA, as
above), `symbol` (SYMBOL or `null`), `web` (USE_WEB='A'). Full reconciliation like master data.

### calendar_events  [KALENDAR_NEW] – one record per occurrence inside a window
Push payload has one extra key, the same in every batch of the run:
`"window": {"from": "YYYY-MM-DD", "to": "YYYY-MM-DD"}` (both days inclusive, local days).
Default window = yesterday … today + 60 days (`[bridge] calendar_days_back` / `calendar_days_ahead`).

Record keys:
`key` (string, the identity: `"<ID_KALENDAR>"` for a plain event, `"<pattern ID_KALENDAR>-<YYYYMMDD>"`
for an occurrence of a recurring event, the date being the occurrence's original date),
`id` (ID_KALENDAR of the row the data comes from: the event, the pattern, or the changed occurrence),
`pattern_id` (ID_KALENDAR of the recurrence pattern or `null`), `recurring` (bool),
`occurrence_date` (`YYYY-MM-DD` original date of the occurrence or `null`),
`start`, `end` (`YYYY-MM-DD HH:MM:SS` Europe/Prague local time like every contract datetime; `end` is
exclusive), `all_day` (bool, VOLBY bit 0; then `start`/`end` are local midnights, `end` = the day after
the last day), `resource_ids` (list of `calendar_resources` ids, possibly empty or several),
`activity_id` (ID_ORD_CINNOST), `owner_id` (ID_PARTNER), `patient_id` (ID_PACIENT) – ids 0/negative →
`null` –, `title` (TITULEK, **personal data: client names**), `busy_status` (STAV, int: 0 free,
2 busy …), `done` (VYRIZENO='A'), `modified` (POSLEDNI_MODIFIKACE_TS, `YYYY-MM-DD HH:MM:SS`).
ZPRAVA (notes), reminders and Google ids are never read.

Rules (bridge side):

1. Rows: TYP 0 plain event, TYP 1 recurrence pattern, TYP 3 changed occurrence, TYP 4 deleted
   occurrence (TYP 3/4 point to the pattern with ID_PREDEK and to the occurrence with
   OPAKOVANI_INDEX, 0 = the first one – the same matching DevExpress uses). A record is sent when it
   overlaps the window (`start < to + 1 day` and `end > from`).
2. Recurrence (OPAKOVANI_INFO, DevExpress `TcxSchedulerEventRecurrenceInfoData`, 40 bytes, layout in
   `winvet_bridge/scheduler.py`): daily (every n days / every weekday), weekly (days bit 0 Sunday …
   bit 6 Saturday, every n weeks, weeks start on Monday), monthly and yearly (day of month or n-th
   [last] weekday). End: Count > 0 occurrences, Count = 0 until Finish (inclusive day), Count = -1
   none. A changed occurrence replaces its occurrence (own time, resources, texts); a deleted one
   removes it. Occurrence time = the pattern's time of day and duration.
3. Resources (ZDROJ_INFO): a streamed Delphi variant (one value or a list) of wide strings; numeric
   strings are resource ids, other strings resource **names** (resolved case-insensitively against
   KALENDAR_NEW_KALENDAR). Layout in `scheduler.py`. Undecodable → `resource_ids: []`.
4. All-day events are stored by WinVet from 23:00 of the previous day to 23:00 of the last day; they
   are rounded to the nearest local midnight. Recurrences of all-day events are expanded on these real
   days (checked on the analysis copy: all 15 deleted occurrences match the date of their index).
5. Problems (undecodable recurrence, occurrence without pattern, event without time) are counted in
   the log (counts only) and never stop the run.

Rules (Odoo side):

1. Upsert by `key`. The last batch (`batch == batches`, all batches of the `run_id` present) deletes
   the stored events overlapping the window whose key was not in any batch of the run. Events outside
   the window are never touched.
2. `owner_id` / `patient_id` are matched with the owners / patients of the kartotéka sync
   (`res.partner.winvet_ref`, `elite.vet.pet.winvet_ref`); unmatched → title only.
3. Switch "Kalendář z WinVetu" off: pushes are answered `ok: true` with every record `skipped` and
   nothing stored (the bridge keeps sending; switch it on again or remove the calendar from the
   bridge later).

### `sync --only calendar`
`py -m winvet_bridge sync --only calendar` reads and pushes just the three calendar entities
(no change journal, the cursor and the daily full run stay as they are). A status is sent first as in
every run. Service mode (`run`) does this itself every `calendar_interval_minutes` (default 5, 0 = off)
between the normal runs; the normal and the full run always include the calendar too.

### Guard
New fingerprint group `calendar` (KALENDAR_NEW, KALENDAR_NEW_KALENDAR, ORD_CINNOST); a change blocks
only the three calendar entities. A bridge v4 with a `verified.json` that has no `calendar` group
blocks the calendar until `approve` (verified for 2603 on the analysis copy: `df31de3832520240`).

Sizes v4 (analysis copy, data until 16. 11. 2026): calendar_resources 4, calendar_activities 44,
calendar_events 203 in the default window from 24. 10. (1091 for 26. 8. – 24. 11.; KALENDAR_NEW has
1005 rows: 964 plain, 12 patterns, 14 changed, 15 deleted occurrences).
