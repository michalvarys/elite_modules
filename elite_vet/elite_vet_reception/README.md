# Recepce (elite_vet_reception)

Odoo 18 modul: pracoviště recepce v pokladně Odoo „Recepce“ a stavy návštěvy
(spec: `docs/superpowers/specs/2026-10-22-reception-workplaces-design.md`).
Závisí na `elite_vet_sale` a `pos_hr`. Ostatní moduly se neupravují, jen rozšiřují (`_inherit`).

Návod pro recepci, lékařky a vedení: [doc/recepce-v-pokladne.md](doc/recepce-v-pokladne.md);
obrazovka Ordinace a účty ordinací: [doc/ordinace.md](doc/ordinace.md).

## Stavy návštěvy

Na `elite.vet.clinical.record` přibývá:

| Pole | Význam |
|---|---|
| `visit_stage` | `waiting` (Čeká) / `in_room` (V ordinaci); prázdné = záznam vznikl mimo recepci |
| `arrived_at` | čas příchodu (přijetí recepcí) |
| `called_at` | čas zavolání do ordinace |
| `received_by` | jméno zaměstnance pokladny (pos_hr), který klienta přijal – volitelné |
| `room_id` | ordinace návštěvy (úkol 15): z rezervace (uložený compute podle `reservation_id`, doplní se i stávajícím záznamům), prázdná = nepřiřazená (neobjednaní); mění ji `assign_room` / `call_patient` |

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
| `check_in(reservation_id, employee_name=None, note=None)` | záznam (`record_id`, `stage`, …) |
| `check_in_winvet(event_id, employee_name=None, note=None)` | záznam; dnešní záznam kalendáře WinVetu se zvířetem z kartotéky (návštěva v ordinaci podle mapování, `winvet_event_id` na záznamu návštěvy; záznam WinVetu se nemění) |
| `walk_in(pet_id, doctor_id=False, employee_name=None, room_id=False, note=None)` | záznam |
| `set_reception_note(record_id, note)` | záznam; poznámka recepce rozepsané návštěvy (prázdná = smazat) |
| `call_patient(record_id, room_id=None, doctor_id=False)` | záznam + `needs_doctor`; jen sestra a lékařka |
| `assign_room(record_id, room_id=False, doctor_id=False)` | záznam + `needs_doctor` |
| `room_board(day=None)` | data obrazovky Ordinace (viz níže) |

- **arriving** – potvrzené rezervace dne (bez druhých ordinací) bez nezrušeného záznamu, podle času:
  `reservation_id, time, pet_id|None, pet_name, owner, partner_id, procedure, doctor, room, needs_match`
  (`needs_match` = webová rezervace bez spárovaného zvířete), navíc `key` (`r-<rezervace>`) a
  `source` (`odoo`). Se zapnutým kalendářem z WinVetu (elite_vet_winvet) i dnešní záznamy WinVetu se
  zvířetem z kartotéky, nevyřízené a ještě nepřijaté: `key` `w-<záznam>`, `winvet_event_id`,
  `reservation_id` None, `source` `winvet`, `time` None u celodenních; řazeno podle času.
- **waiting** – rozepsané záznamy dne se stavem návštěvy, podle příchodu:
  `record_id, pet_name, owner, doctor, room, stage, stage_label, arrived_time, waiting_minutes,
  reception_note` (u V ordinaci minuty od příchodu do zavolání).
- **to_pay** – všechny nezaplacené účty návštěv (Čeká na platbu / Částečně zaplaceno) bez ohledu
  na den, nejstarší první:
  `record_id, sale_order_id, pet_name, owner, partner_id, amount, payment_state, payment_state_label,
  date, date_label, room_note` (`amount` = zbývá zaplatit, `date_label` = „dnes“ nebo „D. M.“,
  `room_note` = poznámka ordinace pro recepci; s ní Zaplatit nejdřív ukáže okno „Poznámka
  z ordinace“ → Pokračovat k platbě). Stejné položky má `open_bills` v `owner_data`.
- **paid_count** – počet dnes zaplacených záznamů.
- Záznam (`check_in` / `walk_in` / `call_patient` / `assign_room`): `record_id, stage, stage_label,
  state, pet_id, pet_name, reservation_id, doctor, arrived_time, received_by, room_id, room,
  reception_note`.
  Ve sloupci Čekárna a ordinace (`waiting`) je `room` ordinace návštěvy (`room_id`), ne rezervace.

Pravidla přijetí:

- Přijmout jde jen rezervaci na dnešek (den kliniky): „Rezervace není na dnešek – přijmout jde jen
  dnešní návštěvu.“ Jen potvrzenou rezervaci; proběhlá (`done`): „Proběhlou rezervaci nelze znovu
  přijmout.“
- Souběžné přijetí ze dvou pokladen: druhé narazí na unikátnost rezervace a vrátí už založený záznam.
- Rezervace, která už záznam má (lékařka otevřela kartu dřív), vrátí tento záznam; nový nevznikne
  a stav V ordinaci zůstane.
- Webová rezervace bez zvířete skončí chybou „Rezervace z webu ještě není spárovaná s klientem
  a zvířetem – otevřete Kartotéku.“
- Nový záznam dostane lékařku z rezervace (u `walk_in` zadanou lékařku), stav Čeká, `arrived_at`
  a `received_by`.
- `walk_in` použije dnešní rozepsaný záznam zvířete, jinak založí nový (i když už dnes jeden
  uzavřený má).
- **Poznámka recepce** (požadavek 25. 10., pole `reception_note` záznamu z `elite_vet_clinic`):
  `note` u `check_in` / `walk_in` se ořízne a zapíše jen neprázdná (opakované přijetí bez poznámky
  starou nechá). `set_reception_note` ji změní nebo smaže, jen u rozepsané návštěvy („Návštěva je už
  uzavřená – poznámku recepce už nejde změnit.“). Sledovaná v chatteru, do nabídky ani na účtenku se
  nedostane. Pokladna: Přijmout v Dnes i v tabuli otevře `NoteDialog` (`static/src/pos/note_dialog/`,
  Enter = potvrdit), u Čekárny a ordinace tlačítko Poznámka, v Kartotéce při Přijmout bez objednání
  textové pole.
- Každá změna pošle zprávu na tabuli (`notify_board`, kanál `elite_vet_reservation/changed`);
  stejně i uzavření (Hotovo, k pokladně), znovuotevření a zrušení záznamu, takže sloupec
  K pokladně v pokladně se mění hned.

## Kartotéka (majitelé a zvířata)

Stejné API `elite.vet.reception`, stejná kontrola role. Majitele a zvířata recepce zakládá
a upravuje vlastními právy (bez sudo); pod sudo se čtou jen účty návštěv.

| Metoda | Vrací |
|---|---|
| `booking_search(term)` | řádky vyhledávání v kroku 1 Objednat: `{kind: "pet", id, name, species_label, owner, partner_id, phone}` za každé živé zvíře (majitel nalezený jménem / telefonem / e-mailem → všechna jeho živá zvířata, každé jednou), majitel bez živého zvířete `{kind: "owner", id, partner_id, owner, phone}`; bez personálu a firem (pravidlo Kartotéky), bez uhynulých; nejvýš 20 řádků, méně než 2 znaky = `[]` |
| `card_search(term)` | seznam: zvířata (`kind: "pet"`, tvar `search_patients` karty pacienta – jméno, majitel, čip, číslice telefonu) a majitelé (`kind: "owner"`: `id, partner_id, name, owner, phone, email, pet_count`) podle jména / telefonu / e-mailu, které žádné nalezené zvíře neukazuje (např. bez zvířat); méně než 2 znaky = `[]` |
| `owner_data(partner_id)` | `{"owner": {id, name, phone, mobile, email, street, city, zip}, "pets": [...], "open_bills": [...], "no_shows": {...}}` (zvíře navíc `no_show_count`) |
| `client_no_shows(partner_id)` | `no_show_summary` klienta pro upozornění v Objednat: `{count, last_date, last_label, text, items: [{id, date, date_label, procedure, pet}]}` (požadavek 25. 10., rezervace Nedorazil za 12 měsíců, viz `elite_vet_reservation/models/no_show.py`) |
| `save_owner(vals, partner_id=None)` | `owner_data`; klíče `name, phone, mobile, email, street, city, zip` (jiné se ignorují), jméno povinné; nový majitel má `is_vet_client` |
| `save_pet(partner_id, vals, pet_id=None)` | `owner_data`; klíče (Task 22) `name, species, species_other, breed, sex, birth_date, birth_year, chip, tattoo, passport, color, weight, next_vaccination, next_deworming, important_note, note, death_date` (text, prázdné = nic; data `RRRR-MM-DD`; `weight` v kg i s desetinnou čárkou, ≥ 0; `birth_year` 1950 … letos; narození a úhyn ne v budoucnosti, úhyn ne před narozením), `deceased` (bool, jen při úpravě – nové zvíře nejde založit jako uhynulé; `false` smaže `death_date`), `alerts` (`[{id?, kind, note}]` = celý seznam aktivních upozornění: s `id` se upraví, bez `id` přibude, chybějící se archivují; bez klíče se upozornění nemění). `species_other` jen u druhu `other`. Jméno a druh povinné, zvíře musí patřit majiteli |
| `pet_options()` | `{"species": [{value, label}], "alert_kinds": [{value, label}]}` – druhy zvířete a druhy upozornění (karta pacienta) pro formulář zvířete |
| `match_reservation(reservation_id, partner_id, pet_id)` | `{reservation_id, time, partner_id, owner, pet_id, pet_name, needs_match}` – rezervace (webová i už spárovaná) dostane majitele a zvíře (i její druhá ordinace); webová pak jde přijmout |

- **pets** – všechna aktivní zvířata majitele (uhynulá na konci): `id, name, species, species_other,
  species_label, breed, sex, birth_date, birth_year, chip, tattoo, passport, color, weight, note,
  important_note, alerts, alert_list, next_vaccination, next_deworming, deceased, death_date,
  no_show_count` (`alerts` = souhrn upozornění, `alert_list` = `[{id, kind, kind_label, note}]`
  aktivních upozornění, prázdné hodnoty `null`).
- **Upozornění** (`elite.vet.pet.alert`) recepce podle ACL jen čte; `save_pet` je po kontrole role
  zapisuje pod sudo, jen u toho jednoho zvířete. Odebrání = archivace (jako v kartě pacienta).
- **open_bills** – nezaplacené účty majitele, stejný tvar jako `to_pay` (`record_id, amount,
  payment_state_label, …`).
- Stejný telefon nebo e-mail jako jiný majitel nevadí: uloží se, nic se neslučuje.
- Majitel nesmí být kontakt uživatele (personál) ani firmy: „Tento kontakt není klient kliniky.“
  Úprava existujícího kontaktu mu `is_vet_client` nepřidá (jen nový majitel ho dostane).
- Hodnoty formuláře se berou jako text (ořezaný); jiná data skončí chybou.
- `match_reservation` u druhé ordinace páruje hlavní rezervaci; rezervace, která už má návštěvu
  jiného zvířete, skončí chybou „Rezervace už má návštěvu jiného zvířete.“ Rezervaci s jiným
  zvířetem, která ještě návštěvu nemá, přepíše (změna klienta). Zrušená rezervace: chyba; proběhlá (`done`): „Proběhlou rezervaci nelze změnit.“
  Při změně klienta (rezervace už měla jiného majitele) se kontakt rezervace (jméno, telefon, e-mail,
  jazyk) přepíše podle nového majitele, stejně jako v průvodci rezervací; e-maily i telefon na tabuli
  pak patří novému klientovi. Jméno a druh zvířete se srovnají vždy; první spárování webové rezervace
  kontakt z formuláře ponechá. Totéž platí pro kopii ve druhé ordinaci.

## Objednání (záložka Objednat)

Stejné API `elite.vet.reception`, stejná kontrola role. Volné časy i uložení jdou přes průvodce
rezervací (`elite.vet.reservation.wizard`, s právy volajícího) – stejný výpočet jako tabule.
Den je `"YYYY-MM-DD"` v čase kliniky, `minute` = minuty od půlnoci.

| Metoda | Vrací |
|---|---|
| `booking_options()` | `{"procedures": [{id, name, duration}], "doctors": [{id, name}], "frequent": [id]}` (lékařky přijímající objednávky; `frequent` = nejvýš 6 úkonů s nejvíc rezervacemi – druh rezervace, ne zrušené, bez kopií druhé ordinace – za posledních 30 dní do dneška, od nejčastějšího; bez dat prvních 6 úkonů v běžném pořadí) |
| `free_slots(procedure_id, day, doctor_id=False)` | `{"day", "slots": [{time, minute, room_id, room, doctor_id, doctor}], "next_free_day"}` – řádky průvodce (čas × ordinace); `next_free_day` = nejbližší další den s volným časem v horizontu recepce, jinak `None` |
| `free_days(procedure_id, day, doctor_id=False, days=7)` | `[{day, count, closed}]` – řada dnů v Objednat: počet různých volných časů dne (jako průvodce); `None` pro minulý den a den za horizontem; nejvýš 14 dní. `closed: true` = den bez jakékoli možnosti volna bez ohledu na rezervace: žádná ordinační doba v ordinacích úkonu pro recepci (i výjimka „zavřeno“), plná blokace přes ně, nebo – když je lékařka potřeba (nastavení, specializace úkonu, filtr lékařky) – žádná služba lékařky, která úkon dělá. Otevřený, ale plně obsazený den má `count: 0, closed: false` |
| `nearest_free(procedure_id, doctor_id=False)` | `{day, time, minute, room_id, room, doctor_id, doctor}` nejbližšího volného času od teď v horizontu recepce (řádky průvodce jako `free_slots`; víc ordinací ve stejné minutě → první podle přirozeného řazení názvů, jako na obrazovce), jinak `None`; za horizont se nehledá |
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

- **Lišta** (jediný patch navbaru, `navbar_patch/`): Dnes, Kartotéka… (režim `browse`), Objednat
  (znovu stisknuté na Objednat ukončí režim Přesunout), Pokladna (standardní obrazovka produktů),
  Tabule (dialog `BoardDialog` nad pokladnou, viz níže).
- **Pokladna** (obrazovka produktů): tlačítko **Klient** v ovládacích tlačítkách účtu
  (`control_buttons_patch/`, `t-inherit` `point_of_sale.ControlButtons`, na malé obrazovce
  `point_of_sale.ActionpadWidget`; komponenta přes `patch` `components`) otevře Kartotéku v režimu
  `order` a ukazuje zákazníka účtu („Klient: Jana Nováková“). Standardní `SelectPartnerButton`
  je v pokladně Recepce skrytý a `PosStore.selectPartner` (Zákazník na obrazovce platby, dotaz
  na zákazníka u faktury) otevře místo seznamu partnerů tutéž Kartotéku – pravidla úkolu 5 platí
  vždy (vratka: standardní upozornění zůstává). Výběr z obrazovky platby pro tentýž účet na ní
  zůstane, nový účet přepne na Pokladnu.
- **Dnes** (`ReceptionTodayScreen`): výchozí obrazovka po načtení pokladny i po přihlášení PINem
  (patch `PosStore.firstScreen` a přesměrování ProductScreen → Dnes jen hned po přihlašovací
  obrazovce, když předtím nebyla otevřená Pokladna). Tři sloupce z `today_data`, přepínání dní
  ‹ Dnes ›; Přijmout jen pro dnešek (`check_in` se jménem přihlášeného zaměstnance), u každé
  rezervace Klient… (u nespárované webové „Spárovat“) – Kartotéka v režimu `reservation` s jejím
  majitelem a zvířetem, „+ Bez objednání“ u Přicházejí (jen dnešek) – Kartotéka v režimu
  `walk_in`, Zaplatit (viz níže). Obnovení zprávou na sběrnici
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
  rovnou i s prvním zvířetem) a zvířete (druhy z `pet_options`). Formulář zvířete (Task 22) má
  nahoře jméno, druh (u Jiné i Jiný druh), pohlaví, plemeno, narození a čip, sbalovací sekci
  **Další údaje** (u nového zvířete zavřená, u úpravy otevřená, když v ní něco je: rok narození,
  hmotnost, barva, tetování, pas, příští vakcinace a odčervení, Důležité, poznámka), seznam
  **Upozornění** (druh + poznámka, přidat / odebrat) a jen při úpravě **Uhynulý** + datum úhynu
  (s potvrzením). Karta majitele ukáže u zvířete Důležité jako červený štítek, hmotnost a příští
  odčervení. Prop `mode` určuje jediný úkol
  okna: nadpis okna říká, k čemu se klient vybírá, pod ním je krátká nápověda a v patičce je
  nejvýš jedno hlavní tlačítko (vedle Zavřít):

  | `mode` | Odkud | Nadpis | Hlavní tlačítko |
  |---|---|---|---|
  | `browse` (výchozí) | lišta Kartotéka… | Kartotéka | žádné (jen hledání, prohlížení, založení a úprava) |
  | `booking` | Objednat, krok 1 („+ Nový klient“, „Upravit“, majitel bez zvířete) | Vybrat klienta a zvíře pro objednání | Vybrat → `onSelect({id, name, owner, partner_id})`, okno se zavře |
  | `order` | Pokladna, tlačítko Klient | Klient k účtu v pokladně | Vybrat k účtu – zákazník otevřené objednávky; objednávka s položkami jiného klienta se nepřepíše – vznikne nová (úkol 5) |
  | `reservation` | Dnes Klient… / Spárovat, detail na tabuli Klient… | Klient k rezervaci 9:00 Očkování | Přiřadit k rezervaci (`match_reservation`), pak `onChanged` |
  | `walk_in` | Dnes + Bez objednání | Přijmout bez objednání | Přijmout (`walk_in`) s výběrem lékařky kterákoli / konkrétní, pak `onChanged` |

  Další props: `reservation` (režim `reservation`: `{reservation_id, time, procedure, owner,
  partner_id, pet_id, pet_name}`, předvyplní klienta a zvíře), `client` (`{partner_id, pet_id}` –
  v režimu `booking` dosavadní výběr; v režimu `order` se bez něj ukáže zákazník otevřené
  objednávky), `start` (`"new_owner"` – okno se otevře rovnou na formuláři Nový klient;
  `"new_pet"` – u klienta z `client` rovnou na formuláři Nové zvíře). Tlačítka, která potřebují zvíře, jsou bez vybraného živého zvířete neaktivní
  s poznámkou „Vyberte zvíře.“ (klient bez zvířat: „Přidejte zvíře (+ Nové zvíře).“)
- **Objednat** (`ReceptionBookingScreen`): jeden sloupec očíslovaných kroků – 1 Klient a zvíře
  (pole hledání přímo v kroku: `booking_search` 300 ms po posledním znaku, od 2 znaků, Enter =
  hned / první řádek; řádek zvířete „Rex (pes) · Jana Nováková · 777…“ vybere, řádek majitele bez
  zvířete otevře Kartotéku `booking` + `start: "new_pet"`; „+ Nový klient“ = Kartotéka `booking` +
  `start: "new_owner"`; po výběru „Rex · Jana Nováková [Změnit] [Upravit]“ – Změnit otevře
  hledání znovu, Upravit Kartotéku na klientovi a zvířeti), 2 úkon (častá z `frequent` jako velká
  tlačítka, vybraný úkon mimo ně jako další zvýrazněné tlačítko; „Jiný úkon…“ = seznam všech
  s filtrem bez diakritiky), 3 den (nad řadou tlačítko „Nejdřív: dnes 14:30 · Ordinace 2 ·
  MVDr. Malá“ z `nearest_free` – vyplní den, ordinaci i čas a posune řadu na jeho týden; řada 7 dní
  od `weekStart` s počty z `free_days`, zavřený den šedý, neaktivní, „zavřeno“, „nic volného“ jen
  pro otevřený plně obsazený; ‹ › o týden a vybere první den s volnem, kalendář, další volný den;
  filtr „jen lékařka…“ = `doctorId`; po změně úkonu / lékařky a v režimu Přesunout skočí výběr na
  první den řady s volnem, když vybraný den volno nemá – ne po kliknutí na den ani s `prefill`
  z tabule), 4 ordinace (jen víc ordinací s volnem – `rooms`, jedna se
  vybere sama – `activeRoom`; volba zůstává přes změnu dne), 5 čas (`free_slots` vybrané
  ordinace, dopoledne / odpoledne). Dole souhrn (`summary`), poznámka a jediné tlačítko Objednat
  (`book`). Po úspěchu se formulář vyprázdní (vše kromě dne), upozornění „Objednáno: čt 22. 10.
  2026 9:00 · Rex“; po chybě („mezitím obsazeno“) se dny i časy načtou znovu. Vybraný klient je ve
  stavu obrazovky (prop `pet` jen jako počáteční hodnota). Props z tabule a lišty (POS obrazovku
  nepřipojuje znovu, jen mění props – `onWillUpdateProps`, rozlišení podle `key`): `prefill`
  `{day, minute, room_id, room, key}` (klik do volného místa: den a ordinace, po výběru úkonu se
  vybere čas, když je volný, jinak upozornění), `reset` `{key}` (lišta Objednat znovu: konec režimu
  Přesunout), `move` `{reservation_id, procedure_id, doctor_id, day, label, pet_name, owner,
  procedure, key}` (režim Přesunout rezervaci: bez kroku klienta, úkon a lékařka předvyplněné,
  tlačítko „Přesunout“ = `move_reservation`). „Tabule“ otevře `BoardDialog` na vybraném dni.
- **Tabule** (`board_dialog/`, `BoardDialog`, velikost dialogu `fs`): data z
  `elite.vet.reservation.board_data(day)` (stejná jako backendová tabule, `payment_state`
  z elite_vet_sale) ve vlastní šabloně a SCSS (třídy `o_ev_board_*`, geometrie jako backend:
  1,6 px/min, pruhy služeb lékařek, události s barvou úkonu a proužkem lékařky, blokace, štítek
  k pokladně / zaplaceno, čára „teď“ v čase kliniky). Den ‹ Dnes › a datum; obnovení zprávou
  `elite_vet_reservation/changed` a každých 30 s, časovače se ruší při zavření. Klik na rezervaci
  → `BoardEventDialog` (`board_reservation`): Přijmout (`check_in` hlavní rezervace), Klient…
  (Kartotéka v režimu `reservation` nad tabulí, tabule zůstane otevřená; ne u zrušené, proběhlé
  a nedorazivší), Přesunout (Objednat s `move`; jen `can_move`), Zrušit rezervaci (potvrzení
  v dialogu, `cancel_reservation`), Nedorazil (jen `can_no_show`, potvrzení v dialogu,
  `no_show_reservation`). Přetažení (HTML5 drag & drop, jen potvrzené hlavní rezervace,
  ne kopie druhé ordinace – `is_second_room` v událostech `board_data`) → `move_reservation`.
  Po změně dne se tabule posune na „teď“ (dnešek), jinak na začátek dne. Klik do volného
  místa (i přes blokaci „jen web“) → dialog se zavře, Objednat s `prefill` (vybrané zvíře
  z Objednat zůstává). Blokace jsou jen ke čtení.
- Chyby API (`UserError`) se ukazují jako upozornění pokladny česky.
- Kdo pokladnu otevírá (počáteční stav hotovosti), musí mít u uživatele vyplněný e-mail – Odoo
  při otevření relace zapisuje zprávu a bez adresy odesílatele otevření odmítne.

## Tabule v pokladně – API

Stejné API `elite.vet.reception`, stejná kontrola role. Den tabule čte pokladna přímo
`elite.vet.reservation.board_data` (recepce má na rezervace práva čtení i zápisu). Přesun
a zrušení jdou s právy volajícího přes existující metody rezervace – žádná vlastní pravidla
dostupnosti.

| Metoda | Vrací |
|---|---|
| `board_reservation(reservation_id)` | detail: `reservation_id, main_id, state, state_label, source, date, date_label, is_today, time, time_label, room_id, room, procedure_id, procedure, doctor_id, doctor, partner_id, owner, pet_id, pet_name, phone, email, problem, note, linked, is_second_room, needs_match, has_record, visit_label, payment_state, payment_state_label, can_check_in, can_move, can_cancel, can_no_show, cancel_sends_email` |
| `move_reservation(reservation_id, day, minute, room_id=False)` | `board_reservation` po přesunu přes `board_move` (lékařka ve službě, ordinace úkonu, kontrola překryvu při zápisu) |
| `no_show_reservation(reservation_id)` | `{reservation_id, state}` – Nedorazil přes `action_no_show` z backendu (bez e-mailu; jen potvrzená hlavní rezervace z dneška nebo dřív bez návštěvy, jinak `UserError`; blokace a kopie ve druhé ordinaci ne). Tabule se obnoví přes bus (`write` → `notify_board`), počítá se do „Nedorazil N×“ |
| `cancel_reservation(reservation_id)` | `{reservation_id, state, email_sent}` – `action_cancel("clinic")` hlavní rezervace (e-mail o zrušení jako v backendu, jen s `contact_email`) |

- U druhé ordinace společného zákroku (`is_second_room`) patří klient, návštěva a zrušení hlavní
  rezervaci (`main_id`). Přesouvá se jen hlavní rezervace (čas se do kopie synchronizuje):
  u kopie je `can_move` False a `move_reservation` skončí chybou „Druhá ordinace se přesouvá
  s hlavní rezervací – přesuňte hlavní rezervaci.“
- `board_data` (patch `elite.vet.reservation` odsud) přidává ke každé události `is_second_room`.
- `can_check_in`: dnešní potvrzená rezervace se spárovaným zvířetem bez návštěvy;
  `can_move` / `can_cancel`: potvrzená (zrušit i čekající z webu) a bez návštěvy; `can_move`
  navíc ne u kopie druhé ordinace.
- Přesun i zrušení rezervace, která už má návštěvu: „Klient už je přijatý (návštěva je založená)
  – rezervaci nejde přesunout / zrušit.“ Přesunout jde jen potvrzenou rezervaci, zrušit jen
  potvrzenou nebo čekající. Blokace: „Rezervace nebyla nalezena.“

## Obrazovka Ordinace (úkol 15)

Klientská akce `elite_vet_reception.action_room_board` (tag `elite_vet_reception.room_board`,
`static/src/room_board/`, bundle `web.assets_backend`), menu **Ordinace › Ordinace** (první položka,
Recepce a výš). Params `{room_id}` otevře jednu ordinaci. Návod: [doc/ordinace.md](doc/ordinace.md).

- **Účet ordinace**: `res.users.elite_vet_room_id` (formulář uživatele › Přístupová práva › Elite
  Vet). Výchozí obrazovka takového účtu (role Recepce až Lékařka, ne Vedení) je obrazovka Ordinace;
  obrazovka se na účtu ordinace otevře vždy na jeho ordinaci, jinak na volbě uložené v prohlížeči
  (`localStorage` `elite_vet_reception.room_view`, `all` nebo id ordinace).
- **Účet člena týmu** (úkol 23): `elite.vet.doctor.user_id` (Rozpis služeb › Lékařky › Účet,
  unikátní, jen interní uživatelé; na uživateli jen pro čtení `elite_vet_doctor_id` „Člen týmu“).
  Propojený účet s rolí Sestra / Lékařka (ne Vedení, ne účet ordinace) má výchozí obrazovku
  Ordinace. Obrazovka se mu při každém otevření nastaví na ordinaci, kde má teď službu (jinak další
  dnešní službu, jinak Všechny ordinace); ruční přepnutí platí, dokud v obrazovce pracuje (i po
  návratu z karty jejím tlačítkem zpět – obnova akce z drobečkové navigace, `useSetupAction`
  `getLocalState`; obnovení stránky a Zpět prohlížeče otevírají znovu), do `localStorage` se neukládá.
  Kdo pacienta převzal: `assign_room` / `call_patient` propojenou **Lékařkou** (člen týmu s rezervacemi) zapíše za lékařku ji,
  když záznam lékařku nemá nebo ji má jen automaticky (`doctor_auto`: z rozpisu, z rezervace); ručně vybraná lékařka
  zůstane. Sestry, recepce a účty ordinací dál podle rozpisu. Úpravy obsahu záznamu propojenou
  lékařkou: viz README modulu elite_vet_clinic, „Ošetřující lékařka“.
  `_doctor_for_user` (Moji pacienti dnes, R17): nejdřív propojení, shoda jména jen u účtu bez
  propojení, a ne, když je lékařka toho jména propojená s jiným účtem.
- **Vytvořit účty** (`elite.vet.account.wizard`, tlačítko v seznamu Lékařky + Akce, jen Vedení):
  viz [doc/ordinace.md](doc/ordinace.md) kapitola 6.
- **`room_board(day=None)`** → `{"date", "is_today", "time", "columns": [...], "rooms": [{id, name,
  color}], "perms": {"can_call", "user_room_id", "member_account", "roster_room_id"}}`. `columns[0]` = Nepřiřazení (`key: "unassigned"`,
  `room_id: None`), pak jedna za každou aktivní ordinaci v pořadí (`sequence`) a ordinace, které
  mají dnes návštěvu, i když jsou archivované. Sloupec: `key, room_id, name, color, on_duty: [{id,
  name}]` (služby `elite.vet.doctor.assignment` dne, které pokrývají teď; jen dnes), `shifts:
  [{doctor, label, now}]`, `sections: {in_room, waiting, booked, done}`, `counts`.
  - `in_room` / `waiting`: rozepsané záznamy dne se stavem návštěvy (podle zavolání / příchodu),
  - `booked`: potvrzené rezervace dne (bez druhých ordinací) bez nezrušeného záznamu + rozepsané
    záznamy bez stavu (karta otevřená před příchodem), podle času rezervace,
  - `done`: uzavřené záznamy dne.
  - Karta: `key` (`r<záznam>` / `b<rezervace>`), `record_id, reservation_id, walk_in, stage`
    (`in_room/waiting/booked/done`), `time` (příchod, jinak čas rezervace), `reservation_time,
    arrived_time, called_time, waiting_minutes, pet_id, pet_name, species_label, owner, partner_id,
    procedure, doctor, doctor_id, room_id, alerts, reception_note, draggable` (jen dnešní rozepsaný
    záznam se stavem).
- **`assign_room(record_id, room_id=False, doctor_id=False)`**: jen dnešní rozepsaný záznam
  („Do ordinace jde přiřadit jen dnešní rozepsanou návštěvu.“), `room_id` False = zpět do
  Nepřiřazení. Rezervace svou ordinaci nemění (tabule ukazuje rezervaci).
- **Lékařka z rozpisu** (`_set_room`): záznam **bez lékařky**, který dostane ordinaci (přiřazení,
  Zavolat, příjem bez objednání s ordinací), dostane lékařku, která v ordinaci teď slouží
  (`hour_from ≤ teď < hour_to`). Dvě ve službě → je-li mezi nimi lékařka spárovaná s přihlášeným
  uživatelem (podle jména), vezme se ona; jinak odpověď nese `needs_doctor: [{id, name}]` a klient se
  zeptá (pak `assign_room(…, doctor_id)`). Nikdo ve službě → zůstane prázdná. Zadaná `doctor_id` se
  zapíše vždy. Lékařka už na záznamu zůstává (i při přesunu do jiné ordinace).
- **`call_patient(record_id, room_id=None, doctor_id=False)`**: dosavadní chování zůstává; s `room_id`
  se návštěva přesune do té ordinace; bez něj platí ordinace záznamu. Lékařka podle pravidla výše,
  bez ordinace (nebo nikdo ve službě) jako dřív lékařka volajícího uživatele (R17).
- Každá změna pošle `notify_board` (kanál `elite_vet_reservation/changed`); obrazovka se obnoví
  zprávou a záložně každých 30 s.
- Práva: jako zbytek API (`_check_reception`), zápis přes `_records()` (sudo s příznakem API).
  Zavolat jen sestra a lékařka; recepce přiřazuje.

## Ordinace: Moji pacienti dnes (karta pacienta)

Úvodní obrazovka karty pacienta (`elite_vet_clinic`) se rozšiřuje odsud: `models/patient_card.py`
(`_inherit`) a `static/src/patient_card_patch/` (JS `patch`, XML `t-inherit`, bundle
`web.assets_backend`).

- `my_patients_today()` – filtr podle lékařky zůstává (rezervace i neobjednaní jen její; účet bez
  spárované lékařky vidí vše). Každá položka navíc nese:
  `key` (`r<rezervace>` / `w<záznam>`, unikátní), `group` (`waiting` / `in_room` / `arriving` / `done`),
  `visit_stage` (`waiting` / `in_room` / `False`), `arrived_time`, `called_time`, `waiting_minutes`
  (jen u rozepsaného záznamu ve stavu Čeká / V ordinaci, u V ordinaci od příchodu do zavolání, jinak
  `None`), `payment_state`, `walk_in`, `reception_note` (poznámka recepce, žlutě pod řádkem).
- `unassigned` (nový klíč odpovědi, pravidlo R17): dnešní rozepsaní neobjednaní bez lékařky ve stavu
  Čeká / V ordinaci, stejný tvar jako `items`. Plní se jen u filtrovaného seznamu lékařky (nefiltrovaný
  je má v `items`); úvodní obrazovka je ukazuje v Čekají s poznámkou „kterákoli lékařka“.
- Skupiny: **Čekají** (rozepsaný záznam ve stavu Čeká, podle příchodu, „příchod 9:24 · čeká 6 min“,
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
| Recepce (+ skupina Pokladna a sklad) | `action_open_reception_pos` – pokladna Recepce (`/pos/ui?config_id=…`, stejné okno) | Pokladna, Rezervace, Diskuze, Sklad jen s Přehledem skladu a Příjmem zboží |
| Sestra, Lékařka | Karta pacienta (`elite_vet_clinic.action_patient_card`) | Ordinace, Rezervace, Diskuze – bez Pokladny a Skladu |
| Účet ordinace (Sestra / Lékařka s polem Ordinace) | obrazovka Ordinace (`action_room_board`) na své ordinaci | jako Lékařka |
| Vedení | Přehled tržeb a výdajů (`elite_vet_winvet.action_winvet_dashboard`) | vše |

- **Pokladna a sklad (recepce)** (`elite_vet_sale.group_till_stock`, vlastní kategorie „Elite Vet –
  pokladna“, ve formuláři uživatele samostatné pole mimo výběr role) dává pokladnu, nabídky
  a sklad (`point_of_sale.group_pos_user`, `sales_team.group_sale_salesman_all_leads`,
  `stock.group_stock_user`). Role samy pokladnu ani sklad nedávají; Vedení skupinu má přes
  nadřazené skupiny.
- Při **změně role** (`res.users.create` / `write`, nejvyšší role se změnila): nově Recepce →
  skupinu dostane; nově Sestra nebo Lékařka → odeberou se skupiny pokladny, prodeje a skladu
  (`TILL_RIGHTS` v `elite_vet_sale/models/res_users.py`: tato skupina, POS uživatel/správce,
  prodejce, sklad uživatel/správce). Jen při změně role – ruční zaškrtnutí nebo odškrtnutí potom
  zůstane (např. sestra, která přijímá zboží, může skupinu dostat ručně).
- `/pos/ui` otevře jen uživatel s právem pokladny (`elite_vet_sale/controllers/main.py`, jinak 403);
  Odoo samo stránku otevře každému internímu uživateli a relaci založí pod sudo.

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
  Prodej, Fakturace, Zaměstnanci, WinVet data, Rozpis služeb, Web a Přehledy (Dashboards)
  jen vedení; Aplikace jen správci systému (`base.group_system` při každé aktualizaci – `base_install_request`
  je jinak otevře všem, starší verze je dávala vedení); aplikace Ordinace od recepce, ale recepce v ní
vidí jen první položku Ordinace (obrazovka ordinací), ostatní položky od sestry; Pokladna jen se skupinou
  Pokladna a sklad (recepce) a vedení; Diskuze všem; Sklad (kořen) a v něm jen Přehled skladu
  a Příjem zboží (přesunutý z Operací přímo pod Sklad hned za Přehled skladu) pro skupinu Pokladna
  a sklad a vedení, ostatní položky Skladu jen vedení. Kopie obou položek v Ordinaci jsou jen pro
  vedení (úkol 15; recepce je má ve Skladu).
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
  a výdajů. Pokladnu a sklad dává samostatná skupina **Pokladna a sklad (recepce)**: Recepce ji
  dostane při nastavení role, sestře a lékařce se při změně role odebere (ručně ji lze přidat). Nastaví se samy při změně skupin uživatele; po úpravě členů ve formuláři skupiny
  použijte Uživatelé › Akce › **Nastavit výchozí obrazovky** (zaškrtnout libovolného uživatele,
  provede se pro všechny interní). Vlastní výchozí obrazovka se nepřepisuje.
- **Skrytá menu** (každá aktualizace `elite_vet_reception` je nastaví znovu): Prodej, Fakturace,
  Zaměstnanci, WinVet data, Rozpis služeb, Web a Přehledy jen vedení (Aplikace jen správce systému); Ordinace od
  sestry (recepce v ní vidí jen obrazovku Ordinace); Pokladna a Sklad (jen Přehled skladu a Příjem zboží) jen se skupinou Pokladna
  a sklad (recepce) a vedení – sestra a lékařka je nevidí.
  Samostatná aktualizace modulu, kterému menu patří, vrátí jeho skupiny – pak aktualizujte
  i `elite_vet_reception`.
- **Účty ordinací.** Na ordinaci jeden účet (např. „Ordinace 1“), role **Lékařka**, ve formuláři
  uživatele › Přístupová práva › Elite Vet pole **Ordinace**. Po přihlášení se otevře obrazovka
  Ordinace na této ordinaci. Lékařku návštěvy bere obrazovka z Rozpisu lékařů (rezervace).
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
