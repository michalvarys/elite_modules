# WinVet bridge ⇄ Odoo contract (v1)

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
