# Rezervace

Odoo 18 modul. Nahrazuje rezervační systém WinVet: ordinace, ordinační doba,
rozpis lékařů, úkony a rezervace jsou v Odoo, na webu `/rezervacni-system`
běží vlastní průvodce místo iframu.

## Návody (česky)

- [Návod pro recepci](doc/recepce.md) – tabule, žádosti z webu, nová rezervace,
  přesun, blokace, klienti, e-maily, časté situace.
- [Návod pro správce](doc/nastaveni.md) – práva, lékařky a specializace, ordinace
  a ordinační doba, úkony, rozpis lékařů, nastavení rezervace, kontrolní seznam
  před spuštěním.
- [Jak to funguje](doc/jak-to-funguje.md) – výpočet volných termínů, pravidlo
  lékařka × úkon, cesta žádosti z webu, ochrana proti dvojímu zabrání.

Snímky obrazovek jsou v `doc/img/`.

## Stručně

- Aplikace **Rezervace**: **Tabule**, **Nová rezervace**, **Čekající z webu**,
  **Rezervace**, **Rozpis lékařů**, **Klienti**, **Mazlíčci**, **Konfigurace**
  (Ordinace, Výjimky ordinační doby, Úkony, Nastavení rezervace, Časté dotazy).
- Skupiny: **Recepce** (denní práce) a **Správce rezervací** (konfigurace).
  **Blokace** (`kind = "block"`) zakládá, přesouvá, upravuje a maže jen Správce rezervací:
  pravidla záznamů v `security/rules.xml` (Recepce zapisuje jen `kind != "block"`, čtení beze
  změny) a kontrola v `create` / `write` / `unlink` s hláškou „Blokace může měnit jen správce
  rezervací.“. `board_data` vrací `can_edit_blocks`; bez něj tabule skryje **Nová blokace**,
  blokace nejdou přetáhnout a otevřou se ve formuláři jen ke čtení
  (`view_reservation_block_readonly_form`). Cesty přes `sudo` (web, cron) se to netýká.
- **Nastavení** (`elite.vet.setting` z `elite_vet_web`) ukládá jen Správce rezervací:
  `elite_vet_web` dává zápis správci kalendáře (ACL), tento modul ho pravidlem záznamu omezí na
  čtení (pravidla patří tomuto modulu, `-u elite_vet_web` je nezruší) a `write` / `create` /
  `unlink` hlásí „Nastavení může měnit jen správce rezervací.“. Menu **Nastavení kontaktu**,
  **Nastavení rezervace** a obě serverové akce, které nastavení otevírají, nastaví
  `<function>` v `views/menus.xml` (`elite.vet.setting._elite_vet_apply_setting_groups`) při
  každé instalaci / aktualizaci na Správce rezervací. Čtení (web, veřejnost) zůstává.
- Lékařka = **Lékařka – přijímá rezervace** v Rozpis služeb → Lékařky; kdo dělá
  který úkon, plyne ze specializací na kartě v Náš tým.
- **Směny se zadávají jednou, v Rozpisu služeb.** Směna lékařky s **Ordinací**
  (předvyplní se z **Výchozí ordinace** lékařky) se sama propíše do Rezervace → Rozpis
  lékařů s časem směny (`hour_from` / `hour_to`, předvyplní se z typu směny, jde změnit u každé
  směny); změna / smazání směny nebo ordinace ji upraví / smaže, změna času typu směny přepíše
  od dneška dál směny, které měly čas typu (ručně změněný čas zůstane). Takové služby jsou označené
  **Z rozpisu služeb** a lékařka, ordinace, datum a čas se u nich mění jen v Rozpisu
  služeb. Ruční služby (vlastní čas, půl směny) se dál zadávají v Rozpisu lékařů;
  překrývající se ruční službu téže lékařky směna převezme. **Zkopírovat na další
  týden** kopíruje jen ruční služby. Stávající rozpis jednorázově propíše **Rozpis
  služeb → Převzít rozpis do rezervací** (Správce rezervací). Technicky: model
  `elite.vet.shift` dostal `room_id`, vazba je `shift_id` na `elite.vet.doctor.assignment`
  (`models/shift.py`); modul Rozpis služeb se nemění.
- Průvodce rezervací i objednání v pokladně předvyplní lékařku ve službě (jde změnit).

## Nasazení

- `proxy_mode = True` v `odoo.conf` za reverzní proxy (limit žádostí na IP adresu).
- Funkční odchozí pošta a vyplněný e-mail firmy (odesílatel e-mailů).
- Upgrade s novými překlady: `-u elite_vet_reservation --i18n-overwrite`.

## Co modul neumí (zatím)

Platební brána pro zálohy, import klientů z WinVetu (pole *ID ve WinVetu* je
připravené), SMS.
