# Recepce (elite_vet_reception)

Odoo 18 modul: pracoviště recepce v pokladně Odoo „Recepce“ a stavy návštěvy
(spec: `docs/superpowers/specs/2026-10-22-reception-workplaces-design.md`).
Závisí na `elite_vet_sale` a `pos_hr`. Ostatní moduly se neupravují, jen rozšiřují (`_inherit`).

## Stavy návštěvy

Na `elite.vet.clinical.record` přibývá:

| Pole | Význam |
|---|---|
| `visit_stage` | `waiting` (Čeká) / `in_room` (V ordinaci); prázdné = záznam vznikl mimo recepci |
| `arrived_at` | čas příchodu (přijetí recepcí) |
| `called_at` | čas zavolání do ordinace |
| `received_by` | jméno zaměstnance pokladny (pos_hr), který klienta přijal – volitelné |

Otevření dnešního záznamu z karty pacienta (`open_today_record`) sestrou nebo lékařkou posune
rozepsaný záznam ve stavu Čeká (nebo bez stavu) do V ordinaci a zapíše `called_at`.

## API `elite.vet.reception` (abstraktní)

Volání `orm.call("elite.vet.reception", "<metoda>", [args])`. Každá metoda nejdřív ověří skupinu
Recepce (sestra, lékařka a vedení ji mají přes nadřazené skupiny) a teprve potom pracuje se
záznamy pod sudo – recepce sama do záznamu psát nesmí. Den a časy jsou v čase kliniky
(Europe/Prague).

| Metoda | Vrací |
|---|---|
| `today_data(day=None)` | `{"date", "arriving": [...], "waiting": [...], "to_pay": [...], "paid_count"}` |
| `check_in(reservation_id, employee_name=None)` | záznam (`record_id`, `stage`, …) |
| `walk_in(pet_id, doctor_id=False, employee_name=None)` | záznam |
| `call_patient(record_id)` | záznam; jen sestra a lékařka |

- **arriving** – potvrzené rezervace dne (bez druhých ordinací) bez nezrušeného záznamu, podle času:
  `reservation_id, time, pet_id|None, pet_name, owner, partner_id, procedure, doctor, room, needs_match`
  (`needs_match` = webová rezervace bez spárovaného zvířete).
- **waiting** – rozepsané záznamy dne se stavem návštěvy, podle příchodu:
  `record_id, pet_name, owner, doctor, room, stage, stage_label, arrived_time, waiting_minutes`
  (u V ordinaci minuty od příchodu do zavolání).
- **to_pay** – všechny nezaplacené účty návštěv (Čeká na platbu / Částečně zaplaceno) bez ohledu
  na den, nejstarší první:
  `record_id, sale_order_id, pet_name, owner, partner_id, amount, payment_state, payment_state_label,
  date, date_label` (`amount` = zbývá zaplatit, `date_label` = „dnes“ nebo „D. M.“).
- **paid_count** – počet dnes zaplacených záznamů.
- Záznam (`check_in` / `walk_in` / `call_patient`): `record_id, stage, stage_label, state, pet_id,
  pet_name, reservation_id, doctor, arrived_time, received_by`.

Pravidla přijetí:

- Přijmout jde jen rezervaci na dnešek (den kliniky): „Rezervace není na dnešek – přijmout jde jen
  dnešní návštěvu.“
- Souběžné přijetí ze dvou pokladen: druhé narazí na unikátnost rezervace a vrátí už založený záznam.
- Rezervace, která už záznam má (lékařka otevřela kartu dřív), vrátí tento záznam; nový nevznikne
  a stav V ordinaci zůstane.
- Webová rezervace bez zvířete skončí chybou „Rezervace z webu ještě není spárovaná s klientem
  a zvířetem – otevřete Kartotéku.“
- Nový záznam dostane lékařku z rezervace (u `walk_in` zadanou lékařku), stav Čeká, `arrived_at`
  a `received_by`.
- `walk_in` použije dnešní rozepsaný záznam zvířete, jinak založí nový (i když už dnes jeden
  uzavřený má).
- Každá změna pošle zprávu na tabuli (`notify_board`, kanál `elite_vet_reservation/changed`).

## Kartotéka (majitelé a zvířata)

Stejné API `elite.vet.reception`, stejná kontrola role. Majitele a zvířata recepce zakládá
a upravuje vlastními právy (bez sudo); pod sudo se čtou jen účty návštěv.

| Metoda | Vrací |
|---|---|
| `card_search(term)` | seznam: zvířata (`kind: "pet"`, tvar `search_patients` karty pacienta – jméno, majitel, čip, číslice telefonu) a majitelé (`kind: "owner"`: `id, partner_id, name, owner, phone, email, pet_count`) podle jména / telefonu / e-mailu, které žádné nalezené zvíře neukazuje (např. bez zvířat); méně než 2 znaky = `[]` |
| `owner_data(partner_id)` | `{"owner": {id, name, phone, mobile, email, street, city, zip}, "pets": [...], "open_bills": [...]}` |
| `save_owner(vals, partner_id=None)` | `owner_data`; klíče `name, phone, mobile, email, street, city, zip` (jiné se ignorují), jméno povinné; nový majitel má `is_vet_client` |
| `save_pet(partner_id, vals, pet_id=None)` | `owner_data`; klíče `name, species, breed, sex, birth_date, chip, note`; jméno a druh povinné, zvíře musí patřit majiteli |
| `match_reservation(reservation_id, partner_id, pet_id)` | `{reservation_id, time, partner_id, owner, pet_id, pet_name, needs_match}` – webová rezervace dostane majitele a zvíře (i její druhá ordinace), pak jde přijmout |

- **pets** – všechna aktivní zvířata majitele (uhynulá na konci): `id, name, species, species_label, breed,
  sex, birth_date, chip, alerts, next_vaccination, deceased` (`alerts` = souhrn upozornění,
  `next_vaccination` = příští vakcinace z WinVetu).
- **open_bills** – nezaplacené účty majitele, stejný tvar jako `to_pay` (`record_id, amount,
  payment_state_label, …`).
- Stejný telefon nebo e-mail jako jiný majitel nevadí: uloží se, nic se neslučuje.
- Majitel nesmí být kontakt uživatele (personál) ani firmy: „Tento kontakt není klient kliniky.“
  Úprava existujícího kontaktu mu `is_vet_client` nepřidá (jen nový majitel ho dostane).
- Hodnoty formuláře se berou jako text (ořezaný); jiná data skončí chybou.
- `match_reservation` u druhé ordinace páruje hlavní rezervaci; rezervace, která už má návštěvu
  jiného zvířete, skončí chybou „Rezervace už má návštěvu jiného zvířete.“

## Objednání (záložka Objednat)

Stejné API `elite.vet.reception`, stejná kontrola role. Volné časy i uložení jdou přes průvodce
rezervací (`elite.vet.reservation.wizard`, s právy volajícího) – stejný výpočet jako tabule.
Den je `"YYYY-MM-DD"` v čase kliniky, `minute` = minuty od půlnoci.

| Metoda | Vrací |
|---|---|
| `booking_options()` | `{"procedures": [{id, name, duration}], "doctors": [{id, name}]}` (lékařky přijímající objednávky) |
| `free_slots(procedure_id, day, doctor_id=False)` | `{"day", "slots": [{time, minute, room_id, room, doctor_id, doctor}], "next_free_day"}` – řádky průvodce (čas × ordinace); `next_free_day` = nejbližší další den s volným časem v horizontu recepce, jinak `None` |
| `book(pet_id, procedure_id, day, minute, room_id, doctor_id=False, note=None)` | `{reservation_id, label}` – potvrzená rezervace pro zvíře a jeho majitele (kontakt z majitele), lékařka ve službě; potvrzovací e-mail jako v průvodci (když má majitel e-mail) |

- Před uložením se znovu ověří, že je čas volný; obsazený čas (i když ho odmítne až kontrola
  překryvu při uložení) skončí chybou „Termín 9:00 už mezitím někdo obsadil – vyberte jiný.“

## Role, výchozí obrazovky a menu

| Role | Výchozí obrazovka (`res.users.action_id`) | Menu |
|---|---|---|
| Recepce | `action_open_reception_pos` – pokladna Recepce (`/pos/ui?config_id=…`, stejné okno) | Pokladna, Rezervace, Diskuze |
| Sestra, Lékařka | Karta pacienta (`elite_vet_clinic.action_patient_card`) | + Ordinace, Sklad jen s Přehledem skladu a Příjmem zboží |
| Vedení | Přehled tržeb a výdajů (`elite_vet_winvet.action_winvet_dashboard`) | vše |

- Výchozí obrazovka se nastaví při založení uživatele a při každé změně jeho skupin – jen když
  nemá žádnou nebo má některou z rolových; vlastní jinou výchozí obrazovku nikdy nepřepíše.
- Uživatelé › Akce › **Nastavit výchozí obrazovky** (jen vedení) totéž provede pro všechny
  interní uživatele (`res.users.action_elite_vet_set_home_actions`), vlastní obrazovky zůstanou.
  Stejně se to provede při každé aktualizaci modulu (`_elite_vet_apply_home_actions_all`).
- Změna členů přímo ve formuláři skupiny (Nastavení › Skupiny) výchozí obrazovku nemění – potom
  klikněte na „Nastavit výchozí obrazovky“.
- URL pokladny se počítá z id pokladny Recepce (v každé databázi jiné): při instalaci, při každé
  aktualizaci modulu a v `elite.vet.sale.setup.ensure_setup()`.
- Menu (`ir.ui.menu._elite_vet_apply_role_menus`, `data/menus.xml`, běží při každé aktualizaci):
  Prodej, Fakturace, Zaměstnanci, WinVet data, Rozpis služeb, Web, Přehledy (Dashboards)
  a Aplikace jen vedení; Ordinace od sestry; Pokladna od recepce; Diskuze všem;
  ve Skladu zůstanou sestře a lékařce jen Přehled skladu a Příjem zboží (přesunutý z Operací přímo
  pod Sklad hned za Přehled skladu), ostatní položky, které by viděla, jsou jen pro vedení. Obě položky jsou i v Ordinaci.
  Menu patří jiným modulům: samostatná aktualizace takového modulu vrátí jeho skupiny, další
  aktualizace `elite_vet_reception` je zase nastaví.
- Účetní, která má vidět Fakturaci, potřebuje skupinu Vedení (menu Fakturace je jen pro vedení).
- Vedení dostává skupiny Zaměstnanci: uživatel (`hr.group_hr_user`, zakládá zaměstnance pokladny)
  a Správce rozpisu.

## Obsluha PINem (pos_hr)

Pokladna Recepce má zapnuté přihlášení zaměstnanců (`module_pos_hr`). Zapne se při instalaci
a aktualizaci modulu, jen když pokladna nemá otevřenou relaci (Odoo změnu za otevřené relace
nedovolí) – jinak se zapíše varování do logu: zavřete pokladnu a aktualizujte modul znovu.

Zaměstnance s PINem zakládá **vedení** v aplikaci Zaměstnanci (jméno, PIN, případně propojený
uživatel); modul žádné zaměstnance nezakládá. Bez vybraných zaměstnanců v nastavení pokladny se
mohou přihlásit všichni zaměstnanci firmy.

## Testy

```bash
docker compose stop odoo
bash elite_vet/nasazeni/testy-reception.sh "" update   # první běh bez "" update (instalace)
docker compose start odoo
```
