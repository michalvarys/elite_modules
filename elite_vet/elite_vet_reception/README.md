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

## Testy

```bash
docker compose stop odoo
bash elite_vet/nasazeni/testy-reception.sh "" update   # první běh bez "" update (instalace)
docker compose start odoo
```
