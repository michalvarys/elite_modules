# Denní import WinVet přes SFTP

Připraveno pro Debian/Ubuntu, systemd, Docker Engine + Compose plugin, Python 3.10+.
Odoo může běžet v Dockeru nebo mimo něj; pracovní Firebird má vlastní kontejner a
port 3051 dostupný pouze na localhostu. Je nezávislý na databázi Odoo.

Tok: správce vytvoří ZIP s jediným FBK → SFTP upload `.zip.part` → zavření souboru
→ přejmenování na `.zip` → do minuty worker → privátní kopie → obnova FBK
→ kontrola identity, struktury a počtů → plná synchronizace existujícím API Odoo.

## 1. Dohoda se správcem WinVetu

Předat mu host/IP serveru, SSH port (obvykle 22), účet `winvet-upload`, vzdálenou
složku `/incoming` a fingerprint hostitelského SSH klíče ověřený jiným kanálem.
Předat mu heslo samostatného SFTP účtu. Klientský SSH klíč není potřeba.
Fingerprint je ověření identity serveru, nikoli požadavek na přihlašování klíčem.

Podmínky předání:

- Jen dokončená konzistentní záloha vytvořená WinVetem / `gbak`, nikoli kopie živé FDB.
- Název `WINVET_zaloha_21.10.2026_04-03.zip`; čas v názvu je **čas pořízení zálohy
  v Europe/Prague**, nikoli čas odeslání. Uvnitř je jediný `.fbk` (složky jsou přípustné).
- Nahrát jako `WINVET_zaloha_21.10.2026_04-03.zip.part`, **zavřít upload**, pak
  SFTP rename na `WINVET_zaloha_21.10.2026_04-03.zip` ve stejné složce.
- Finální `.zip` nikdy nepřepisovat ani neupravovat. Další záloha dostane nový čas/název.
- Při přerušení navázat/opakovat `.part`; rename provést jen po úspěšném přenosu.
- Přenos spustit po úspěšném dokončení zálohování, bez závislosti na pevném odhadu času.
- Na vzdáleném SFTP uchovávat např. posledních 7 úspěšně nahraných denních ZIPů.
  Čistění zajistí odesílatel; neodstraňovat aktuální soubor ani nedokončený přenos.

Pro automatické odesílání heslem na Windows použijte WinSCP. Pod účtem, který
spouští plánovanou úlohu, vytvořte uložené SFTP spojení `WinVetBackup` s heslem
a ověřeným fingerprintem serveru. Použijte vlastní konfigurační soubor
`C:\WinVet\winscp.ini`, přístupný pouze tomuto účtu a administrátorům.

Příklad skriptu `C:\WinVet\upload.txt`:

```text
option batch abort
option confirm off
open WinVetBackup
cd /incoming
put "C:/WinVet/Backup/WINVET_zaloha_21.10.2026_04-03.zip" WINVET_zaloha_21.10.2026_04-03.zip.part
mv WINVET_zaloha_21.10.2026_04-03.zip.part WINVET_zaloha_21.10.2026_04-03.zip
exit
```

```powershell
& "C:\Program Files (x86)\WinSCP\WinSCP.com" /ini="C:\WinVet\winscp.ini" /script="C:\WinVet\upload.txt"
if ($LASTEXITCODE -ne 0) { throw "Přenos zálohy selhal" }
```

Konkrétní názvy a dávku má generovat jeho zálohovací úloha. Před automatizací musí
ručně ověřit fingerprint serveru a uložit jej do konfigurace WinSCP, kterou
plánovač používá. Nevypínat kontrolu hostitelského klíče. Pro ruční test lze
použít `sftp winvet-upload@SERVER` a zadat heslo; OpenSSH `sftp -b` samo o sobě
neřeší bezobslužné zadání hesla.

## 2. Omezený SFTP účet na našem serveru

Následující příkazy spouští administrátor jako root. Návod předpokládá dosud
neexistující účet a složky; existující konfiguraci nejprve porovnat.

```bash
apt-get update
apt-get install -y openssh-server python3-venv python3-pip libfbclient2
# Docker Engine a Compose plugin musí být již nainstalované.
docker compose version

useradd --no-create-home --home-dir /incoming --shell /usr/sbin/nologin winvet-upload
# Nastavte samostatné dlouhé heslo pro správce záloh.
passwd winvet-upload

install -d -o root -g root -m 0755 /srv/sftp /srv/sftp/winvet
install -d -o winvet-upload -g winvet-upload -m 0750 /srv/sftp/winvet/incoming
```

Nastavte SSH (stejný obsah je přiložen v `sshd-winvet.conf`):

```bash
cat > /etc/ssh/sshd_config.d/60-winvet.conf <<'SSHCONF'
Match User winvet-upload
    ChrootDirectory /srv/sftp/winvet
    ForceCommand internal-sftp -d /incoming -u 0027
    AuthenticationMethods password
    PubkeyAuthentication no
    PasswordAuthentication yes
    KbdInteractiveAuthentication no
    DisableForwarding yes
    PermitTTY no
    X11Forwarding no
Match all
SSHCONF
sshd -t
sshd -T -C user=winvet-upload,host=localhost,addr=127.0.0.1 | \
  grep -E 'chrootdirectory|forcecommand|authenticationmethods|passwordauthentication|disableforwarding'
systemctl reload ssh
```

Na některých distribucích se služba jmenuje `sshd`. Ověřit, že hlavní
`/etc/ssh/sshd_config` načítá `sshd_config.d/*.conf`; zkontrolovat také existující
`AllowUsers`, `AllowGroups`, `DenyUsers` a jiné `Match` bloky. První odpovídající
nastavení může mít přednost. Současné administrační SSH spojení ponechte otevřené
během testu druhého spojení. Neměňte globální SSH autentizaci ostatních účtů.

Celá cesta ke kořeni chrootu musí patřit rootovi a nesmí být zapisovatelná jinými
uživateli. Zapisovat smí účet pouze do `incoming`. Dostane SFTP, žádný shell,
forwardování, klíče Odoo ani přístup ke kontejnerům. Odoo používá interně jiný účet.

## 3. Instalace mostu a workeru

Z repozitáře zkopírujte **celý** adresář `modules/elite_vet/winvet_bridge` do
`/opt/winvet-import` včetně balíčku, `verified.json`, `schema_baseline.json` a
`deploy/sftp`. SFTP konfigurace z předchozího kroku na této instalaci nezávisí.

```bash
install -d -o root -g root -m 0755 /opt/winvet-import
# Příklad z vašeho rozbaleného repozitáře:
cp -a modules/elite_vet/winvet_bridge/. /opt/winvet-import/
chown -R root:root /opt/winvet-import
python3 -m venv /opt/winvet-import/venv
/opt/winvet-import/venv/bin/pip install /opt/winvet-import

install -d -o root -g root -m 0700 /etc/winvet-import /srv/winvet /srv/winvet/state
# Firebird proces v kontejneru musí umět projít přes /work.
install -d -o root -g root -m 0755 /srv/winvet/work
install -m 0600 /opt/winvet-import/deploy/sftp/import.example.ini /etc/winvet-import/import.ini
install -m 0600 /opt/winvet-import/deploy/sftp/bridge.example.ini /etc/winvet-import/bridge.ini
```

Doporučeno aspoň 10 GB volného místa pro tento malý současný dataset; worker před
obnovou vyžaduje alespoň maximum z 2 GB a dvanáctinásobku ZIPu. Budoucí větší data
mohou potřebovat více. Na příjmovou složku nastavte podle filesystemu diskovou kvótu
nebo samostatný omezený filesystem; samotná velikostní kontrola workeru upload nelimituje.

Vytvořte heslo pracovního Firebirdu a soubor pro systemd (bez výpisu hesla):

```bash
umask 077
python3 - <<'PY'
from pathlib import Path
import secrets
password = secrets.token_hex(32)
Path('/etc/winvet-import/firebird_password').write_text(password + '\n')
Path('/etc/winvet-import/secrets.env').write_text(
    'WINVET_FB_PASSWORD=' + password + '\nWINVET_ODOO_API_KEY=REPLACE_ME\n')
PY
chmod 0600 /etc/winvet-import/firebird_password /etc/winvet-import/secrets.env
editor /etc/winvet-import/secrets.env
editor /etc/winvet-import/bridge.ini
```

Nahradit API klíč klíčem z nastavení modulu `elite_vet_winvet` a URL správnou HTTPS
adresou Odoo. Adresa musí jednoznačně routovat do správné Odoo databáze (dbfilter / doména).
Klíč může měnit synchronizovaná data, patří pouze nám, ne správci SFTP.
Na ARM upravte cestu `fb_client_library` podle `dpkg -L libfbclient2`.

V Odoo musí být nainstalované aktuální `elite_vet_winvet` a `elite_vet_clinic`
a jejich závislosti; klinika přidává příjem balíčků a frází. Worker nepovažuje
přeskočenou entitu nebo přeskočené záznamy za úspěch.

```bash
docker compose -p winvet-import -f /opt/winvet-import/deploy/sftp/compose.yml up -d
docker logs winvet-import-fb --tail 30
```

Port 3051 neotvírat ve firewallu. Je navázán výhradně na 127.0.0.1.
Firebird není produkční databáze WinVet, obsahuje pouze naše pracovní kopie.
Worker běží jako root, protože pracuje s Docker socketem a nastavuje vlastníka
pracovní složky na UID Firebirdu; účet odesílatele do skupiny docker nepřidávat.

## 4. První důvěryhodná záloha a kontrola bez zápisu do Odoo

Nechte správce poslat aktuální zálohu podle dohody. Nejdříve zkontrolujte, že
`.zip.part` je při uploadu ignorovaný a `.zip` se objeví až po přejmenování.
Timer zatím nezapínejte.

```bash
set -a
. /etc/winvet-import/secrets.env
set +a
/opt/winvet-import/venv/bin/python /opt/winvet-import/deploy/sftp/backup_import.py \
  --config /etc/winvet-import/import.ini \
  --inspect /srv/sftp/winvet/incoming/WINVET_zaloha_21.10.2026_04-03.zip
```

Datum nahraďte skutečným. `--inspect` provede obnovu a plné zkušební čtení, vypíše
jen hash referenčního záznamu a počty, nepřipojuje se k Odoo a neoznačuje soubor za
importovaný. Platí limit stáří 36 hodin i při inspect. Pro prověření historické
zálohy použijte **samostatnou kopii konfigurace** s dočasně vyšším limitem.

V `/etc/winvet-import/import.ini`:

- `identity_sha256`: vložit hash z důvěryhodné zálohy. Reference není univerzální
  UUID databáze; je to otisk vybraného stabilního záznamu. Vhodnější je explicitní
  neměnné ID a stabilní sloupce. Změna/smazání reference import zastaví a vyžaduje kontrolu.
- `minimum_counts`: po kontrole počtů nastavte realistická minima. Nepřebírejte
  automaticky nuly z neověřené zálohy. Prázdné nepovinné entity lze vědomě povolit nulou.
- `minimum_ratio = 0.80`: zastaví pokles kterékoliv entity o více než 20 % proti
  poslední úspěšné záloze. Hromadné legitimní mazání vyžaduje kontrolovaný zásah.
- `max_age_hours = 36`, `stale_hours = 30`: vhodné pro jednou denně; upravit podle dohody.
- `retry_seconds = 900`: po chybě opakuje stejný soubor za 15 minut.

SHA256 ZIPu worker počítá lokálně pro deduplikaci; odesílatel nemusí posílat další soubor.
ZIP CRC ověřuje při extrakci. Kontrola integrity přenosu je také součástí SSH.

## 5. První import a automatické hlídání

Před prvním plným importem zazálohujte Odoo a ověřte výběr správné WinVet zálohy.
Plný import může archivovat/smazat dříve importované záznamy chybějící v novém snapshotu.

```bash
install -m 0644 /opt/winvet-import/deploy/sftp/winvet-import.service /etc/systemd/system/
install -m 0644 /opt/winvet-import/deploy/sftp/winvet-import.timer /etc/systemd/system/
systemctl daemon-reload
systemctl start winvet-import.service
journalctl -u winvet-import.service -n 80 --no-pager
cat /srv/winvet/state/state.json
# Až první import skončí úspěšně:
systemctl enable --now winvet-import.timer
systemctl list-timers winvet-import.timer
```

Systemd kontroluje příjem každou minutu. Jedna instance služby a souborový zámek
brání souběhu. Kontroluje vždy nejnovější hotovou zálohu podle času v názvu;
starší snapshoty není potřeba importovat postupně. Stejnou či starší již úspěšně
zpracovanou zálohu ignoruje. `.part` se nikdy nečte. Po restartu znovu projde složku.

Záloha se kopíruje mimo SFTP složku; sender k pracovní databázi nemá přístup.
FBK se obnovuje do nového unikátního souboru, nikdy se nepřepisuje živá DB.
Celé čtení všech entit a kontroly proběhnou **před prvním zápisem do Odoo**.
Plný import jde po dávkách, není jednou společnou transakcí. Při chybě mohou být
některé dávky již uložené; opakovaný full běh znovu sesouhlasí stejný snapshot.
Před prvním push se trvale uloží čas rozpracované zálohy, aby ani po pádu nešlo
pokračovat starší zálohou. Novější záloha může rozpracovanou nahradit.

Pracovní ZIP, FBK a FDB se po běhu odstraňují, vstupní ZIP zůstává pro opakování
u odesílatele ve složce incoming. Při násilném ukončení/timeoutu mohou zůstat
`/srv/winvet/work/job-*`: odstranit ručně po ověření, že neběží služba ani gbak.
Neodstraňovat `/srv/winvet/state/state.json` v rámci běžného čištění.

## 6. Provoz a řešení chyb

```bash
systemctl status winvet-import.timer winvet-import.service
journalctl -u winvet-import.service --since today
cat /srv/winvet/state/state.json
```

Návratový kód 1 znamená chybu importu, chybějící čerstvý úspěšný snapshot nebo
chybu konfigurace. Journal obsahuje bezpečné důvody odmítnutí (stará záloha, identita, propad počtů),
u cizích knihoven pouze typ výjimky. Detailní data pacientů ani hesla se nevypisují.
Odoo má vlastní stav synchronizace a upozornění na změnu struktury, ale samostatně
nepozná, že ZIP vůbec nedorazil. **Napojte failed stav této systemd služby nebo
`last_backup` ve stavovém JSONu na stávající monitoring serveru.** Tento balík
sám neposílá e-mail/SMS; bez monitoringu je chyba pouze v journalu a statusu služby.
Po úspěšném běhu systemd failed stav při dalším spuštění odstraní.

Při chybě stejného souboru worker čeká 15 minut a opakuje pokus; nový soubor zkusí
hned. Vynucení okamžitého opakování: zastavit timer a službu, v JSONu nastavit
`retry_at` na 0, znovu službu spustit. Zachovat ostatní položky stavu.

Při změně identity, schématu, propadu počtů nebo vrácení žurnálu zpět nejdřív
prověřit zdroj a obnovit kopii přes `--inspect`. Nikdy automaticky neschvalovat
novou verzi WinVetu ani nemazat baseline. Změnu `verified.json`/schématu řeší
správce integrace podle README mostu. Vědomé snížení minim nebo reset kurzoru
provést jen po kontrole zálohy a záloze stavového JSONu.

Pokud import stále selhává:

1. `docker ps`, `docker logs winvet-import-fb --tail 50`, volné místo a práva k souborům.
2. Pustit `--inspect` na stejný ZIP: obnova/čtení a guard versus přenos do Odoo.
3. Zkontrolovat HTTPS URL, certifikát, API klíč, dbfilter a instalované moduly.
4. Zkontrolovat Odoo log a jeho stav WinVet; Odoo může podrobnosti chyby uložit tam.

Služba má celkový timeout 4 hodiny, gbak uvnitř kontejneru 30 minut. Při timeoutu
ověřte a případně restartujte pouze pracovní Firebird kontejner před opakováním;
nezahajujte ruční import souběžně. V případě velkého datasetu limity upravte.

Zdroje k nastavení:
- OpenSSH chroot, ForceCommand a práva: https://man.openbsd.org/sshd_config
- Oficiální Firebird Docker image a `_FILE`: https://github.com/FirebirdSQL/firebird-docker
- gbak create/restore: https://firebirdsql.org/file/documentation/html/en/firebirddocs/gbak/firebird-gbak.html

Heslová automatizace WinSCP: https://winscp.net/eng/docs/scripting

## Kalendář WinVetu (most 4.0.0)

Plná synchronizace ze zálohy posílá i kalendář WinVetu (okno od dne běhu − 1 na 60 dní). Kalendář
ze zálohy je ale starý tolik, kolik je stará záloha, a záznamy okna, které v záloze nejsou, Odoo
smaže. Pro kalendář na tabuli proto používejte most na PC s WinVetem (`sync --only calendar` každých
5 minut). Když běží jen tento příjem záloh, tabule ukazuje kalendář podle poslední zálohy; vedení ho
může v Odoo vypnout (WinVet data → Kalendář z WinVetu → Zapnout / vypnout), pak se neukládá.
Do `/opt/winvet-import/` zkopírujte i nový `verified.json` (skupina otisků `calendar`), jinak zůstane
kalendář blokovaný.

## Zálohy klientů (most 5.0.0)

Plná synchronizace ze zálohy posílá i zálohy klientů (`deposits`, `deposit_uses`) a formu úhrady
dokladů. Most 5.0.0 čte nový sloupec `DOKLAD.FORMA_UHRADY` a triggery žurnálu u `PARTNER_ZALOHA`, takže
se změnily otisky `sales` a `journal` a přibyla skupina `deposits`: do `/opt/winvet-import/`
zkopírujte spolu s mostem **nový `verified.json`**, jinak budou tržby a zálohy blokované.
