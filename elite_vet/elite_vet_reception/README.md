# Recepce (elite_vet_reception)

Odoo 18 modul: pracoviště recepce v pokladně Odoo „Recepce“ a stavy návštěvy
(spec: `docs/superpowers/specs/2026-10-22-reception-workplaces-design.md`).
Závisí na `elite_vet_sale` a `pos_hr`. Ostatní moduly se neupravují, jen rozšiřují (`_inherit`).

Návod pro recepci, lékařky a vedení: [doc/recepce-v-pokladne.md](doc/recepce-v-pokladne.md).

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
- Každá změna pošle zprávu na tabuli (`notify_board`, kanál `elite_vet_reservation/changed`);
  stejně i uzavření (Hotovo, k pokladně), znovuotevření a zrušení záznamu, takže sloupec
  K pokladně v pokladně se mění hned.

## Kartotéka (majitelé a zvířata)

Stejné API `elite.vet.reception`, stejná kontrola role. Majitele a zvířata recepce zakládá
a upravuje vlastními právy (bez sudo); pod sudo se čtou jen účty návštěv.

| Metoda | Vrací |
|---|---|
| `card_search(term)` | seznam: zvířata (`kind: "pet"`, tvar `search_patients` karty pacienta – jméno, majitel, čip, číslice telefonu) a majitelé (`kind: "owner"`: `id, partner_id, name, owner, phone, email, pet_count`) podle jména / telefonu / e-mailu, které žádné nalezené zvíře neukazuje (např. bez zvířat); méně než 2 znaky = `[]` |
| `owner_data(partner_id)` | `{"owner": {id, name, phone, mobile, email, street, city, zip}, "pets": [...], "open_bills": [...]}` |
| `save_owner(vals, partner_id=None)` | `owner_data`; klíče `name, phone, mobile, email, street, city, zip` (jiné se ignorují), jméno povinné; nový majitel má `is_vet_client` |
| `save_pet(partner_id, vals, pet_id=None)` | `owner_data`; klíče `name, species, breed, sex, birth_date, chip, note`; jméno a druh povinné, zvíře musí patřit majiteli |
| `pet_options()` | `{"species": [{value, label}]}` – druhy pro formulář zvířete |
| `match_reservation(reservation_id, partner_id, pet_id)` | `{reservation_id, time, partner_id, owner, pet_id, pet_name, needs_match}` – rezervace (webová i už spárovaná) dostane majitele a zvíře (i její druhá ordinace); webová pak jde přijmout |
| `reservations_to_assign(days=7)` | potvrzené a webové rezervace od dneška do `days` dní dopředu (bez druhých ordinací), podle začátku: `reservation_id, date, date_label, time, pet_id, pet_name, partner_id, owner, procedure, doctor, needs_match, has_record` (`date_label` = „dnes“, „zítra“ nebo „čt 29. 10.“; `has_record` = už má nezrušenou návštěvu) |

- **pets** – všechna aktivní zvířata majitele (uhynulá na konci): `id, name, species, species_label, breed,
  sex, birth_date, chip, note, alerts, next_vaccination, deceased` (`alerts` = souhrn upozornění,
  `next_vaccination` = příští vakcinace z WinVetu).
- **open_bills** – nezaplacené účty majitele, stejný tvar jako `to_pay` (`record_id, amount,
  payment_state_label, …`).
- Stejný telefon nebo e-mail jako jiný majitel nevadí: uloží se, nic se neslučuje.
- Majitel nesmí být kontakt uživatele (personál) ani firmy: „Tento kontakt není klient kliniky.“
  Úprava existujícího kontaktu mu `is_vet_client` nepřidá (jen nový majitel ho dostane).
- Hodnoty formuláře se berou jako text (ořezaný); jiná data skončí chybou.
- `match_reservation` u druhé ordinace páruje hlavní rezervaci; rezervace, která už má návštěvu
  jiného zvířete, skončí chybou „Rezervace už má návštěvu jiného zvířete.“ Rezervaci s jiným
  zvířetem, která ještě návštěvu nemá, přepíše (změna klienta). Zrušená rezervace: chyba.

## Objednání (záložka Objednat)

Stejné API `elite.vet.reception`, stejná kontrola role. Volné časy i uložení jdou přes průvodce
rezervací (`elite.vet.reservation.wizard`, s právy volajícího) – stejný výpočet jako tabule.
Den je `"YYYY-MM-DD"` v čase kliniky, `minute` = minuty od půlnoci.

| Metoda | Vrací |
|---|---|
| `booking_options()` | `{"procedures": [{id, name, duration}], "doctors": [{id, name}]}` (lékařky přijímající objednávky) |
| `free_slots(procedure_id, day, doctor_id=False)` | `{"day", "slots": [{time, minute, room_id, room, doctor_id, doctor}], "next_free_day"}` – řádky průvodce (čas × ordinace); `next_free_day` = nejbližší další den s volným časem v horizontu recepce, jinak `None` |
| `book(pet_id, procedure_id, day, minute, room_id, doctor_id=False, note=None)` | `{reservation_id, label}` – potvrzená rezervace pro zvíře a jeho majitele (kontakt z majitele), lékařka ve službě; potvrzovací e-mail jako v průvodci (když má majitel e-mail) |

- Uhynulé zvíře objednat ani přijmout bez objednání nejde: „Zvíře je vedené jako uhynulé.“
  Majitel musí projít pravidlem Kartotéky (ne personál, ne firma).
- `next_free_day` se hledá jen pro den bez volného času; den za horizontem recepce vrátí prázdný
  seznam bez výpočtu.
- Když se rezervace po uložení nenajde, `book` skončí chybou (nikdy nevrací `reservation_id` False).
- Před uložením se znovu ověří, že je čas volný; obsazený čas (i když ho odmítne až kontrola
  překryvu při uložení) skončí chybou „Termín 9:00 už mezitím někdo obsadil – vyberte jiný.“

## Pokladna Recepce (frontend)

Soubory `static/src/pos/` (bundle `point_of_sale._assets_pos`). Jen v pokladně Recepce
(`pos.config.is_elite_vet_reception`, počítané z `elite_vet_sale.pos_config_reception`); ostatní
pokladny zůstávají standardní.

- **Lišta** (jediný patch navbaru, `navbar_patch/`): Dnes, Kartotéka…, Objednat, Pokladna
  (standardní obrazovka produktů), Tabule (backendová tabule ve stejném okně).
- **Dnes** (`ReceptionTodayScreen`): výchozí obrazovka po načtení pokladny i po přihlášení PINem
  (patch `PosStore.firstScreen` a přesměrování ProductScreen → Dnes jen hned po přihlašovací
  obrazovce, když předtím nebyla otevřená Pokladna). Tři sloupce z `today_data`, přepínání dní
  ‹ Dnes ›; Přijmout jen pro dnešek (`check_in` se jménem přihlášeného zaměstnance), u každé
  rezervace Klient… (u nespárované webové „Spárovat“) – Kartotéka v režimu rezervace s jejím
  majitelem a zvířetem, Zaplatit (viz níže). Obnovení zprávou na sběrnici
  `elite_vet_reservation/changed` a záložně každých 30 s; o půlnoci se „Dnes“ samo přepne na nový
  den; když se první načtení nepovede, ukáže se chyba s tlačítkem „Zkusit znovu“. Nová relace se tu (jako na obrazovce
  produktů) zeptá na počáteční stav hotovosti.
- **Zaplatit** (`PosStore.payReceptionBill`): účet (nabídka) se načte stejně jako v pos_sale
  „Vyrovnat objednávku“ (`_getSaleOrder` → zákazník → fiskální pozice → `settleSO`) bez výběrového
  okna a otevře se platba. Účet dostane vždy vlastní pokladní objednávku, pokud ta otevřená není
  prázdná a bez jiného zákazníka – dva klienti se nikdy nesmíchají na jedné účtence. Účet, který
  už v některé otevřené objednávce je, se zaplatí v ní (vybere se) – nikdy ve dvou objednávkách.
- **Kartotéka** (`CardIndexDialog`, dialog nad pokladnou): hledání (Enter), výsledky (zvířata
  a majitelé), karta majitele s otevřenými účty a zvířaty, formuláře majitele (nový klient
  rovnou i s prvním zvířetem) a zvířete (druhy z `pet_options`), akce Přijmout bez objednání
  (volitelně lékařka), Objednat, Vybrat k účtu (zákazník otevřené objednávky; objednávka s položkami jiného klienta se
  nepřepíše – vznikne nová), Přiřadit k rezervaci (otevřeno z Dnes: ta rezervace; z lišty
  „Přiřadit k rezervaci…“: výběr z `reservations_to_assign`, rezervace s návštěvou neaktivní),
  Zavřít. Po přiřazení se Dnes obnoví.
- **Objednat** (`ReceptionBookingScreen`): úkon, lékařka, den ‹ Dnes › / datum, další volný den,
  volné časy (`free_slots`), poznámka, Objednat (`book`); po úspěchu i po chybě („mezitím
  obsazeno“) se časy načtou znovu.
- Chyby API (`UserError`) se ukazují jako upozornění pokladny česky.
- Kdo pokladnu otevírá (počáteční stav hotovosti), musí mít u uživatele vyplněný e-mail – Odoo
  při otevření relace zapisuje zprávu a bez adresy odesílatele otevření odmítne.

## Ordinace: Moji pacienti dnes (karta pacienta)

Úvodní obrazovka karty pacienta (`elite_vet_clinic`) se rozšiřuje odsud: `models/patient_card.py`
(`_inherit`) a `static/src/patient_card_patch/` (JS `patch`, XML `t-inherit`, bundle
`web.assets_backend`).

- `my_patients_today()` – filtr podle lékařky zůstává (rezervace i neobjednaní jen její; účet bez
  spárované lékařky vidí vše). Každá položka navíc nese:
  `key` (`r<rezervace>` / `w<záznam>`, unikátní), `group` (`waiting` / `in_room` / `arriving` / `done`),
  `visit_stage` (`waiting` / `in_room` / `False`), `arrived_time`, `called_time`, `waiting_minutes`
  (jen u rozepsaného záznamu ve stavu Čeká / V ordinaci, u V ordinaci od příchodu do zavolání, jinak
  `None`), `payment_state`, `walk_in`.
- `unassigned` (nový klíč odpovědi, pravidlo R17): dnešní rozepsaní neobjednaní bez lékařky ve stavu
  Čeká / V ordinaci, stejný tvar jako `items`. Plní se jen u filtrovaného seznamu lékařky (nefiltrovaný
  je má v `items`); úvodní obrazovka je ukazuje v Čekají s poznámkou „kterákoli lékařka“.
- Skupiny: **Čekají** (rozepsaný záznam ve stavu Čeká, podle příchodu, „přišel 9:24 · čeká 6 min“,
  tlačítko Zavolat), **V ordinaci**, **Objednaní – ještě nepřišli** (rezervace bez záznamu nebo se
  záznamem bez stavu), **Hotovo dnes** (uzavřený záznam; také rezervace ve stavu Proběhlá bez záznamu).
- Neobjednaní (dnešní záznamy se stavem návštěvy bez rezervace, `walk_in: true`, `reservation_id: None`)
  jsou v `items` podle lékařky záznamu; bez lékařky jsou v `unassigned`.
- **Zavolat** = `elite.vet.reception.call_patient(record_id)`, pak se otevře karta zvířete. Záznam bez
  lékařky dostane lékařku volajícího uživatele (když je spárovaný); tlačítko je během volání neaktivní.
- Texty: „příchod 9:24 · čeká 6 min“, „od 9:30“ (zavoláno).
- Pravidlo R5: když sestra nebo lékařka otevře kartu (ze seznamu, z tabule, z hledání …) a dnešní
  záznam je ve stavu Čeká, karta jednou zavolá `call_patient`; `card_data` zůstává jen pro čtení.
  Chyba (např. role recepce) se tiše ignoruje. `_record_data` proto nese i `visit_stage`.
- Seznam se obnovuje zprávou na kanálu `elite_vet_reservation/changed` a záložně každých 30 s,
  dokud je vidět úvodní obrazovka.

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

## Pro správce

Krátce, co musí vedení / správce nastavit a hlídat (podrobnosti výše; uživatelský postup
v [návodu, část C](doc/recepce-v-pokladne.md)):

- **Role a výchozí obrazovky.** Role = skupiny Elite Vet (Recepce < Sestra < Lékařka < Správce =
  Vedení). Recepce → pokladna Recepce, sestra a lékařka → Karta pacienta, vedení → Přehled tržeb
  a výdajů. Nastaví se samy při změně skupin uživatele; po úpravě členů ve formuláři skupiny
  použijte Uživatelé › Akce › **Nastavit výchozí obrazovky** (zaškrtnout libovolného uživatele,
  provede se pro všechny interní). Vlastní výchozí obrazovka se nepřepisuje.
- **Skrytá menu** (každá aktualizace `elite_vet_reception` je nastaví znovu): Prodej, Fakturace,
  Zaměstnanci, WinVet data, Rozpis služeb, Web, Přehledy a Aplikace jen vedení; Ordinace od
  sestry (recepce ne); ve Skladu sestra a lékařka jen Přehled skladu a Příjem zboží.
  Samostatná aktualizace modulu, kterému menu patří, vrátí jeho skupiny – pak aktualizujte
  i `elite_vet_reception`.
- **Účetní** potřebuje skupinu **Vedení** (menu Fakturace je jen pro vedení).
- **Zaměstnanci s PINem.** Modul žádné nezakládá. Vedení je zakládá v **Zaměstnanci** (jméno,
  záložka Nastavení › **PIN kód**, případně Příslušný uživatel) a povolí na pokladně: Prodejní
  místa › Konfigurace › Nastavení › pokladna Recepce › Rozhraní PoS › Přihlásit se jako
  zaměstnanec › **Základní oprávnění** (recepční) / **Pokročilé oprávnění** (uzávěrka, oprava
  platby, vklad a výběr hotovosti). Prázdné seznamy = smí každý zaměstnanec firmy.
  Bez pokročilého oprávnění vidí „Zavřít pokladnu“ jen zaměstnanec propojený s uživatelem,
  pod kterým je relace otevřená.
- **E-mail u uživatele.** Kdo otevírá pokladnu (počáteční stav hotovosti), musí mít e-mail –
  jinak Odoo otevření relace odmítne.
- **Před aktualizací modulů zavřete pokladnu.** Přihlášení PINem (`module_pos_hr`) jde zapnout
  jen bez otevřené relace; jinak aktualizace zapíše varování do logu a je třeba ji po uzávěrce
  zopakovat. Totéž platí pro nastavení `elite_vet_sale`.

## Testy

```bash
docker compose stop odoo
bash elite_vet/nasazeni/testy-reception.sh "" update   # první běh bez "" update (instalace)
docker compose start odoo
```
