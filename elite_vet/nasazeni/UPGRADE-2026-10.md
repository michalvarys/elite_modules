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
Vedení zakládá účty průvodcem **Vytvořit účty**. Větev `feature/elite-vet-member-accounts`. Cílový
kód: `elite_vet_calendar` 18.0.5.5.0, `elite_vet_clinic` 18.0.1.2.0, `elite_vet_reception`
18.0.1.7.0 (nově závisí na `auth_signup`, který je v Odoo nainstalovaný vždy).

Pravidla a záloha jako v krocích 2–3. Pak jeden běh:

```bash
<odoo> -d <db> -u elite_vet_calendar,elite_vet_clinic,elite_vet_reception --stop-after-init 2>&1 | tee upgrade-ucty-tymu-$(date +%F-%H%M).log
grep -nE " (ERROR|CRITICAL) |Traceback" upgrade-ucty-tymu-*.log      # nesmí nic najít
```

Přibudou sloupce `elite_vet_doctor.user_id` (s unikátním omezením) a
`elite_vet_clinical_record.doctor_from_roster`, dva přechodné modely průvodce a jejich práva (jen
Vedení). Data se nemění: nikdo zatím propojený není, takže se nic nechová jinak, dokud se účty
nepropojí. Na počítačích obnovit stránku natvrdo (Ctrl+Shift+R).

**Jak založit účty (vedení, po upgradu):**
1. Rozpis služeb › **Lékařky** › tlačítko **Vytvořit účty**.
2. Zkontrolovat řádky: přihlašovací jméno (e-mail z karty v Náš tým; prázdné doplnit nebo řádek
   nechat nezaškrtnutý), roli (Lékařka u lékařek s rezervacemi, jinak Sestra – recepci přepnout
   na Recepce), zaškrtnutí **Vytvořit**.
3. **Hesla** – jedna ze dvou cest:
   - nechat **Poslat pozvánku e-mailem** vypnuté a heslo nastavit v Nastavení › Uživatelé › účet ›
     Akce › **Změnit heslo** (sdělit osobně), nebo
   - zaškrtnout **Poslat pozvánku e-mailem**: každý dostane standardní pozvánku Odoo s odkazem na
     nastavení hesla (zařadí se do fronty e-mailů a odejde s nejbližším během odesílání, odkaz platí
     podle `auth_signup.signup_validity_hours`, výchozí 6 dní). Musí fungovat odchozí pošta.
4. **Vytvořit účty** – zpráva řekne, kolik účtů vzniklo a kolik řádků se přeskočilo.
5. Existující účet (např. založený dřív ručně) propojit přímo ve sloupci **Účet**; průvodce takový
   řádek nenabízí, pokud už propojený je, a odmítne přihlašovací jméno, které už má jiný účet.

Kontrola: přihlásit se jedním novým účtem lékařky v den, kdy má v Rozpisu lékařů službu → otevře se
Ordinace na její ordinaci; Moji pacienti dnes ukazují její rezervace. Účty ordinací se nemění.

```sql
SELECT d.name, u.login FROM elite_vet_doctor d JOIN res_users u ON u.id = d.user_id ORDER BY d.name;
```
