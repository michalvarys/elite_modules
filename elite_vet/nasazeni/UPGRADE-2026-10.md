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
