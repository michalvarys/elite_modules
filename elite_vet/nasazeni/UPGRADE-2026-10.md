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

## Doplnění: blokace a nastavení jen správce

Pro server, na kterém už běží předchozí doplnění (ordinace). Blokace v rezervacích a nastavení
(Nastavení rezervace, Nastavení kontaktu) bude měnit jen **Správce rezervací** (vedení). Cílový
kód: `elite_vet_reservation` 18.0.2.2.0 (`elite_vet_reception` beze změny verze, mění se jen jeho
testy; `elite_vet_web` se nemění).

Pravidla a záloha jako v krocích 2–3. Pak jeden běh:

```bash
<odoo> -d <db> -u elite_vet_reservation --stop-after-init 2>&1 | tee upgrade-spravce-$(date +%F-%H%M).log
grep -nE " (ERROR|CRITICAL) |Traceback" upgrade-spravce-*.log      # nesmí nic najít
```

Data se nemění: přibudou čtyři pravidla záznamů (`security/rules.xml`), formulář blokace jen ke
čtení a skupiny u menu a akcí nastavení.

**Co se změní uživatelům:**
- Recepce, sestry, lékařky a účty ordinací: na tabuli **Rezervace › Tabule** zmizí **Nová
  blokace**, blokace nejdou přetáhnout a klik na ni ji otevře jen ke čtení. Úprava, zrušení
  nebo smazání blokace jinudy (seznam Rezervace) skončí hláškou „Blokace může měnit jen správce
  rezervací.“ Rezervace fungují jako dosud, klik do sloupce (i do blokace jen pro web) dál
  objednává. Tabule v pokladně blokace neměnila ani dřív.
- Kdo má práva správce kalendáře / webu (Hlavní stránka, Ceník), ale ne Správce rezervací:
  nevidí **Nastavení kontaktu** ani **Nastavení rezervace** a nastavení neuloží. Web nastavení
  čte dál.
- Vedení (Správce rezervací) a administrátor beze změny.

Kontrola (oba dotazy mají vrátit uvedené řádky):

```sql
-- 4 pravidla
SELECT name FROM ir_rule WHERE id IN (SELECT res_id FROM ir_model_data
  WHERE module = 'elite_vet_reservation' AND model = 'ir.rule');
-- menu a akce nastavení jen se skupinou Správce rezervací (5 řádků, group_xmlid vždy group_reservation_manager)
SELECT d.name, g.module || '.' || g.name AS group_xmlid
FROM ir_model_data d
LEFT JOIN ir_ui_menu_group_rel m ON d.model = 'ir.ui.menu' AND m.menu_id = d.res_id
LEFT JOIN ir_act_server_group_rel a ON d.model = 'ir.actions.server' AND a.act_id = d.res_id
JOIN ir_model_data g ON g.model = 'res.groups' AND g.res_id = coalesce(m.gid, a.gid)
WHERE d.module = 'elite_vet_web'
  AND d.name IN ('menu_nastaveni_root', 'menu_nastaveni_web', 'menu_rezervace_nastaveni',
                 'action_setting_otevrit', 'action_setting_rezervace');
```

Pozor: samotné `-u elite_vet_web` vrátí kořenovému menu Nastavení kontaktu skupinu správce
kalendáře. Položka pod ním zůstane jen pro Správce rezervací, takže menu zůstane skryté a zápis
blokuje pravidlo; další `-u elite_vet_reservation` skupinu srovná.

Uživateli předej: kdo z recepce zakládal blokace (oběd, porady), potřebuje je teď zadat přes
vedení, nebo mu dát skupinu **Správce rezervací** (= role Vedení). Na počítačích s tabulí obnovit
stránku natvrdo (Ctrl+Shift+R).

## Doplnění: státní svátky

Pro server, na kterém už běží předchozí doplnění (blokace a nastavení jen správce). Státní svátky
se ukazují samy všude, kde je den – nic se nezadává, nic se neblokuje (recepce je jen upozorněna,
web dál řídí nastavení **Státní svátky jen ručně**). Cílový kód: `elite_vet_calendar` 18.0.5.3.0,
`elite_vet_reservation` 18.0.2.3.0, `elite_vet_reception` 18.0.1.2.0.

Pravidla a záloha jako v krocích 2–3. Pak jeden běh:

```bash
<odoo> -d <db> -u elite_vet_calendar,elite_vet_reservation,elite_vet_reception --stop-after-init 2>&1 | tee upgrade-svatky-$(date +%F-%H%M).log
grep -nE " (ERROR|CRITICAL) |Traceback" upgrade-svatky-*.log      # nesmí nic najít
```

`-u elite_vet_calendar` aktualizuje i moduly, které na něm závisí; vyjmenované jsou kvůli
přehlednosti. Data se nemění, žádné záznamy nepřibudou. Kód svátků se přesunul do
`elite_vet_calendar/models/holidays.py` (`elite_vet_reservation/models/holidays.py` ho přebírá,
staré importy fungují). Mění se pohledy kalendářů (`js_class="elite_vet_holiday_calendar"`),
průvodce rezervací (upozornění), stránka /rozpis-lekaru a JS/CSS tabule, pokladny a webového
kalendáře.

**Co se změní uživatelům:**
- Tabule (backend i v pokladně): ve svátek červený štítek „Státní svátek: …“ u nadpisu dne
  (s „· web neobjednává“, když web ve svátky neobjednává); svátky ve dnech týdne mají tečku.
- Pokladna › Objednat: svátek v řadě dnů s nápisem „svátek“, vybrat jde; v souhrnu upozornění.
  Pokladna › Dnes: štítek u nadpisu.
- Nová rezervace (průvodce): žluté upozornění, uložit jde.
- Rozpis služeb, Rezervace › Rozpis lékařů, kalendář Rezervace: název svátku v buňce / hlavičce dne.
  Ručně zadané „Státní svátek“ v rozpisu můžou zůstat, nevadí – na webu má ručně zadaná
  celodenní poznámka přednost a svátek se neukáže dvakrát.
- Web: /rozpis-lekaru má název svátku v buňce dne; v kalendáři objednání mají svátky červenou
  tečku a název v bublině (i když web ve svátek objednává).

Kontrola po startu: tabule na 28. 10. a 17. 11. (štítek), /rozpis-lekaru (název svátku v buňce),
kalendář objednání na webu v měsíci se svátkem (tečka). Když se na /rozpis-lekaru svátek
neukáže, stránka byla upravená ve webovém editoru a má vlastní kopii pohledu – ověřit:

```sql
SELECT id, key, website_id FROM ir_ui_view WHERE key = 'elite_vet_calendar.rozpis_lekaru';
-- víc než jeden řádek = kopie z editoru; změnu je pak potřeba do kopie přenést ručně
```

Na počítačích s tabulí a na pokladnách obnovit stránku natvrdo (Ctrl+Shift+R).

## Doplnění: požadavky 25. 10.

Pro server, na kterém už běží předchozí doplnění (státní svátky). Sedm požadavků kliniky, každý
v samostatném commitu (větev `feature/elite-vet-requests-1025`). Cílový kód: `elite_vet_calendar`
18.0.5.4.0, `elite_vet_clinic` 18.0.1.1.0, `elite_vet_reservation` 18.0.2.4.0,
`elite_vet_reception` 18.0.1.3.0 (`elite_vet_sale`, `elite_vet_web` beze změny verze).

Pravidla a záloha jako v krocích 2–3 (pokladny zavřené, krok 3). Pak jeden běh:

```bash
<odoo> -d <db> -u elite_vet_calendar,elite_vet_clinic,elite_vet_reservation,elite_vet_reception --stop-after-init 2>&1 | tee upgrade-pozadavky-$(date +%F-%H%M).log
grep -nE " (ERROR|CRITICAL) |Traceback" upgrade-pozadavky-*.log      # nesmí nic najít
grep -n "block_reason:" upgrade-pozadavky-*.log                      # migrace důvodu blokace (počet)
```

Co upgrade udělá s daty:
- **Důvod blokace** přestává být překládaný (pre-migrace `elite_vet_reservation` 18.0.2.4.0):
  sloupec `block_reason` se z jsonb převede na text – zůstane česká hodnota, jinak anglická, jinak
  jakákoli vyplněná. V logu je „block_reason: N values kept as plain text“.
- Nová pole (prázdná, nic se nedopočítává): záznam návštěvy `reception_note`, `room_note`;
  rezervace `cancelled_by_id`, `cancelled_at` (vyplní se až při dalším zrušení – u starých
  zrušených je kdo a kdy v historii zpráv rezervace). Počty „Nedorazil“ se počítají za běhu.
- Nový průvodce `elite.vet.reservation.restore.wizard` (právo jen Správce rezervací), nová menu
  **Rezervace › Historie rezervací** (jen Správce rezervací). Nic se nenastavuje.

**Co se změní uživatelům:**
1. **/rozpis-lekaru:** v buňce dne jen tečka a jméno lékařky; ikony specializací jsou v bublině
   u jména (najetí myší, klik / ťuknutí na jméno, klávesnice).
2. **Poznámka recepce pro ordinaci:** Přijmout (Dnes i tabule v pokladně) otevře okno
   s nepovinnou poznámkou (Enter = Přijmout); Přijmout bez objednání má pole v Kartotéce; v Dnes
   u čekajících tlačítko Poznámka. Ordinace ji vidí žlutě (Moji pacienti dnes, obrazovka
   Ordinace, karta pacienta nahoře).
3. **Poznámka z ordinace pro recepci:** v kartě pacienta nad „Hotovo, k pokladně“ (jde měnit
   i po uzavření); v pokladně žlutě v K pokladně a v Kartotéce, Zaplatit ji nejdřív ukáže
   (Pokračovat k platbě). Obě poznámky jsou interní, na účtence ani faktuře nejsou.
4. **Blokace:** důvod napsaný s profilem v angličtině / němčině se uloží a všichni ho vidí stejně.
5. **Tabule (backend i pokladna):** přetažení rezervace nebo blokace se nejdřív zeptá
   „Přesunout … z … na …?“ (i s upozorněním na e-mail klientovi); Zrušit nic nezmění.
6. **Historie rezervací** (Správce rezervací): všechny rezervace s filtry (Zrušené, Nedorazil,
   Přesunuté, Dnes / Tento týden / Tento měsíc …), kdo a kdy zrušil, historie změn v kartě
   a tlačítko **Obnovit** u zrušené rezervace (jen když je termín volný; e-mail klientovi jen se
   zaškrtnutým „Poslat klientovi potvrzení“).
7. **Nedorazil:** počet za 12 měsíců u klienta a zvířete – tlačítko na kartě klienta / mazlíčka,
   štítek v Kartotéce pokladny, upozornění v Objednat a v průvodci Nová rezervace.

Kontrola po startu:
- /rozpis-lekaru: v buňkách nejsou ikony, najetím na jméno bublina s ikonami. Když se stránka
  nezměnila, má kopii z webového editoru (SQL u doplnění „státní svátky“ výše) – změnu je
  potřeba do kopie přenést ručně.
- Rezervace › Historie rezervací je vidět správci, recepci ne.
- Upgrade log: řádek `block_reason:` a žádná chyba.

Na počítačích s tabulí, v kartě pacienta a na pokladnách obnovit stránku natvrdo (Ctrl+Shift+R).

## Doplnění: přepínač WinVet / Elite Vet

Pro server, na kterém už běží předchozí doplnění (požadavky 25. 10.). Nové nastavení **Rezervace
na webu** přepíná stránku /rezervacni-system mezi formulářem WinVet (podle adresy) a naším
rezervačním průvodcem. Větev `feature/elite-vet-booking-switch`. Cílový kód:
`elite_vet_reservation` 18.0.2.5.0, `elite_vet_reception` 18.0.1.4.0 (ostatní moduly beze změny
verze).

Pravidla a záloha jako v krocích 2–3. Pak jeden běh:

```bash
<odoo> -d <db> -u elite_vet_reservation,elite_vet_reception --i18n-overwrite --stop-after-init 2>&1 | tee upgrade-prepinac-$(date +%F-%H%M).log
grep -nE " (ERROR|CRITICAL) |Traceback" upgrade-prepinac-*.log      # nesmí nic najít
```

`--i18n-overwrite` je potřeba kvůli přejmenovaným textům průvodce (viz níže); bez něj zůstanou
staré překlady.

Co upgrade udělá s daty:
- Nový povinný sloupec `elite_vet_setting.web_booking_source`. Stávající záznam nastavení dostane
  **`winvet`** – po upgradu je tedy na /rezervacni-system **formulář WinVet** (z pole „Adresa
  formuláře WinVet“, dosud `booking_url`), i když tam předtím byl náš průvodce. Nic jiného se
  nemění, rezervace ani žádosti z webu se nemažou.
- Agent hodnotu **nepřepíná** (pravidla: nic neměnit v datech) – přepnutí dělá uživatel (níže).

```sql
SELECT web_booking_source, booking_url FROM elite_vet_setting;   -- winvet + adresa WinVet
```

Když je `booking_url` prázdné, stránka ukáže výchozí formulář WinVet kliniky
(`…/booking/f5832eae07850edb2b5a1167843ef423`); zapiš to do zprávy, ať adresu uživatel doplní.

**Postup pro uživatele (první ostré spuštění):**
1. Po upgradu je na webu WinVet – klienti se objednávají jako dosud. Ověřit v anonymním okně:
   /rezervacni-system ukazuje rámeček WinVet s hláškou „Načítáme rezervační systém…“.
2. V klidu nastavit náš systém: Rezervace › Konfigurace (ordinace a ordinační doba, úkony,
   lékařky a specializace, rozpis), Nastavení rezervace (e-maily, limity) – kontrolní seznam
   v `elite_vet_reservation/doc/nastaveni.md`, kapitola 10. Recepce může mezitím objednávat
   v Odoo (tabule, Nová rezervace, pokladna) – to na přepínači nezávisí.
3. Přepnout: Rezervace › Konfigurace › **Nastavení rezervace** › skupina *Rezervace na webu* ›
   **Elite Vet (náš kalendář)** › Uložit (jen Správce rezervací).
4. Ověřit v anonymním okně (obnovit stránku): na /rezervacni-system jsou kroky „1 · Co
   potřebujete“ a seznam úkonů, rámeček WinVet zmizel. Volitelně zkušební žádost a kontrola, že
   dorazila do Rezervace › Čekající z webu (pak ji zrušit).
5. Návrat: stejné pole zpět na **WinVet (podle adresy)**. Náš systém pak z webu (stránka i chat)
   rezervace nepřijímá, žádosti z dřívějška v Čekajících zůstávají.

Stránka /rozpis-lekaru přepínač sleduje (viz *Navazující úpravy* níže): při WinVet je na ní
formulář WinVet jako dřív, při Elite Vet tlačítko „Objednat se online“ na /rezervacni-system.

**Další změny ve stejném upgradu:**
- Text pod rezervací (Nastavení rezervace › „Text uprostřed rámečku“, např. věta o pohotovostním
  poplatku) je pod naším průvodcem vycentrovaný v šířce průvodce; dřív na PC ležel u levého
  okraje stránky. V režimu WinVet beze změny. Kontrola: /rezervacni-system v režimu Elite Vet na
  PC – text je pod kartami úkonů uprostřed.
- Webový průvodce: první záložka „Podle problému“ se jmenuje **„Podle úkonu“** (de „Nach
  Leistung“, ru „По услуге“), stejně i věty, které na ni odkazují („Vyberte podle úkonu…“).
  „Popište problém“ ve formuláři zůstává. Potřebuje `--i18n-overwrite` (je v příkazu výše).

**Nedorazil na tabuli v pokladně** (`elite_vet_reception` 18.0.1.4.0, upgrade proto
`-u elite_vet_reservation,elite_vet_reception`): v detailu rezervace na tabuli v pokladně je
tlačítko **Nedorazil** (potvrzená rezervace z dneška nebo dřív, klient nepřijatý; ne u kopie ve
druhé ordinaci). Zeptá se „Označit … v 9:00 jako nedorazil?“ a nastaví stav Nedorazil stejně
jako tlačítko v backendu – klientovi nic neodejde, počítá se do „Nedorazil N×“. Data se upgradem
nemění. Kontrola: Pokladna › Tabule › dnešní nepřijatá rezervace › Nedorazil je v patičce okna.

**Potvrzení žádosti z webu na tabuli** (backend, `elite_vet_reservation`): přetažení žádosti
z panelu „Čekající z webu“ na tabuli i zelená tlačítka **Potvrdit → …** se nejdřív zeptají
„Potvrdit žádost Rex (Jana Nováková) na čt 29. 10. 10:00–10:20, Ordinace 1?“ (s větou
„Klient dostane potvrzovací e-mail (adresa).“, když žádost e-mail má) – **Potvrdit / Zrušit**.
Teprve Potvrdit žádost potvrdí (a pošle e-mail jako dřív). Data se nemění. Na počítačích
s tabulí obnovit stránku natvrdo (Ctrl+Shift+R).

### Navazující úpravy přepínače (26. 10.)

Větev `feature/elite-vet-switch-followups`. Cílový kód: `elite_vet_web` 18.0.1.21.0,
`elite_vet_reservation` 18.0.2.6.0 (ostatní beze změny). Když server ještě nemá doplnění výše,
stačí jeden běh s cílovým kódem obou větví; jinak:

```bash
<odoo> -d <db> -u elite_vet_web,elite_vet_reservation --i18n-overwrite --stop-after-init 2>&1 | tee upgrade-prepinac2-$(date +%F-%H%M).log
grep -nE " (ERROR|CRITICAL) |Traceback" upgrade-prepinac2-*.log     # nesmí nic najít
```

Data se nemění, hodnota přepínače zůstává, jak je. `--i18n-overwrite` kvůli novým textům na
/rozpis-lekaru (cs/de/ru).

- **Text pod rezervací vycentrovaný i u WinVetu.** Dřív ležel pod rámečkem WinVet u levého
  okraje stránky (stejná příčina jako pod naším průvodcem: `.vet-page p{margin:0}`). Hláška při
  načítání se nemění – text je během načítání uprostřed rámečku a po načtení klesne pod něj.
  Kontrola: /rezervacni-system v anonymním okně na PC, v obou režimech – text je uprostřed.
- **Text pod rezervací jde upravit i v režimu Elite Vet.** Nastavení rezervace má novou skupinu
  **Text pod rezervacemi** (pole Text), viditelnou v obou režimech. Skupina „Hláška, dokud se
  rezervace načítá“ (nadpis, druhý řádek) zůstává jen pro WinVet.
- **/rozpis-lekaru podle přepínače.** WinVet: dole formulář WinVet beze změny. Elite Vet: na jeho
  místě věta „Online objednávky přijímáme na stránce rezervačního systému.“ a tlačítko
  **Objednat se online** na /rezervacni-system (s jazykovou předponou; de „Online buchen“,
  ru „Записаться онлайн“). Kontrola: /rozpis-lekaru v anonymním okně, v režimu Elite Vet je
  dole tlačítko a žádný rámeček WinVet.

## Doplnění: kalendář z WinVetu

Záznamy kalendáře WinVetu se synchronizují do Odoo: ukážou se na tabuli (backend i pokladna) jako
„z WinVetu“, obsadí termín pro objednávání v Odoo a v pokladně v Dnes jdou přijmout. Jen jedním
směrem – most z WinVetu jen čte, Odoo do WinVetu nic nezapisuje; objednává se dál ve WinVetu.
Větev `feature/elite-vet-winvet-calendar`. Cílový kód: most **4.0.0** (kontrakt v4),
`elite_vet_winvet` 18.0.1.3.0, `elite_vet_reservation` 18.0.2.7.0, `elite_vet_reception`
18.0.1.5.0 (`elite_vet_clinic` jen soubor tabule, bez změny verze).

### Odoo

Pravidla a záloha jako v krocích 2–3. Pak jeden běh:

```bash
<odoo> -d <db> -u elite_vet_reservation,elite_vet_winvet,elite_vet_reception --stop-after-init 2>&1 | tee upgrade-kalendar-$(date +%F-%H%M).log
grep -nE " (ERROR|CRITICAL) |Traceback" upgrade-kalendar-*.log      # nesmí nic najít
```

Co upgrade udělá s daty: jen nové tabulky (`elite_vet_winvet_calendar_*`, vazby
`elite_vet_winvet_cal_event_*_rel`) a nový sloupec `elite_vet_clinical_record.winvet_event_id`
(prázdný). Rezervace, e-maily ani nastavení se nemění. Kalendář je po upgradu **zapnutý**, ale
prázdný, dokud most 4.0.0 nepošle první data. Na počítačích s tabulí obnovit stránku natvrdo
(Ctrl+Shift+R), v pokladně znovu načíst.

```sql
SELECT count(*) FROM elite_vet_winvet_calendar_event;                           -- 0 po upgradu
SELECT value FROM ir_config_parameter WHERE key = 'elite_vet_winvet.calendar_enabled';  -- žádný řádek = zapnuto
```

### Most na PC s WinVetem (dělá správce PC, ne agent)

1. Zastavit úlohy / službu mostu, nahradit složku mostu (`C:\WinVetBridge\`) obsahem
   `modules/elite_vet/winvet_bridge` z větve – **včetně `verified.json`** (nová skupina otisků
   `calendar`, ověřená pro WinVet 2603); `config.ini` a stavový soubor ponechat.
2. `py -m winvet_bridge --config config.ini check` – `bridge_version : 4.0.0`, u `calendar`
   „ok“ a `blocked : -`. Když je WinVet jiné verze než 2603 nebo `calendar` DIFFERS, kalendář je
   blokovaný (ostatní data běží dál) – předat správci integrace (README mostu, „Co dělat, když
   aktualizace WinVetu něco zablokuje“).
3. `py -m winvet_bridge --config config.ini sync --only calendar --dry-run` – vypíše počty
   (`calendar_events records=…`), nic neposílá.
4. Plán: hlavní úloha (každých 15 min) a denní plný běh beze změny – kalendář jde s nimi. Navíc
   **úloha jen pro kalendář každých 5 minut** (`sync --only calendar`, příkaz v README mostu,
   „Nespouštět novou instanci“). Služba přes NSSM (`run`) to dělá sama
   (`calendar_interval_minutes = 5`), třetí úloha tam není potřeba.
5. Volitelně do `config.ini` `[bridge]`: `calendar_days_back = 1`, `calendar_days_ahead = 60`
   (okno), `calendar_interval_minutes = 5`. Bez nich platí tyto výchozí hodnoty.

Starý most (3.x) kalendář neposílá; nový most se starým Odoo (bez kalendáře) kalendář přeskočí
s varováním („unknown entity“) a zbytek synchronizuje dál – pořadí upgradu proto nevadí.

### Kontrola po prvním běhu (vedení, Odoo)

1. **WinVet data → Stav synchronizace:** řádky Kalendáře WinVetu, Činnosti kalendáře, Záznamy
   kalendáře bez chyby.
2. **WinVet data → Kalendář z WinVetu → Kalendáře → ordinace:** „ORDINACE 1“ → Ordinace 1,
   „ORDINACE 2“ → Ordinace 2, „Sál“ → Sál, skrytý „Georgiana - sál“ bez ordinace. Jinak ordinaci
   vybrat ručně (zůstane). Kalendář bez ordinace se v Odoo nikde neukazuje a nic neblokuje.
3. **Činnosti → úkony:** volitelně – úkon jen doplní název na kartě (čas a obsazení na něm
   nezávisí).
4. **Tabule** na den s objednávkami ve WinVetu: šedé karty se štítkem WinVet ve správných
   ordinacích, celodenní záznamy jako štítky v hlavičce. Nová rezervace v Odoo na čas karty
   WinVetu musí skončit hláškou „obsazený“.
5. **Zapnout / vypnout:** počet přenesených záznamů a rozsah dnů.

Lokální ověření (analytická kopie WinVetu, 25. 10.): kalendáře 4, činnosti 44 (11 se samo
spárovalo s úkonem), záznamy 203 v okně 24. 10. – 24. 12. (166 s časem, 37 celodenních,
139 výskytů opakovaných záznamů, 23 se zvířetem z kartotéky); druhý běh nic nezměnil.

### Jak kalendář z WinVetu vypnout (přechod na objednávání v Odoo)

Až se bude objednávat jen v Odoo: **WinVet data → Kalendář z WinVetu → Zapnout / vypnout →
Vypnout kalendář z WinVetu** (Vedení). Karty WinVet zmizí z tabule i z Dnes, nic neblokují
a další záznamy z mostu se neukládají. **Smazat přenesené záznamy** je pak vymaže (ve WinVetu
zůstanou). Na PC s WinVetem potom smazat úlohu „WinVet bridge - kalendar“ (běžné běhy kalendář
dál posílají, Odoo ho ignoruje). Zpět: tlačítko **Zapnout**, další běh mostu okno znovu naplní.

## Doplnění: všechna pole zvířete

Kartotéka v pokladně má ve formuláři zvířete všechna pole zvířete (povinné jen jméno a druh):
Jiný druh, sbalovací **Další údaje** (rok narození, hmotnost, barva, tetování, číslo pasu, příští
vakcinace a odčervení, Důležité, poznámka), **Upozornění** (přidat / odebrat) a při úpravě
**Uhynulý** + datum úhynu. Větev `feature/elite-vet-pet-form`. Cílový kód: `elite_vet_reception`
18.0.1.6.0 (ostatní moduly beze změny).

Pravidla a záloha jako v krocích 2–3. Pak jeden běh:

```bash
<odoo> -d <db> -u elite_vet_reception --stop-after-init 2>&1 | tee upgrade-pole-zvirete-$(date +%F-%H%M).log
grep -nE " (ERROR|CRITICAL) |Traceback" upgrade-pole-zvirete-*.log      # nesmí nic najít
```

Data se nemění, žádné tabulky ani sloupce nepřibudou (pole zvířete už existují), práva se
nemění: upozornění recepce dál jen čte a zapisuje je jen API Kartotéky po kontrole role (odebrání
= archivace jako v kartě pacienta). Mění se jen Python API (`save_pet`, `owner_data`,
`pet_options`) a JS/CSS pokladny – v pokladně znovu načíst (Ctrl+Shift+R).

Kontrola po startu: Kartotéka → klient → **+ Nové zvíře** (Další údaje zavřené, Uhynulý není),
**Upravit** u zvířete s hmotností z WinVetu (Další údaje otevřené, hmotnost s čárkou). Recepci
připomenout: u zvířat z WinVetu přenos dál přepisuje pole, která má i WinVet (seznam v návodu
recepce, kapitola 3 „Souběh s WinVetem“) – měnit je i ve WinVetu.

## Doplnění: účty členů týmu

Každý člen týmu (Rozpis služeb › Lékařky) může mít vlastní účet, propojený ve sloupci **Účet**.
Propojená lékařka / sestra začíná na obrazovce Ordinace na ordinaci své dnešní služby, lékařka se
zapisuje k pacientům, které zavolá nebo vezme do ordinace, Moji pacienti dnes jsou podle propojení.
Lékařka s vlastním účtem, která v záznamu návštěvy něco změní, se zapíše jako ošetřující („Ošetřuje:“
v kartě pacienta). Vedení zakládá účty průvodcem **Vytvořit účty**. Větev
`feature/elite-vet-member-accounts`. Cílový kód: `elite_vet_calendar` 18.0.5.5.0, `elite_vet_clinic`
18.0.1.3.0, `elite_vet_reception` 18.0.1.8.0 (nově závisí na `auth_signup`, který je v Odoo
nainstalovaný vždy).

Pravidla a záloha jako v krocích 2–3. Pak jeden běh:

```bash
<odoo> -d <db> -u elite_vet_calendar,elite_vet_clinic,elite_vet_reception --stop-after-init 2>&1 | tee upgrade-ucty-tymu-$(date +%F-%H%M).log
grep -nE " (ERROR|CRITICAL) |Traceback" upgrade-ucty-tymu-*.log      # nesmí nic najít
```

Přibudou sloupce `elite_vet_doctor.user_id` (s unikátním omezením) a
`elite_vet_clinical_record.doctor_auto` (u starých záznamů prázdný = lékařka se bere jako vybraná),
tabulka `elite_vet_clinical_record_other_doctor_rel` (Upravovaly také), dva přechodné modely
průvodce a jejich práva (jen Vedení). Data se nemění: nikdo zatím propojený není, takže se nic nechová jinak, dokud se účty
nepropojí. Na počítačích obnovit stránku natvrdo (Ctrl+Shift+R).

**Jak založit účty (vedení, po upgradu):**
1. Rozpis služeb › **Lékařky** › tlačítko **Vytvořit účty**.
2. Zkontrolovat řádky: přihlašovací jméno (e-mail z karty v Náš tým; prázdné doplnit nebo řádek
   nechat nezaškrtnutý), roli (Lékařka u lékařek s rezervacemi, jinak Sestra – recepci přepnout
   na Recepce), zaškrtnutí **Vytvořit**.
3. **Hesla** – jedna ze dvou cest:
   - nechat **Poslat pozvánku e-mailem** vypnuté a heslo nastavit v Nastavení › Uživatelé › účet ›
     Akce › **Změnit heslo** (sdělit osobně; Odoo 18 přitom samo zařadí do fronty e-mail
     „Security Update: Password Changed“ na e-mail účtu – to je standard Odoo, ne tento modul), nebo
   - zaškrtnout **Poslat pozvánku e-mailem**: každý dostane standardní pozvánku Odoo s odkazem na
     nastavení hesla (zařadí se do fronty e-mailů a odejde s nejbližším během odesílání, odkaz platí
     podle `auth_signup.signup_validity_hours`, výchozí 6 dní). Musí fungovat odchozí pošta.
4. **Vytvořit účty** – zpráva řekne, kolik účtů vzniklo a kolik řádků se přeskočilo.
5. Existující účet (např. založený dřív ručně) propojit přímo ve sloupci **Účet**; průvodce takový
   řádek nenabízí, pokud už propojený je, a odmítne přihlašovací jméno, které už má jiný účet.

Kontrola: přihlásit se jedním novým účtem lékařky v den, kdy má v Rozpisu lékařů službu → otevře se
Ordinace na její ordinaci; Moji pacienti dnes ukazují její rezervace; po zápisu do anamnézy
dnešního pacienta bez vybrané lékařky karta ukáže „Ošetřuje: <ona>“. Účty ordinací se nemění.

```sql
SELECT d.name, u.login FROM elite_vet_doctor d JOIN res_users u ON u.id = d.user_id ORDER BY d.name;
```

## Doplnění: web vs klinika v kalendáři

Na tabuli (backend i Tabule v pokladně) je u každé rezervace vidět, odkud je: modrý štítek
**WEB** a modrý čárkovaný obrys = z webu (i z chatu na webu), bílý štítek s **iniciálami** =
založil(a) někdo z kliniky (najetím jméno a čas), šedý **WinVet** = z WinVetu. Pod lištou tabule
je legenda a přepínač **Vše | Web | Klinika** (pamatuje si ho prohlížeč; WinVet jen ve „Vše“).
Seznamy Rezervace a Historie rezervací mají sloupce **Zdroj** a **Založil(a)**, filtry
**Z webu** / **Z kliniky** a seskupení podle Zdroje; pokladna › Dnes › Přicházejí má štítek WEB.
Hodnota zdroje „Interně“ se přejmenovala na **Klinika**. Větev `feature/elite-vet-source-visible`.
Cílový kód: `elite_vet_reservation` 18.0.2.8.0, `elite_vet_reception` 18.0.1.9.0.

Pravidla a záloha jako v krocích 2–3. Pak jeden běh:

```bash
<odoo> -d <db> -u elite_vet_reservation,elite_vet_reception --stop-after-init 2>&1 | tee upgrade-web-klinika-$(date +%F-%H%M).log
grep -nE " (ERROR|CRITICAL) |Traceback" upgrade-web-klinika-*.log      # nesmí nic najít
```

Žádné tabulky ani sloupce nepřibudou, data se nemění: „Založil(a)“ je počítané z `create_uid`
(jen interní uživatelé), zdroj už u rezervací je (web zakládá jen `/rezervace/api/submit`,
který používá formulář i chat). Mění se pohledy, popisek výběru zdroje a JS/CSS tabulí – na
počítačích i v pokladně obnovit stránku natvrdo (Ctrl+Shift+R).

Kontrola: Rezervace › Tabule na dni s webovou i klinickou rezervací → WEB s obrysem / iniciály,
legenda, přepínač Web skryje klinické a WinVet („skryto: N“); Rezervace › seznam → sloupce Zdroj
a Založil(a), filtr Z webu.

```sql
SELECT source, count(*) FROM elite_vet_reservation WHERE kind = 'reservation' GROUP BY source;
```

## Doplnění: opravy 26. 10.

Tři opravy z testování (větev `feature/elite-vet-fixes-1026`). Cílový kód:
`elite_vet_calendar` 18.0.5.6.0, `elite_vet_reservation` 18.0.2.9.0, `elite_vet_reception` 18.0.1.10.0.

1. **Potvrzení žádosti z webu lékařkou (i recepcí a sestrou).** Žádost s e-mailem, který patří
   uživateli Odoo (člen týmu si objedná vlastní zvíře – od účtů členů týmu má každá lékařka
   e-mail jako přihlašovací jméno), se spárovala s kontaktem toho uživatele a označení „klient“
   na něm směl změnit jen správce práv → potvrzení skončilo chybou „You are not allowed to
   modify 'User'“. Teď se nastaví jen tento příznak (sudo). Rozpis služeb a Rozpis lékařů dál
   mění jen správce rozpisu / Správce rezervací.
2. **Okno přesunu a potvrzení** (tabule v backendu i v pokladně, potvrzení žádosti z webu):
   políčka **Datum**, **Čas** (po krocích rezervací) a **Ordinace** předvyplněná z puštění,
   opravitelná; hláška „obsazeno / neslouží lékařka“ zůstane v okně. Zaškrtávátko **Poslat
   klientovi e-mail o změně** / **Poslat klientovi potvrzení** (výchozí zaškrtnuté, jen když by
   e-mail odešel); odškrtnuté = jen tato změna bez e-mailu, v historii rezervace „Klient nebyl
   o změně (potvrzení) informován.“
3. **/rozpis-lekaru v menším zobrazení** (do 900 px a dotykové displeje): pod jménem jen čas
   od–do, nad každým měsícem krátká legenda barev; bubliny a celodenní poznámky beze změny.

Pravidla a záloha jako v krocích 2–3. Pak jeden běh:

```bash
<odoo> -d <db> -u elite_vet_calendar,elite_vet_reservation,elite_vet_reception --stop-after-init 2>&1 | tee upgrade-opravy-1026-$(date +%F-%H%M).log
grep -nE " (ERROR|CRITICAL) |Traceback" upgrade-opravy-1026-*.log      # nesmí nic najít
```

Žádné tabulky ani sloupce nepřibudou, data se nemění. Mění se šablona stránky /rozpis-lekaru
(záznam modulu, ne kopie z editoru webu – zkontrolujte, že `elite_vet_calendar.rozpis_lekaru`
nemá kopii s jiným `website_id`), JS/CSS tabulí a pokladny – na počítačích i v pokladně obnovit
stránku natvrdo (Ctrl+Shift+R).

Kontrola:
- uživatel s rolí Lékařka: Rezervace › Tabule → přetáhnout žádost z webu do ordinace → okno
  s datem, časem a ordinací → opravit čas → **Potvrdit**; tlačítko „+ služba“ ani klik na pruh
  lékařky se jí nenabízí;
- přesun potvrzené rezervace s e-mailem na jiný čas s odškrtnutým e-mailem → v historii
  „Klient nebyl o změně informován.“, ve frontě e-mailů nic nového;
- /rozpis-lekaru na mobilu → pod jmény jen „8:00–14:00“, nad měsícem barvy s názvy směn.

```sql
SELECT key, website_id FROM ir_ui_view WHERE key = 'elite_vet_calendar.rozpis_lekaru';
SELECT m.date, m.body FROM mail_message m
 WHERE m.model = 'elite.vet.reservation' AND m.body LIKE '%nebyl o%informován%' ORDER BY m.id DESC LIMIT 10;
```

## Doplnění: zpráva z vyšetření

Tisk zprávy z vyšetření pro majitele bez interních poznámek (větev
`feature/elite-vet-visit-report`). Cílový kód:
- `elite_vet_calendar` 18.0.5.7.0
- `elite_vet_clinic` 18.0.1.4.0
- `elite_vet_sale` 18.0.1.1.0
- `elite_vet_reception` 18.0.1.11.0

Co přibude:
- PDF **Zpráva z vyšetření**:
  - v kartě pacienta tlačítko **Zpráva pro majitele** a ikona tiskárny v historii;
  - Tisk u záznamu návštěvy;
  - ikona v pokladně › Dnes › K pokladně.
- Pole **Číslo KVL** u lékařky. Návod: `elite_vet_reception/doc/ordinace.md`, kapitola 8.

Pravidla a záloha jako v krocích 2–3. Pak jeden běh:

```bash
<odoo> -d <db> -u elite_vet_calendar,elite_vet_clinic,elite_vet_sale,elite_vet_reception --stop-after-init 2>&1 | tee upgrade-zprava-$(date +%F-%H%M).log
grep -nE " (ERROR|CRITICAL) |Traceback" upgrade-zprava-*.log      # nesmí nic najít
```

Přibude jeden sloupec, `elite_vet_doctor.kvl_number` (prázdný), a záznamy reportu a jeho
paperformatu. Ostatní data se nemění. Po aktualizaci obnovte stránku natvrdo (Ctrl+Shift+R),
na počítačích i v pokladně.

Po aktualizaci (vedení):
1. **Rozpis služeb › Lékařky**: vyplňte u každé lékařky **Číslo KVL**. Bez čísla se ve zprávě
   tiskne jen jméno.
2. **Nastavení › Společnosti**, vaše společnost:
   - název kliniky, jak se má tisknout (teď je tam „My Company“);
   - adresa, **IČO** (Identifikační číslo společnosti) a **DIČ**;
   - telefon, e-mail, web;
   - **logo**. Bez vlastního loga zpráva logo nemá. Telefon, e-mail a adresu bez vyplnění vezme
     zpráva z Nastavení webu.
3. Odoo musí PDF vytvořit (wkhtmltopdf je v obrazu odoo:18). Server musí umět stáhnout styly sám
   ze sebe: když PDF vyjde bez formátování, nastavte systémový parametr `report.url` na adresu, na
   které Odoo uvnitř serveru odpovídá (např. `http://localhost:8069`).

Kontrola:
- otevřete kartu pacienta s dnešním záznamem → **Zpráva pro majitele**. Otevře se PDF s hlavičkou
  kliniky, pacientem, majitelem, lékařkou s číslem KVL a vyplněnými oddíly;
- ověřte, že ve zprávě **není** poznámka recepce, poznámka pro recepci, upozornění ani ceny;
- Ordinace › Záznamy návštěv → záznam → Tisk › Zpráva z vyšetření → stáhne se
  `Zprava_<zvíře>_<datum>.pdf`;
- u zaplaceného účtu s lékem ze skladu je ve zprávě šarže a exspirace.

```sql
SELECT id, name, kvl_number FROM elite_vet_doctor WHERE active ORDER BY name;
SELECT report_name, binding_model_id FROM ir_act_report_xml WHERE report_name = 'elite_vet_clinic.report_visit_document';
```

## Doplnění: vzhled ordinací (úkol 26)

Moduly: `elite_vet_clinic` (18.0.1.5.0) a `elite_vet_reception` (18.0.1.12.0).

```bash
docker compose stop odoo
docker compose run --rm odoo odoo -d DATABAZE -u elite_vet_clinic,elite_vet_reception --stop-after-init --no-http
docker compose start odoo
```

Schéma se nemění (žádný nový sloupec), mění se jen vzhled a přibývá metoda `take_next_patient`
(tlačítko **Vzít dalšího**). Po aktualizaci obnovte stránku natvrdo (Ctrl+Shift+R) na všech
počítačích a tabletech v ordinacích.

Kontrola:
- Ordinace › Ordinace › jedna ordinace: nahoře název, kdo slouží, přepínač ordinací vpravo;
  sloupce Čekají | V ordinaci | Dnes ještě přijdou; u čekajícího Zavolat a nabídka „…“;
- když čeká někdo bez ordinace, oranžový pruh s **Vzít dalšího** a **Zobrazit**;
- Všechny ordinace: souhrn nahoře, přetažení pacienta do jiné ordinace funguje;
- karta pacienta: větší písmo, velká pole vitálních hodnot, štítek „V ordinaci od …“ v záhlaví;
- Moji pacienti dnes: stejné dlaždice pacientů jako na obrazovce Ordinace.

Návod s obrázky: `elite_vet_reception/doc/ordinace.md` (kapitoly 2–4 a 7).

## Doplnění: zpětná vazba 26. 10.

Větev `feature/elite-vet-feedback-1026b`. Cílový kód:
- `elite_vet_clinic` 18.0.1.6.0 (zpráva „lékař/ka“, zpráva z návštěvy z WinVetu, záhlaví karty
  a šířka sloupců);
- `elite_vet_reservation` 18.0.2.10.0 (okno přesunu / potvrzení s časem **Do**);
- `elite_vet_reception` 18.0.1.13.0 (totéž okno na tabuli v pokladně).

Schéma se nemění (žádný nový sloupec). Přibude jen záznam reportu „Zpráva z vyšetření“ pro
návštěvy z WinVetu. Pravidla a záloha jako v krocích 2–3, pak:

```bash
docker compose stop odoo
docker compose run --rm odoo odoo -d DATABAZE -u elite_vet_reservation,elite_vet_clinic,elite_vet_reception --stop-after-init --no-http 2>&1 | tee upgrade-1026b-$(date +%F-%H%M).log
grep -nE " (ERROR|CRITICAL) |Traceback" upgrade-1026b-*.log      # nesmí nic najít
docker compose start odoo
```

Po aktualizaci obnovte stránku natvrdo (Ctrl+Shift+R) na počítačích, tabletech i v pokladně.

Kontrola:
- tabule rezervací: přetáhněte rezervaci → v okně jsou **Datum**, **Od**, **Do**, **Ordinace**;
  změna **Do** rezervaci prodlouží / zkrátí, věta „na …“ ukazuje oba časy; obsazený čas
  v prodloužení okno odmítne a nechá otevřené;
- stejné okno v pokladně › Tabule a u potvrzení žádosti z webu;
- formulář rezervace: po změně Začátku se Konec posune se stejnou délkou a dá se přepsat;
- karta pacienta: záhlaví na dva řádky; při šířce 1280 px a víc jde přetáhnout dělič mezi
  sloupci, dvojklik vrátí šířku, po obnovení stránky šířka zůstane;
- karta pacienta › Historie: u návštěvy z WinVetu je ikona tisku → PDF s měřením, textem
  záznamu, diagnózou a položkami **bez cen**; ve zprávě je „Ošetřující lékař/ka“ a „Podpis
  a razítko lékaře/ky“. Uživatele WinVetu propojte s lékařkami (WinVet data › Uživatelé WinVet),
  jinak zpráva z WinVetu lékařku neuvede.

```sql
SELECT report_name, model FROM ir_act_report_xml WHERE report_name LIKE 'elite_vet_clinic.report_%visit%';
SELECT name, latest_version FROM ir_module_module WHERE name IN ('elite_vet_reservation','elite_vet_clinic','elite_vet_reception');
```

## Doplnění: zrušení přijetí

Větev `feature/elite-vet-undo-check-in`. Cílový kód `elite_vet_reception` 18.0.1.14.0: v pokladně
› Dnes u pacienta, který **čeká**, tlačítko **Zrušit přijetí** (přijato omylem). Objednaný se vrátí
mezi Přicházejí, neobjednaný z čekárny zmizí; návštěva zůstane jako Zrušeno s poznámkou
v chatteru. Jde to jen dnes, než pacienta zavolají a než v návštěvě něco je.

Schéma se nemění. Pravidla a záloha jako v krocích 2–3, pak:

```bash
docker compose stop odoo
docker compose run --rm odoo odoo -d DATABAZE -u elite_vet_reception --stop-after-init --no-http 2>&1 | tee upgrade-undo-$(date +%F-%H%M).log
grep -nE " (ERROR|CRITICAL) |Traceback" upgrade-undo-*.log      # nesmí nic najít
docker compose start odoo
```

Po aktualizaci obnovte pokladnu natvrdo (Ctrl+Shift+R).

Kontrola: přijměte zkušební rezervaci → v Čekárně a ordinaci je u ní **Zrušit přijetí** → potvrďte
→ rezervace je zase v Přicházejí a jde znovu přijmout. U pacienta **V ordinaci** tlačítko není.

```sql
SELECT name, latest_version FROM ir_module_module WHERE name = 'elite_vet_reception';
```

## Doplnění: spárování objednávek z WinVetu

Větev `feature/elite-vet-winvet-pairing`. Cílový kód `elite_vet_winvet` 18.0.1.4.0 a
`elite_vet_reception` 18.0.1.15.0: v pokladně › Dnes jsou v Přicházejí **všechny** dnešní
objednávky z WinVetu, i ty jen s textem (štítek **bez karty**). Recepce je spáruje s kartou
(**Spárovat…** → Kartotéka → **Přiřadit k objednávce**) a pak přijme. Totéž je na obrazovce
Ordinace v nabídce … u objednávky bez karty. Spárování je jen v Odoo, do WinVetu se nezapisuje.

Schéma: nová pole na `elite_vet_winvet_calendar_event` (`manual_pet_id`, `manual_partner_id`,
`matched_by_id`, `matched_at`, uložená počítaná `effective_pet_id`, `effective_partner_id` –
při aktualizaci se dopočítají pro všechny přenesené záznamy). Pravidla a záloha jako v krocích
2–3, pak (oba moduly v jednom běhu):

```bash
docker compose stop odoo
docker compose run --rm odoo odoo -d DATABAZE -u elite_vet_winvet,elite_vet_reception --stop-after-init --no-http 2>&1 | tee upgrade-pairing-$(date +%F-%H%M).log
grep -nE " (ERROR|CRITICAL) |Traceback" upgrade-pairing-*.log      # nesmí nic najít
docker compose start odoo
```

Po aktualizaci obnovte pokladnu i backend natvrdo (Ctrl+Shift+R).

Kontrola: v Dnes › Přicházejí je objednávka z WinVetu jen s textem se štítkem **bez karty**
a tlačítkem **Spárovat…** → spárujte ji se zkušebním zvířetem → řádek má zvíře a **Přijmout** →
**Zrušit spárování** ji vrátí. Opravdové objednávky klientů nepárujte zkušebními zvířaty.

```sql
SELECT name, latest_version FROM ir_module_module
 WHERE name IN ('elite_vet_winvet', 'elite_vet_reception');
SELECT count(*) AS sparovano FROM elite_vet_winvet_calendar_event WHERE manual_pet_id IS NOT NULL;
```

**Tip pro kliniku:** ve WinVetu při objednávání vždy vyberte pacienta (nejen text). Taková
objednávka se v Odoo spáruje sama.

Ve stejné větvi (stejný `-u`, jen vzhled): obrazovka Ordinace a Moji pacienti dnes mají pořadí
**Dnes jsou objednaní** (dřív „Dnes ještě přijdou“, s řádkem „ještě nepřišli“) | **Čekají** |
**V ordinaci**, Hotovo dnes sbalené pod posledním. Na užší obrazovce (pod 1100 px) jsou pod sebou
s Čekají první.

## Doplnění: 26. 10. odpoledne

Větev `feature/elite-vet-1026c`. Cílový kód `elite_vet_reception` 18.0.1.16.0, schéma se nemění
(jen obrazovky a jedna metoda):

- **Všechny ordinace:** ordinace s pacienty mají široké sloupce (aspoň 360 px), ordinace a
  Nepřiřazení bez nikoho jsou úzké („nikdo“). Když se sloupce nevejdou, tabule se posouvá do
  strany, hlavičky zůstávají nahoře, dlouhé texty z WinVetu jsou zkrácené (celý text najetím myší).
- **Kartotéka › + Nový klient:** celý formulář zvířete (Další údaje, Upozornění); klient a zvíře
  se uloží najednou (`save_owner` s údaji zvířete – když zvíře neprojde kontrolou, nezaloží se ani
  klient). Tlačítko **Uložit klienta**, ve Spárovat… se zvířetem **Uložit a přiřadit k objednávce**.

Pravidla a záloha jako v krocích 2–3, pak:

```bash
docker compose stop odoo
docker compose run --rm odoo odoo -d DATABAZE -u elite_vet_reception --stop-after-init --no-http 2>&1 | tee upgrade-1026c-$(date +%F-%H%M).log
grep -nE " (ERROR|CRITICAL) |Traceback" upgrade-1026c-*.log      # nesmí nic najít
docker compose start odoo
```

Po aktualizaci obnovte pokladnu i backend natvrdo (Ctrl+Shift+R).

Kontrola: Ordinace › Všechny ordinace – prázdné ordinace jsou úzké, při mnoha obsazených se
tabule posouvá do strany. Pokladna › Kartotéka… › + Nový klient – pod klientem je celý formulář
zvířete s Další údaje (formulář jen otevřete a zavřete Zrušit – zkušebního klienta v ostré
databázi nezakládejte).

```sql
SELECT name, latest_version FROM ir_module_module WHERE name = 'elite_vet_reception';
```

## Doplnění: jeden záznam z vyšetření

Větev `feature/elite-vet-one-record-text`. Cílový kód `elite_vet_clinic` **18.0.1.7.0** (má
migraci), `elite_vet_reception` bez změny verze (jen kód):

- **Karta pacienta:** místo tří polí Anamnéza / Vyšetření / Diagnóza a doporučení je jedno velké
  pole **Záznam z vyšetření** s jedním tlačítkem **Šablona**. Šablona se vloží celá na místo
  kurzoru, bez kurzoru na konec za prázdný řádek; nic nepřepíše. Nabízejí se všechny šablony
  (oddíl šablony už nerozhoduje a ve formuláři šablony není).
- **Zpráva z vyšetření:** jeden oddíl „Záznam z vyšetření“ (řádek vitálních hodnot a text).
- Historie karty, ošetřující lékařka, Zrušit přijetí, seznamy, formulář a vyhledávání
  v Ordinace › Záznamy návštěv berou jen nové pole.

**Co migrace udělá s existujícími záznamy** (při `-u elite_vet_clinic`, jednou):
- Záznam, který má nové pole prázdné a aspoň jeden starý text, dostane do nového pole:
  - jen vyplněné části, každou s nadpisem na vlastním řádku („Anamnéza:“, „Vyšetření:“,
    „Diagnóza a doporučení:“), mezi částmi prázdný řádek;
  - když je vyplněná jediná část, jen její text bez nadpisu.
- Staré texty zůstávají v databázi beze změny (nikde se už neukazují), takže se nic neztratí.
- Píše se přímo SQL: v historii záznamu (chatter) se nic neobjeví, datum poslední změny zůstává.
- Záznam bez textu se nemění. Druhé spuštění nic nezmění (záznam s novým textem se přeskočí).

Pravidla a záloha jako v krocích 2–3, pak:

```bash
docker compose stop odoo
docker compose run --rm odoo odoo -d DATABAZE -u elite_vet_clinic,elite_vet_reception --stop-after-init --no-http 2>&1 | tee upgrade-1027-zaznam-$(date +%F-%H%M).log
grep -nE " (ERROR|CRITICAL) |Traceback" upgrade-1027-zaznam-*.log      # nesmí nic najít
grep -n "record_text filled" upgrade-1027-zaznam-*.log                # kolik záznamů migrace spojila
docker compose start odoo
```

Po aktualizaci obnovte backend natvrdo (Ctrl+Shift+R).

Kontrola (jen čtení):

```sql
SELECT name, latest_version FROM ir_module_module WHERE name = 'elite_vet_clinic';   -- 18.0.1.7.0
-- záznamy se starým textem, ale bez nového pole: musí být 0
SELECT count(*) FROM elite_vet_clinical_record
 WHERE coalesce(btrim(record_text), '') = ''
   AND (coalesce(btrim(anamnesis), '') <> '' OR coalesce(btrim(examination), '') <> ''
        OR coalesce(btrim(diagnosis), '') <> '');
```

Pak otevřete kartu pacienta s dřívější návštěvou: v historii je text návštěvy v jednom bloku
s nadpisy. Šablonu v ostré databázi nevkládejte (zapsala by se do záznamu).

## Doplnění: upozornění pro kliniku na rezervace@ (27. 10.)

`-u elite_vet_reservation`. Upozornění klinice (nová žádost z webu, zrušení klientem) chodí na
`rezervace@elite-vet.cz`: upgrade přepíše jen původní výchozí `info@elite-vet.cz`, ručně nastavenou
jinou adresu nechá. Nový vypínač **Posílat klinice upozornění** (Rezervace › Konfigurace ›
Nastavení rezervace) – vypnuté = klinice nechodí nic, klientům e-maily chodí dál.
Kontrola: `SELECT booking_notify_enabled, booking_notify_email FROM elite_vet_setting;`

## Doplnění: laboratorní výsledky z WinVetu jako tabulka (27. 10.)

Výsledky krve z WinVetu (ProCyte apod.) se v historii karty i ve zprávě z vyšetření rozpadaly na
jednu hodnotu na řádek. Most je teď skládá zpět po řádcích (parametr, výsledek, jednotka, meze)
a Odoo je zobrazí i vytiskne jako tabulku. Větev `feature/elite-vet-winvet-tables`.

1. **Odoo:** `-u elite_vet_clinic` (bez migrace, jen zobrazení), pak v prohlížeči Ctrl+Shift+R.
2. **Most na PC s WinVetem:** nahradit složku mostu obsahem `modules/elite_vet/winvet_bridge`
   (`config.ini`, stav a `verified.json` beze změny). `check` ukáže `bridge_version : 4.0.1`.
3. **Jednou plný běh** `py -m winvet_bridge --config config.ini sync --full` – přepíše texty
   už přenesených návštěv (jinak se opraví až při další změně návštěvy ve WinVetu). Na lokální
   kopii z 26. 10.: 1265 návštěv, z toho 526 s tabulkou.

Kontrola: karta pacienta s krevním vyšetřením z WinVetu → v historii rozbalit návštěvu – tabulka
Metoda / Výsledek / Jednotka / Dolní mez / Horní mez; tisk zprávy totéž.

## Doplnění: forma úhrady v tržbách WinVetu (27. 10.)

V **WinVet data → Tržby** (položky) a **Doklady** jde seskupit i filtrovat podle **Formy úhrady**
(Hotově / Kartou / Převodem / Kombinovaně / Bez úhrady); sloupec je i v seznamech. Účet majitele
(UM) a jeho položky přebírají formu z platby navázaného příjmového dokladu (PODP); platba 0 Kč =
bez úhrady. Upgrade: `-u elite_vet_winvet` (18.0.1.5.0) – nová uložená pole se dopočítají při
upgradu, most se nemění.

## Doplnění: uzávěrka z WinVetu

**WinVet data → Tržby → Uzávěrka** vytiskne pokladní uzávěrku za období (Tento měsíc / Minulý měsíc /
Dnes / Včera / jiné od–do) jako PDF: tržby podle dokladů, přijaté platby a vratky podle formy úhrady,
denní rozpis, faktury a doklady bez úhrady, zálohy a tržby podle položek × forma úhrady, podpisy
Předal/a – Převzal/a. Nově se z WinVetu přenášejí **zálohy klientů** (WinVet data → Zálohy, na kontaktu
tlačítko a záložka Zálohy, na kartě pacienta a v Kartotéce řádek „Záloha: 2 000 Kč“). Jen vedení.
Větev `feature/elite-vet-cash-closure`. Cílový kód: most **5.0.0** (kontrakt v5),
`elite_vet_winvet` 18.0.1.6.0, `elite_vet_clinic` 18.0.1.8.0, `elite_vet_reception` 18.0.1.17.0.

### Odoo

Pravidla a záloha jako v krocích 2–3. Pak jeden běh:

```bash
<odoo> -d <db> -u elite_vet_winvet,elite_vet_clinic,elite_vet_reception --stop-after-init 2>&1 | tee upgrade-uzaverka-$(date +%F-%H%M).log
grep -nE " (ERROR|CRITICAL) |Traceback" upgrade-uzaverka-*.log      # nesmí nic najít
```

Co upgrade udělá s daty: nové tabulky `elite_vet_deposit`, `elite_vet_deposit_use` (prázdné, dokud
most 5.0.0 nepošle data), nový sloupec `elite_vet_sale_document.recorded_method` (prázdný). Nic
existujícího se nemění. V pokladně a v Ordinacích obnovit stránku natvrdo (Ctrl+Shift+R).

### Most na PC s WinVetem (dělá správce PC, ne agent)

1. Zastavit úlohy / službu mostu, nahradit složku mostu (`C:\WinVetBridge\`) obsahem
   `modules/elite_vet/winvet_bridge` z větve – **včetně `verified.json`**: přibyla skupina otisků
   `deposits` a změnily se otisky `sales` (most čte `DOKLAD.FORMA_UHRADY`) a `journal` (triggery žurnálu
   u `PARTNER_ZALOHA`), vše ověřené pro WinVet 2603. Se starým `verified.json` by most zablokoval tržby
   i zálohy. `config.ini` a stavový soubor ponechat.
2. `py -m winvet_bridge --config config.ini check` – `bridge_version : 5.0.0`, u `deposits`, `sales`
   a `journal` „ok“, `blocked : -`. Jinak předat správci integrace (README mostu).
3. **Jednou plný běh** `py -m winvet_bridge --config config.ini sync --full` – pošle všechny zálohy,
   čerpání a formu úhrady na všech dokladech (bez něj by forma přibývala jen u měněných dokladů).
4. Plán úloh beze změny. Starý most (4.x) zálohy neposílá (Odoo je jen nemá); nový most se starým
   Odoo zálohy přeskočí („unknown entity“) – pořadí upgradu nevadí. Jde-li data ze SFTP zálohy na
   serveru, zkopírovat nový most i `verified.json` i do `/opt/winvet-import/` (README `deploy/sftp`).

### Kontrola (vedení, Odoo)

1. **WinVet data → Stav synchronizace:** řádky Zálohy a Čerpání záloh bez chyby.
2. **WinVet data → Zálohy** (filtr S zůstatkem): součty Přijato / Čerpáno / Vráceno / Zůstatek.
3. **WinVet data → Tržby → Uzávěrka → Minulý měsíc → Vytisknout PDF.**

```sql
SELECT count(*), sum(amount), sum(used), sum(refunded), sum(balance) FROM elite_vet_deposit;
SELECT count(*), sum(amount) FROM elite_vet_deposit_use;
SELECT recorded_method, count(*) FROM elite_vet_sale_document GROUP BY 1;
```

Lokální ověření (analytická kopie z 26. 10., ev_test): zálohy 38, čerpání 34, doklady s formou 1134
z 2235. Září 2026 sedí s ruční uzávěrkou: nové úhrady hotově / kartou / převodem, zálohy 4 000 hotově
+ 15 000 kartou, vrácené 3 500 (vratka 500 + zálohy 3 000, hotově), faktury 7 × 9 087, bez úhrady
884 + 1 713 + 449, zálohy 19 000 = 10 000 + 3 000 + 6 000. Rozdíly proti ruční uzávěrce mají
vysvětlení: tři platby z 2. 9. (262 hotově, 120 + 250 kartou) patří k dokladům, které ve WinVetu už
neexistují (zkouška před spuštěním), a převod 1 713 z 21. 9. je úhrada nového dokladu s řádkem
„Převod nedoplatku“ k neuhrazenému dokladu z 18. 9. – ruční uzávěrka ten nový doklad nemá.

## Doplnění: blokace ve více ordinacích a „Přesto přesunout“ (27. 10.)

- **Nová blokace** má místo jedné ordinace zaškrtávátka **Ordinace** (předvyplněné všechny). Blokace
  se založí v každé zaškrtnuté ordinaci; zaškrtnuté všechny = jedna blokace celé kliniky (jako dřív
  prázdná ordinace). Týdenní opakování platí pro každou ordinaci zvlášť. Hotová blokace se dál upravuje
  po jednotlivých ordinacích.
- **Přesun / potvrzení na tabuli** (Ordinace i Tabule v pokladně): když v cílové ordinaci a čase
  neslouží lékařka, která úkon dělá, nebo se úkon v té ordinaci nedělá, dialog chybu ukáže a nabídne
  tlačítko **Přesto přesunout** (u žádosti **Přesto potvrdit**). Lékařka u rezervace zůstane, do historie
  rezervace se zapíše „Přesunuto i přes upozornění: …“. Kolize s jinou rezervací nebo úplnou blokací se
  obejít nedá.

- **Úprava blokace** (28. 10.): formulář ukáže zaškrtnuté ordinace celé skupiny – blokací, které vznikly
  spolu (stejný důvod, druh a čas). Přidaná ordinace dostane kopii, odškrtnutá se smaže, všechny
  zaškrtnuté = jedna blokace celé kliniky. Změna času, důvodu nebo poznámky a „Zrušit blokaci“
  ve formuláři platí pro celou skupinu; přetažení na tabuli dál mění jen jednu blokaci.

Upgrade: `-u elite_vet_reservation,elite_vet_reception` (18.0.2.13.0, 18.0.1.18.0), žádná změna dat ani
mostu. V pokladně a v Ordinacích obnovit stránku natvrdo (Ctrl+Shift+R).

## Doplnění: styly ze šablon do CSS, galerie jako blok, jazyková brána (27. 10.)

Větev `feature/elite-vet-styly-galerie`. Upgrade jedním během:

```bash
<odoo> -d <db> -u elite_vet_theme,elite_vet_team,elite_vet_calendar,elite_vet_web --stop-after-init
```

* **Styly:** v QWeb šablonách už není žádný `<style>`. Společné styly (hlavička, patička, bloky) jsou
  v `elite_vet_theme/static/src/css/zaklad.css` (`web.assets_frontend`), styly jen pro jednu stránku
  v jejím bundlu `elite_vet_*.stranka_*`, který si šablona načte do `<head>`. `bloky.css` zrušen –
  byl kopií stylů homepage. Vzhled ověřen porovnáním vypočtených stylů všech prvků před a po
  (6 stránek, desktop + mobil). Záměrné rozdíly: hlavička na Náš tým a Rozpis je stejná jako
  jinde (tlačítko Zavolat tam dřív nemělo styl), na telefonech ≤ 480 px má Ceník a O nás okraj
  16 px jako ostatní stránky.
* **Galerie** je samostatný blok *Galerie kliniky* (panel bloků → Elite Vet). Fotky dosazuje
  `galerie.js` z `/elite_vet/galerie`, do uložené stránky se nezapisují – přidaná či smazaná fotka
  v Web kliniky → Galerie kliniky je na webu hned. Migrace 18.0.1.22.0 nahradí zamrzlou galerii
  (natvrdo ID fotek + inline `<style>`) v pohledech uložených z editoru blokem a převezme texty
  v každém jazyce. V logu: `Zamrzla galerie nahrazena blokem Galerie v: …` (nebo nic, když kopie není).
* **Jazyková brána** se ukáže jen při první návštěvě: volbu drží `localStorage` + cookie
  `ev_lang_chosen` (rok); server bránu při cookie nevykreslí.
* **Tlačítko Kontakt** v hlavičce (PC) vede na `/#kontakt` (sekce kontaktů na domovské stránce,
  s jazykovou předponou) místo `tel:`. Na mobilu je dál schované. `galerie.js` po doplnění fotek
  znovu dorovná stránku na kotvu, jinak by `#kontakt` z jiné stránky dojel o výšku galerie výš.

Kontrola – domovská stránka nesmí mít vlastní kopii z editoru, jinak se na ni změny šablony
neprojeví (`stary_skript` musí být `f`):

```sql
SELECT id, website_id, arch_db::text LIKE '%sessionStorage.getItem("evSplashSeen"%' AS stary_skript
FROM ir_ui_view WHERE key = 'elite_vet_web.homepage';
```

V prohlížeči Ctrl+Shift+R. `nasazeni/test-vseho.py`, oddíl 4 (galerie) testuje nové chování.


## Doplnění: rozpis DPH v uzávěrce a v pivotu tržeb (29. 10.)

`-u elite_vet_winvet` (18.0.1.7.0). Most ani data se nemění; nová uložená pole se při upgradu
dopočítají ze stávajících řádků (sazba a částka už v Odoo jsou).

* **Uzávěrka (PDF)** má na konci oddíl *Rozpis DPH* (7., u jednoho dne 6.): po sazbách základ daně,
  DPH a celkem s DPH, u každé sazby rozpad na úkony / léky a zboží / ostatní. Stejné řádky jako
  oddíl *Tržby podle položek* (bez peněžních řádků „měna“ a nulových řádků).
* **Tržby podle položek** (`elite.vet.sale.line`): nová pole *Sazba DPH* (seskupení, filtr
  Seskupit → Sazba DPH), *Základ DPH* a *DPH*. Pivot je má mezi měrami, seznam jako volitelné
  sloupce. Původní číselné pole se jmenuje *Sazba DPH (%)*.
* Výpočet: částka řádku je s DPH, základ = částka / (1 + sazba) zaokrouhlený na haléře po
  řádcích, DPH = částka − základ. Sazba je ta z řádku dokladu ve WinVetu (`SAZBA_DPH`), ne
  z ceníku.

Pozor na data: ve WinVetu mají k 29. 10. skoro všechny řádky dokladů sazbu 0 % (5 348 řádků účtů
majitele, DPH 0), 21 % jen 2 řádky; ceník přitom vede 12 % a 21 %. Rozpis to ukáže tak, jak je
na dokladech – u období jen s 0 % napíše „doklady jsou vystavené bez DPH“.

Kontrola: Tržby podle položek → pivot, řádky Sazba DPH; součet *Základ DPH* + *DPH* = *Částka*.

## Doplnění: účet jen pro čtení dat z WinVetu (API pro agenta) (30. 10.)

`-u elite_vet_winvet,elite_vet_sale,elite_vet_clinic` (18.0.1.8.0, 18.0.1.2.0, 18.0.1.9.0). Data
se nemění.

Nová role **WinVet data → Jen čtení (API)** (`elite_vet_winvet.group_winvet_readonly`): čtení
všeho, co posílá most – majitelé (`res.partner`), pacienti, návštěvy a vitální hodnoty, očkování,
doklady, položky tržeb, platby, zálohy a jejich čerpání, výdaje, ceník, sklad (`elite_vet_sale`),
balíčky úkonů a fráze (`elite_vet_clinic`), kalendář z WinVetu, uživatelé WinVetu, stav
synchronizace a změny struktury. Navíc `elite.vet.winvet.dashboard.get_data` a
`elite.vet.cash.closure.closure_data` (uzávěrka jako data). Žádné právo zápisu, vytvoření ani
mazání na datech kliniky – přes API nic nezmění (hlídá test `test_readonly_account`). API klíč
mostu a log běhů nevidí.

Nastavení účtu (např. `slavek`):

1. Nastavení → Uživatelé → účet: typ *Interní uživatel*; v rolích Elite Vet **nic** (ne Recepce,
   ne Vedení – ty mohou zapisovat); *WinVet data* = **Jen čtení (API)**. Ostatní aplikace prázdné.
2. Přihlásit se jako ten účet → Předvolby → Zabezpečení účtu → *Nový API klíč* (heslo se tím
   do agenta nedává; klíč jde kdykoli zrušit).
3. Agent volá JSON-RPC / XML-RPC (`/jsonrpc`, `/xmlrpc/2/object`) s loginem a API klíčem místo
   hesla.

Pro agenta: u `res.partner` vždy uvádět seznam polí (`search_read(domain, ["name", ...])`) –
partner má i účetní pole a ta účet číst nesmí, `search_read` bez polí skončí chybou přístupu.
