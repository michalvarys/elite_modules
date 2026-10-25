# Ordinace (elite_vet_clinic)

Odoo 18 modul, fáze 1 náhrady WinVetu: karta pacienta a záznam návštěvy
(spec: `docs/superpowers/specs/2026-10-15-phase1-patient-card-design.md`).
Závisí na `elite_vet_winvet` (a přes něj na rezervacích a rozpisu lékařů).

## Co modul přidává

| Model | Popis |
|---|---|
| `elite.vet.pet.alert` | Upozornění na pacientovi: druh `bites` Kouše / `allergy` Alergie / `other` Jiné, poznámka, aktivní. Na mazlíčkovi `alert_ids` a počítané `alert_summary` („Kouše; Alergie: penicilin“). |
| `elite.vet.clinical.record` | Záznam návštěvy: pacient, majitel (related, uložený), lékařka, zapsal(a), rezervace (max. jeden záznam na rezervaci), čas `start`, den `date` (čas kliniky Europe/Prague), stav `draft` Rozepsaný / `done` Hotovo – k pokladně / `cancelled` Zrušeno (sledovaný v chatteru), teplota, váha, tep, dech, anamnéza, vyšetření, diagnóza a doporučení (čistý text), položky účtu, `amount_total` (CZK), interní `reception_note` Poznámka recepce (píše recepce při příjmu, sledovaná; klient ji nikde nevidí). Váha uzavřeného záznamu se zapíše do `pet.weight`. |
| `elite.vet.clinical.record.line` | Položka účtu: položka ceníku (`elite.vet.winvet.item`), název, druh (podle položky, volná položka „Jiné“), množství, jednotka, cena za jednotku (výchozí = cena s DPH z ceníku), částka, `bundle_id` když přišla z balíčku. |
| `elite.vet.text.template` | Šablona textu: název, oddíl (anamnéza / vyšetření / diagnóza / kterýkoli), text, pořadí, `group_name` (skupina z WinVetu), `winvet_ref`, `edited_in_odoo`. |
| `elite.vet.procedure.bundle` (+ `.line`) | Balíček výkonů: název, kód, popis, položky (položka ceníku, název, množství, jednotka, pořadí), `winvet_ref`, `edited_in_odoo`; počítaný počet položek a cena podle ceníku. |

Menu **Ordinace**: Karta pacienta (klientská akce `elite_vet_clinic.action_patient_card`, tag
`elite_vet_clinic.patient_card`) · Záznamy návštěv · Upozornění na pacientech · Konfigurace →
Šablony textů, Balíčky výkonů, Sloučit duplicitní klienty (jen správce).

Tlačítko **Karta pacienta**: formulář mazlíčka (záhlaví), klienta (chytré tlačítko; jeden
mazlíček → rovnou karta, víc → seznam mazlíčků s tlačítkem u každého), rezervace (záhlaví;
webová rezervace bez mazlíčka se nejdřív spáruje s klientem a mazlíčkem) a záznamu návštěvy.
Všechna vrací klientskou akci s `params = {pet_id, reservation_id}`.

## Role

Skupiny v kategorii *Rezervace* tvoří jednu řadu: **Recepce < Sestra < Lékařka < Správce
rezervací** (správce implikuje Lékařku – doplněno tímto modulem).

| | Recepce | Sestra | Lékařka | Správce |
|---|---|---|---|---|
| záznamy návštěv, upozornění | číst | číst, zapisovat, zakládat | jako sestra | vše |
| položky účtu | číst | vše (i mazat – úprava účtu) | vše | vše |
| šablony textů, balíčky | číst | číst | číst, zapisovat, zakládat | vše |
| znovu otevřít uzavřený záznam | – | – | ano | ano |
| sloučit duplicitní klienty | – | – | – | ano |

Lékařky v Odoo (`elite.vet.doctor`) nemají vazbu na uživatele; lékařka přihlášeného uživatele
se hledá podle jména (tituly, velikost písmen, diakritika a pořadí slov se ignorují, stejně jako
párování uživatelů WinVetu). Skupiny se uživatelům automaticky nepřidělují – nastaví je správce.

**Sloučení duplicitních klientů** = standardní průvodce Odoo `base.partner.merge.automatic.wizard`
(modul `base`). Správce rezervací bez práva „Vytváření kontaktů“ slučuje jako superuživatel
(sloučení sahá i do cizích aplikací – návštěvníci webu, zprávy…); zůstává limit 3 kontaktů
najednou, kontrola stejného e-mailu se jako u administrátora přeskakuje. ID z WinVetu se při
sloučení zachová (viz README `elite_vet_winvet`).

## Synchronizace z WinVetu (smlouva v2)

Modul rozšiřuje `elite.vet.winvet.sync` o entity `bundles`, `bundle_lines`, `phrases`
(bez tohoto modulu je Odoo odmítne jako `unknown entity` a most je přeskočí).

- Párování podle `winvet_ref`, zapisují se jen změny.
- Balíček nebo šablona upravená v Odoo (`edited_in_odoo` – změna názvu/textu šablony; názvu,
  kódu, popisu nebo položek balíčku) se už nikdy nepřepisuje, nearchivuje a položky takového
  balíčku most nemění, nepřidává ani nemaže.
- Smazané ve WinVetu (nebo chybějící v plném běhu): balíčky a šablony se archivují, položky
  balíčků mažou.
- `phrases`: `name` → název, `text` → text (bez textu = název), `group` → `group_name`; oddíl
  je při založení „Kterýkoli“ a dál ho určuje Odoo (most ho nemění).
- Šablony a balíčky založené v Odoo nemají `winvet_ref` a most je nevidí.

## API karty pacienta

Všechny metody jsou na modelu `elite.vet.clinical.record` a volají se z OWL přes
`this.orm.call("elite.vet.clinical.record", "<metoda>", [args...])`. Běží s právy volajícího
(žádné sudo): recepce smí jen čtecí metody, zapisovací vrací `AccessError`. Chyby pro uživatele
jsou `UserError` s českou zprávou. Vrací se jen JSON (čísla, řetězce, `null`).

Konvence: datum `"YYYY-MM-DD"`; `start` = UTC `"YYYY-MM-DD HH:MM:SS"`; `time` = místní čas
kliniky `"HH:MM"`; prázdná měření (0) jsou `null`; texty záznamu jsou `""`, když jsou prázdné.

### Čtení

**`card_data(pet_id)`** → celá karta:
```text
{
  header: {
    pet: {id, name, species, species_label, breed, sex, color, birth_date, age_text ("7 let",
          "1 rok", "3 roky", "5 měsíců", "2 týdny", "cca 4 roky"), chip, tattoo, passport, deceased, active,
          important_note, note, winvet_note, next_vaccination,
          weight, weight_delta (vs. předchozí měření, null když není), weight_date (poslední měření)},
    owner: {partner_id, name, phone, mobile, email, street, city},
    alerts: [{id, kind ("bites"|"allergy"|"other"), kind_label, note, label}]
  },
  timeline: [ ...nejnovější první, řazeno podle (date, time)... ],
  today_record: RECORD | null,          // dnešní rozepsaný, jinak dnešní uzavřený; nic se nezakládá
  templates: {anamnesis: [TPL], examination: [TPL], diagnosis: [TPL], any: [TPL]},
  bundles: [{id, code, name, description, line_count, amount}],
  doctors: [{id, name}],
  permissions: {can_write, can_edit_templates, is_manager},
  today: "YYYY-MM-DD"
}
TPL = {id, name, body, section, group_name}
```
Položky `timeline` (pole `type`):
```text
record:      {type, id, date, time, doctor, diagnosis (1. řádek), summary (zkrácený text),
              anamnesis, examination, diagnosis_text, state, state_label, vitals_summary, items [názvy], amount_total}
visit:       {type, id, date, time, doctor (lékařka nebo kdo zapsal ve WinVetu), diagnosis, case_name,
              notes (dekurz), vitals: [{time, temperature, heart_rate, respiratory_rate, weight,
              bp_systolic, bp_diastolic, summary}], vitals_summary}
vaccination: {type, id, date, time: null, item, next_date}
```
Zrušené záznamy z Odoo se v ose nezobrazují. Váha pro `weight_delta` se bere ze záznamů
v Odoo (kromě zrušených) a z vitálních hodnot WinVetu.

**`get_record(record_id)`** → `RECORD`:
```text
{id, name, pet_id, partner_id, doctor_id, doctor_name, user_name, reservation_id, start, date, time,
 state ("draft"|"done"|"cancelled"), state_label, temperature, weight, heart_rate, respiratory_rate,
 anamnesis, examination, diagnosis, reception_note (poznámka recepce | null),
 lines: [LINE], amount_total, currency ("Kč"), editable (rozepsaný a uživatel smí zapisovat)}
LINE = {id, sequence, item_id, code, name, kind ("service"|"product"|"other"), kind_label, quantity, unit,
        price_unit, amount, bundle_id, bundle_name}
```

**`search_items(term, kind=None, limit=20)`** → `[{id, code, name, kind, kind_label, unit, price,
stock_tracked}]` – aktivní položky ceníku (bez skupin), `term` v názvu nebo kódu (ilike) nebo
přesný čárový kód; `kind` = `"service"` (+ Úkon) / `"product"` (+ Lék ze skladu). Prázdný `term`
vrátí prvních `limit` podle názvu.

**`search_patients(term, limit=20)`** → `[{id, name, species, species_label, breed, owner,
partner_id, phone, chip, last_visit, deceased, alerts}]` – jméno zvířete, jméno majitele, čip;
číselný výraz (≥ 4 číslice) navíc v telefonu/mobilu majitele a čipu porovnaný jen po číslicích
(stejně jako `normalize_phone` v `elite_vet_reservation`). Kratší výraz než 2 znaky → `[]`.

**`my_patients_today()`** → `{date, doctor: {id, name}|null, filtered_by_doctor, items: [...]}`;
položky: `{reservation_id, start, time, time_end, room, room_color, doctor, pet_id (null u webové
rezervace bez spárovaného mazlíčka), pet_name, species_label, owner, partner_id, phone, procedure,
problem, state, state_label, record_id, record_state, alerts, reception_note}`. Dnešní rezervace (potvrzené
a proběhlé) lékařky přihlášeného uživatele; když se uživatel s žádnou lékařkou nespáruje, všechny
dnešní rezervace.

### Zápis (sestra, lékařka, správce)

Všechny zápisy kromě `open_today_record` a `reopen_record` vyžadují rozepsaný záznam
(uzavřený → `UserError`). Kromě `apply_template` vrací aktuální `RECORD`.

| Metoda | Co dělá |
|---|---|
| `open_today_record(pet_id, reservation_id=False, force_new=False)` | Záznam rezervace, pokud existuje; jinak dnešní rozepsaný záznam pacienta (u rezervace jen bez jiné rezervace; doplní se mu rezervace), jinak dnešní uzavřený; jinak nový rozepsaný. Lékařka z rezervace, jinak podle jména uživatele. `force_new=True` vždy založí nový (druhá návštěva týž den). Rezervace jiného pacienta → `UserError`. |
| `save_record(record_id, vals)` | Zapíše jen `temperature, weight, heart_rate, respiratory_rate, anamnesis, examination, diagnosis, doctor_id`; ostatní klíče se ignorují. Čísla smí být řetězce s čárkou („38,5“), `null`/`""` = prázdné. |
| `add_item(record_id, item_id, quantity=1)` | Přidá položku ceníku; stejná položka se sloučí (množství se sečte). |
| `add_free_line(record_id, name, price_unit=0, quantity=1, kind="other")` | Volná položka mimo ceník. |
| `add_bundle(record_id, bundle_id)` | Přidá všechny položky balíčku; položka, která už v účtu je, jen navýší množství. |
| `update_line(line_id, vals)` | Jen `quantity, price_unit, name, unit, kind, sequence`. |
| `remove_line(line_id)` | Smaže položku účtu. |
| `apply_template(record_id, template_id, section)` | `section` ∈ `anamnesis, examination, diagnosis`; připojí text šablony za stávající text oddělený prázdným řádkem, uloží a vrátí `{section, text}`. Před voláním uložte rozepsaný text (`save_record`), jinak se připojí k uložené verzi. |
| `mark_done(record_id)` | Stav „Hotovo – k pokladně“; váha záznamu se zapíše pacientovi. |
| `reopen_record(record_id)` | Jen lékařka/správce: uzavřený záznam zpět do rozepsaných. |

## Testy

`bash elite_vet/nasazeni/testy-clinic.sh` (poprvé, instalace), dál
`bash elite_vet/nasazeni/testy-clinic.sh "" update`. Před testy zastavte server
(`docker compose stop odoo`), po nich ho spusťte (`docker compose start odoo`).
