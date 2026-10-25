# Upgrade Elite Vet na serveru (říjen 2026)

Instrukce pro agenta na serveru. Kód je na serveru nahraný, zbývá upgrade databáze a kontrola.
Cílový stav kódu je commit `1cc4c9e` (nebo novější) z větve `master`.

**Co upgrade přináší:**
- pokladnu a sklad (`elite_vet_sale`),
- recepci v pokladně (`elite_vet_reception`: Dnes, Objednat, Kartotéka, Tabule, role a výchozí
  obrazovky),
- kartu pacienta (`elite_vet_clinic`),
- napojení Rozpisu služeb na rezervace (`elite_vet_reservation`: ordinace a vlastní čas u směny,
  výchozí ordinace lékařky, úprava služeb z tabule).

## Pravidla

- **Nejdřív záloha** (krok 2). Bez ní nic nespouštěj.
- **Nespouštěj testy** (`nasazeni/testy-*.sh`, `--test-enable`) na ostré databázi. Zapisují do
  databáze a jsou určené pro `ev_test`.
- **Nic nezakládej, neměň ani nemaž v datech.** Neklikej na akce jako „Převzít rozpis do
  rezervací“ nebo „Nastavit výchozí obrazovky“. To jsou kroky pro uživatele (krok 7).
- **Neposílej e-maily** a nepouštěj cron ručně.
- **Když cokoli selže, zastav se.** Nahlas, co se stalo, i s výpisem z logu. Neopravuj kód na
  serveru a neobnovuj zálohu bez souhlasu uživatele.

Dál `<db>` je jméno ostré databáze, `<odoo>` je příkaz Odoo (nebo `docker compose run --rm odoo
odoo` v Dockeru) a `<filestore>` je složka `filestore/<db>`.

## 1. Ověřit kód a stav modulů

```bash
cd <klon repa> && git log --oneline -1          # má být 1cc4c9e nebo novější
```

Když kód na server přišel jako kopie bez gitu, ověř verze v `__manifest__.py`:
`elite_vet_reservation` 18.0.2.1.0, `elite_vet_sale` 18.0.1.0.1, `elite_vet_reception` 18.0.1.0.0
a `elite_vet_clinic` 18.0.1.0.0. Musí existovat soubory
`elite_vet_reservation/models/shift.py` a `elite_vet_reception/models/booking.py` a v souboru
`elite_vet_reservation/models/shift.py` musí být `hour_from`. Když verze nesedí, zastav se.

V `addons-path` musí být složky `elite_vet_*` tak, aby `__manifest__.py` byl přesně jednu úroveň
pod cestou.

```sql
SELECT name, latest_version, state FROM ir_module_module
WHERE name LIKE 'elite_vet_%' OR name IN ('point_of_sale','pos_sale','pos_hr','sale_management','stock','product_expiry','l10n_cz')
ORDER BY name;
```

Výsledek si poznamenej, podle něj se skládá příkaz v kroku 4.

## 2. Záloha

```bash
pg_dump -Fc -d <db> -f elitevet-pred-upgradem-$(date +%F-%H%M).dump
tar czf elitevet-filestore-$(date +%F-%H%M).tgz -C <data_dir>/filestore <db>
```

Ověř, že oba soubory existují a nejsou prázdné.

## 3. Otevřené pokladny

```sql
SELECT id, name, state FROM pos_session WHERE state <> 'closed';
```

Když nějaká je, **zastav se a řekni to uživateli**. Pokladnu musí zavřít člověk, protože se při
tom počítá hotovost. Upgrade zapíná přihlašování zaměstnanců (pos_hr) a s otevřenou pokladnou
se nastavení nepřepíše.

## 4. Upgrade jedním příkazem

Zastav Odoo a pusť jeden běh. Moduly, které už jsou nainstalované (`installed`), dej do `-u`,
chybějící do `-i`. Odoo si pořadí podle závislostí seřadí samo.

Nainstalované moduly obvykle jsou `elite_vet_theme`, `elite_vet_team`, `elite_vet_calendar`,
`elite_vet_web`, `elite_vet_reservation` a `elite_vet_winvet`. Nové obvykle jsou
`elite_vet_clinic`, `elite_vet_sale` a `elite_vet_reception`.

```bash
<odoo> -d <db> \
  -u elite_vet_theme,elite_vet_team,elite_vet_calendar,elite_vet_web,elite_vet_reservation,elite_vet_winvet \
  -i elite_vet_clinic,elite_vet_sale,elite_vet_reception \
  --stop-after-init 2>&1 | tee upgrade-$(date +%F-%H%M).log
```

- Když už je některý z `-i` nainstalovaný, přesuň ho do `-u`.
- **`elite_vet_reception` musí být v běhu vždy**, i když jinak upgraduješ jen `elite_vet_sale`.
  Aktualizace samotného `elite_vet_sale` (nebo kteréhokoli modulu s menu) vrátí skupiny menu na
  původní. Správná menu podle rolí nastaví zase až `elite_vet_reception`.
- Standardní moduly (`point_of_sale`, `pos_sale`, `pos_hr`, `sale_management`, `stock`,
  `product_expiry`, `l10n_cz`) si `-i` přitáhne samo. Musí být v addons Odoo 18 Community.

## 5. Kontrola logu

```bash
grep -nE " (ERROR|CRITICAL) |Traceback|invalid module names" upgrade-*.log
```

Nesmí najít nic. Když najde, Odoo nespouštěj, zastav se a pošli uživateli výpis kolem chyby.
Varování (`WARNING`) jen zapiš do zprávy.

## 6. Spustit a ověřit

Spusť Odoo (nebo restartuj kontejner) a ověř:

```bash
for p in /web/login / /rozpis-lekaru /rezervacni-system; do
  printf '%-22s %s\n' "$p" "$(curl -s -o /dev/null -w '%{http_code}' https://www.elite-vet.cz$p)"
done
```

Všechny adresy mají vrátit `200`.

```sql
-- všechny elite_vet_* jsou installed, verze odpovídají __manifest__.py
SELECT name, latest_version, state FROM ir_module_module WHERE name LIKE 'elite_vet_%' ORDER BY name;
-- nové sloupce Rozpisu služeb (ordinace a vlastní čas)
SELECT column_name FROM information_schema.columns
WHERE table_name = 'elite_vet_shift' AND column_name IN ('room_id','hour_from','hour_to');
-- menu Aplikace patří jen správci systému (musí vrátit base.group_system)
SELECT g.id FROM ir_ui_menu_group_rel r JOIN res_groups g ON g.id = r.gid
WHERE r.menu_id = (SELECT res_id FROM ir_model_data WHERE module='base' AND name='menu_management');
SELECT res_id FROM ir_model_data WHERE module='base' AND name='group_system';
-- pokladna Recepce existuje a má zapnuté přihlášení zaměstnanců
SELECT id, name, module_pos_hr FROM pos_config;
```

Výsledek poslední kontroly se skupinou menu Aplikace porovnej s `group_system`. Musí to být jen
tahle jedna skupina.

## 7. Předat uživateli (agent nedělá)

Ve zprávě uživateli vypiš tyto kroky, které udělá sám:

1. **Uživatelé** – každý, kdo otevírá pokladnu, potřebuje vyplněný e-mail. Rozdělit role
   (Recepce, Sestra, Lékařka, Vedení), potom v Nastavení › Uživatelé označit uživatele
   v seznamu a v nabídce Akce spustit **Nastavit výchozí obrazovky**.
2. **Pokladna Recepce** – zaměstnanci s PINem (pos_hr). Zavírat pokladnu může jen zaměstnanec
   s rozšířenými právy.
3. **Rozpis služeb** – u lékařek vyplnit **Výchozí ordinaci** (Rozpis služeb › Lékařky). Potom
   jednou spustit **Rozpis služeb › Převzít rozpis do rezervací**. Od té doby se služby zadávají
   jen v Rozpisu služeb (ordinace a čas Od–Do) nebo kliknutím na lékařku na Tabuli.
4. **Prohlížeče** – na pokladně a tabuli obnovit stránku natvrdo (Ctrl+Shift+R).
5. **WinVet most** (počítač na klinice) – pokladna a sklad čekají most podle smlouvy v3
   (`winvet_bridge/CONTRACT.md`). Když na klinice běží starší most, aktualizovat ho podle
   `winvet_bridge/deploy/`.

## 8. Zpráva

Pošli uživateli krátce:
- commit kódu,
- seznam modulů před upgradem a po něm (stav a verze),
- cesty k záloze a logu,
- výsledky kontrol z kroku 6,
- případná varování,
- seznam kroků z bodu 7.

## Doplnění: role bez pokladny

Pro server, na kterém už běží `master` s moduly výše (`elite_vet_sale` 18.0.1.0.1). Lékařky
a sestry přestanou vidět pokladnu a sklad; má je jen recepce (nová skupina **Pokladna a sklad
(recepce)**) a vedení. Cílový kód: `elite_vet_sale` 18.0.1.0.2.

Pravidla a záloha jako v krocích 2–3 (záloha, žádná otevřená pokladna). Pak jeden běh:

```bash
<odoo> -d <db> -u elite_vet_sale,elite_vet_reception --stop-after-init 2>&1 | tee upgrade-role-$(date +%F-%H%M).log
grep -nE " (ERROR|CRITICAL) |Traceback" upgrade-role-*.log      # nesmí nic najít
grep -n "Elite Vet till rights" upgrade-role-*.log              # počty a loginy změněných uživatelů
```

`elite_vet_clinic` se neaktualizuje (beze změny). Obě aktualizace musí být v jednom běhu
(`elite_vet_reception` nastaví menu).

**Co se změní uživatelům** (migrace proběhne jednou, ruční změny potom zůstanou):
- Recepce (nejvyšší role Recepce) dostane skupinu Pokladna a sklad (recepce) – pokladna jako dosud,
  navíc Sklad s Přehledem skladu a Příjmem zboží.
- Sestra a Lékařka (ne vedení, ne správce systému) přijdou o skupiny pokladny (uživatel, správce),
  prodejce a skladu (uživatel, správce). Ztratí menu Prodejní místa a Sklad, Příjem zboží
  a Přehled skladu v Ordinaci; `/pos/ui` jim vrátí 403. Karta pacienta, Hotovo k pokladně, stav
  platby a tabule fungují dál.
- Vedení a uživatelé bez role Elite Vet beze změny.

Kontrola (lékařka nemá žádnou skupinu pokladny; dotaz musí vrátit 0 řádků):

```sql
SELECT u.login, d.module || '.' || d.name AS group_xmlid
FROM res_users u
JOIN res_groups_users_rel r ON r.uid = u.id
JOIN ir_model_data d ON d.model = 'res.groups' AND d.res_id = r.gid
WHERE u.share IS NOT TRUE
  AND u.id IN (SELECT uid FROM res_groups_users_rel WHERE gid =
               (SELECT res_id FROM ir_model_data WHERE module = 'elite_vet_clinic' AND name = 'group_clinic_nurse'))
  AND u.id NOT IN (SELECT uid FROM res_groups_users_rel WHERE gid =
               (SELECT res_id FROM ir_model_data WHERE module = 'elite_vet_reservation' AND name = 'group_reservation_manager'))
  AND (d.module, d.name) IN (('point_of_sale', 'group_pos_user'), ('point_of_sale', 'group_pos_manager'),
                             ('elite_vet_sale', 'group_till_stock'), ('stock', 'group_stock_user'),
                             ('stock', 'group_stock_manager'), ('sales_team', 'group_sale_salesman'),
                             ('sales_team', 'group_sale_salesman_all_leads'));
```

Uživateli předej: sestra, která má přijímat zboží, potřebuje v Nastavení › Uživatelé zapnout
**Pokladna a sklad (recepce)** ručně (až po nastavení role). Na pokladně a v kartě obnovit stránku
natvrdo (Ctrl+Shift+R).

## Doplnění: ordinace

Pro server, na kterém už běží předchozí doplnění (role bez pokladny). Přibude obrazovka
**Ordinace › Ordinace** (pacienti dne podle ordinací, Nepřiřazení, Zavolat do ordinace), pole
**Ordinace** u uživatele (účet ordinace) a ordinace u záznamu návštěvy. Cílový kód:
`elite_vet_reception` 18.0.1.1.0 (`elite_vet_sale` beze změny verze, mění se jen jeho test).

Pravidla a záloha jako v krocích 2–3. Pak jeden běh:

```bash
<odoo> -d <db> -u elite_vet_reception --stop-after-init 2>&1 | tee upgrade-ordinace-$(date +%F-%H%M).log
grep -nE " (ERROR|CRITICAL) |Traceback" upgrade-ordinace-*.log      # nesmí nic najít
```

Při upgradu dostanou všechny záznamy návštěv s rezervací ordinaci z rezervace (nové uložené pole).
Neobjednaní zůstanou bez ordinace (Nepřiřazení).

**Co se změní uživatelům:**
- Recepce uvidí aplikaci **Ordinace**, ale jen s položkou Ordinace (obrazovka ordinací). Kartu
  pacienta ani záznamy návštěv nevidí.
- Lékařky, sestry a vedení mají Ordinace › Ordinace jako první položku. Klik na aplikaci Ordinace
  tedy otevře obrazovku ordinací, ne Kartu pacienta. Karta pacienta je v menu hned pod ní.
  Výchozí obrazovka sestry a lékařky zůstává Karta pacienta.
- Kopie Přehledu skladu a Příjmu zboží v aplikaci Ordinace vidí jen vedení. Recepce je má ve Skladu.
- V pokladně: Dnes › Čekárna a ordinace ukazuje ordinaci návštěvy. **+ Bez objednání** má
  nepovinné pole Ordinace.

**Co nastavit (vedení / správce):**
1. Pro každou ordinaci založit uživatele (Nastavení › Uživatelé), např. „Ordinace 1“, s e-mailem
   nebo loginem a heslem. Role **Lékařka**. V záložce Přístupová práva › **Elite Vet** vyplnit
   pole **Ordinace**. Výchozí obrazovka (Ordinace na této ordinaci) se nastaví sama.
2. Zkontrolovat **Rozpis lékařů** (Rezervace) na dnešek. Obrazovka podle něj ukazuje, kdo
   v ordinaci slouží, a podle něj zapisuje lékařku zavolaného pacienta.

Kontrola po upgradu (počet návštěv s rezervací bez ordinace; má vrátit 0, pokud všechny rezervace
ordinaci mají):

```sql
SELECT count(*) FROM elite_vet_clinical_record r JOIN elite_vet_reservation v ON v.id = r.reservation_id
WHERE r.room_id IS NULL AND v.room_id IS NOT NULL;
```

Na počítačích v ordinacích a na pokladně obnovit stránku natvrdo (Ctrl+Shift+R).
