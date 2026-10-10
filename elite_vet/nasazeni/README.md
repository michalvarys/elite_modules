# Nasazení webu Elite Vet — postup na jeden zátah

Celý web běží na modulech: `elite_vet_team` (/nas-tym), `elite_vet_calendar`
(/rozpis-lekaru) a `elite_vet_web` (/ a /rezervacni-system). Instaluje se jen
`elite_vet_web`, zbytek si Odoo dotáhne přes závislosti.

## Rozpis služeb zůstane, jak je

Směny, lékařky i typy směn jsou **záznamy v databázi**, ne součást modulu.
Upgrade do nich nesahá: zakládací funkce se spustí jen tehdy, když je tabulka
prázdná. Ostrý web má vlastní typy směn (Celodenní, Polední, Státní svátek)
i lékařku, která v modulu není (MVDr. Daniela Píšková) — všechno zůstane.

Co se změní, je **vzhled**: dvě lékařky na stejné směně se spojí do jednoho
řádku („A + B — Ranní služba“) místo dvou stejných řádků pod sebou.

**Modul neodinstalovávej.** Odinstalace smaže i tabulky, tedy celý rozpis.
Když je potřeba něco vrátit, jde se zpátky commitem a upgradem, ne odinstalací.

## Než začneš

**Zálohuj databázi.** Kroky 3 a 4 přepisují texty a překlady.

Zkontroluj, jak je na tom web teď, ať máš s čím porovnávat:

```bash
node nasazeni/kontrola-prekladu.js https://www.elite-vet.cz
```

## 1. Nahrát moduly a nainstalovat

```bash
git pull                     # tam, kde je repozitář namountovaný do kontejneru
docker compose exec odoo odoo -c /etc/odoo/odoo.conf -d DATABAZE \
    -i elite_vet_web --stop-after-init --no-http
docker compose restart odoo
```

**Restart není volitelný.** Odoo si mapu statických souborů staví při startu,
takže do restartu by všechny fotky házely 404.

## 2. Přepnout domovskou stránku

Instalační hook přepne jen obecnou stránku Odoo. Elite Vet má na `/` vlastní
stránku svého webu, a tu je potřeba přepnout ručně:

**Nastavení → Technické → Web → Stránky**, najít `/`, v poli **Zobrazení**
vybrat `elite_vet_web.homepage`.

SEO titulek a popis zůstanou na záznamu stránky, ty se nemažou.

Stará stránka `/rezervacni-system` ze staré verze webu musí pryč, jinak budou na
stejné adrese dvě a Odoo si vybere špatnou.

## 3. Nahrát překlady stránek

```bash
docker compose exec odoo odoo -c /etc/odoo/odoo.conf -d DATABAZE \
    -u elite_vet_web,elite_vet_team,elite_vet_calendar \
    --i18n-overwrite --stop-after-init --no-http
```

**Bez `--i18n-overwrite` to neudělá skoro nic.** Odoo standardně nepřepisuje
překlad, který v databázi už je — a tam je zatím ten starý, nesprávný.

## 4. Doplnit překlady obsahu

Texty u lékařek, názvy sekcí, popisky údajů, typy směn a specializace nejsou
součástí šablon, ale záznamy v databázi. Doplní je tenhle skript:

```bash
docker compose exec -i odoo odoo shell -c /etc/odoo/odoo.conf -d DATABAZE \
    --no-http < nasazeni/preklady-dat.py
```

Jde pustit opakovaně — páruje podle současné hodnoty, takže co je už přeložené,
nechá být.

**Tohle je na ostrém webu potřeba.** Stažení www.elite-vet.cz/rozpis-lekaru ve
všech čtyřech jazycích ukázalo, že názvy směn a celodenní poznámky jsou všude
česky — německý, anglický i ruský návštěvník čte „Celodenní služba“ a „Zavřeno“.
Skript je doplní; pokryté jsou i typy, které v modulu nejsou
(Celodenní, Polední, Státní svátek, Den otevřených dveří).

Kdyby klinika mezitím zavedla další typ směny, přidej ho do
`nasazeni/preklady-dat.json` stejným způsobem a skript pusť znovu.

## 5. Zkontrolovat obsah v adminu

Instalace založí výchozí obsah (služby, galerii, hodiny, kontakty, časté dotazy,
ceník, nastavení) i s překlady do všech čtyř jazyků. Admin je rozdělený po
stránkách — každá aplikace obsahuje jen to, co se té stránky týká:

| aplikace | co v ní je |
|---|---|
| **Hlavní stránka** | bloky stránky, služby, koho přijímáme, galerie, ordinační hodiny, kontaktní karty |
| **Rozpis služeb** | rozpis, lékařky, typy směn, specializace, ikony |
| **Náš tým** | členové týmu, sekce, specializace, ikony, popisky podrobností |
| **Ceník** | sekce — každá má štítek, nadpis, popisek, obrázek, úkony a komentář |
| **Rezervace** | nastavení rezervace, časté dotazy |
| **O nás** | text stránky /o-nas, obrázek a video z YouTube |
| **Nastavení kontaktu** | telefony, adresa, sítě, pohotovost — propisuje se do všech stránek |

Projdi je a ověř, že je všechno na svém místě. Nabídka aplikací se kešuje
v prohlížeči, takže po instalaci dej **Ctrl+Shift+R**, jinak nové apky neuvidíš.

Zakládá se jen při **první** instalaci. Když už v databázi nějaké záznamy jsou,
skript je nechá být a nic nepřepíše.

Stránka `/cenik` je nová — pokud má být vidět v menu, přidej položku v
**Web → Upravit → Menu** a přelož ji stejně jako ostatní (tabulka níže).

## 6. Přeložit menu

Položky menu jsou taky data, a překládají se v administraci:
**Web → Upravit → Menu**, u každé položky přepnout jazyk a přepsat název.

| česky | německy | anglicky | rusky |
|---|---|---|---|
| Domovská stránka | Startseite | Home | Главная |
| Služby | Leistungen | Services | Услуги |
| Kontakt | Kontakt | Contact | Контакты |
| Náš tým | Unser Team | Our team | Наша команда |
| Rezervační systém | Terminbuchung | Booking | Запись на приём |
| Rozpis služeb | Dienstplan | Duty schedule | График работы |
| Ceník | Preisliste | Price list | Прайс-лист |
| O nás | Über uns | About us | О нас |

Pozor: **do angličtiny se zapisuje jako první**, protože je to zdrojový slot.
Čeština se pak musí vyplnit zvlášť, jinak zdědí angličtinu.

## 7. Zkontrolovat

```bash
node nasazeni/kontrola-prekladu.js https://www.elite-vet.cz
```

Projde pět stránek ve čtyřech jazycích a nahlásí každý text, který zůstal
anglicky tam, kde být nemá, nebo česky v cizojazyčné verzi. Na lokále to po
dokončení hlásilo **0 problémů z 20 kombinací**.

Kompletní zkoušku — projde admin, založí záznamy, ověří, že se objeví na webu,
a zase je smaže — pustíš takhle:

```bash
docker compose exec -i odoo odoo shell -c /etc/odoo/odoo.conf -d DATABAZE \
    --no-http < nasazeni/test-vseho.py
```

Na lokále hlásí **178 ze 178 kontrol**. Skript po sobě uklízí, ale sahá do ostrých
dat — pouštěj ho až po záloze.

Druhá kontrola se dívá na to, co člověk opravdu vidí — titulek v záložce,
meta popis pro vyhledávače a text stránky ve všech čtyřech jazycích:

```bash
node nasazeni/kontrola-stranek.js https://www.elite-vet.cz
```

Na lokále hlásí **0 problémů z 20 kombinací**. Na ostrém webu před nasazením
hlásila 26 problémů — co přesně opraví nasazení, je v tabulce níž.

Ověř taky, že se u jazyka v adrese vrací i správný `<html lang>` — skript to
kontroluje sám, protože bez hlavičky `Accept-Language` Odoo vrací angličtinu
a člověk pak porovnává angličtinu samu se sebou.

## Co ověřit hned po nasazení

**Nic nesmí prosáknout na ostatní weby.** Databáze hostí i Elite Arenu,
trafiku, Jacka a IMI. Stránka bez přiřazeného webu je v Odoo „obecná“ a
vykreslí se na všech doménách — jednou se to už stalo. Modul si teď stránky
přišije sám (instalační hook i migrace), ale zkontroluj to:

**Nastavení → Technické → Web → Stránky**, sloupec **Web** — u `/cenik`,
`/rezervacni-system`, `/rozpis-lekaru` i `/nas-tym` musí stát Elite Vet,
ne prázdno. Totéž u položek v **Web → Upravit → Menu**.

Obecnou domovskou stránku modul úmyslně nepřepisuje, když je webů víc —
napíše to jen do logu a `/` webu Elite Vet se přepne ručně (krok 2).

**Přepínač jazyků.** Odkazy vedou rovnou na `/cs`, `/de`, `/en`, `/ru`.
Přes `/website/lang/` to stálo na cookie `frontend_lang`, a ten in-app
prohlížeč Instagramu a Facebooku neposílá tak, jak Odoo čeká — klik na jazyk
skončil zpátky na původní stránce. Otevři web z odkazu v Instagramu
a přepni tam a zpátky.

**Ikony specializací.** V rozpisu i na stránce týmu se ukazují jen u lidí,
kteří mají specializaci vyplněnou na kartě v **Náš tým → Členové týmu**
(a lékařka musí mít kartu přiřazenou). Zatím je nemá nikdo, takže po nasazení
to vypadá stejně jako dnes, dokud je klinika nedoplní.

## Co je dnes na ostrém webu rozbité a nasazení to spraví

Změřeno na www.elite-vet.cz skriptem `kontrola-stranek.js` (26 problémů):

| co | kde | po nasazení |
|---|---|---|
| chybí meta popis pro vyhledávače | `/rezervacni-system`, `/cenik`, `/rozpis-lekaru`, `/nas-tym` ve všech 4 jazycích | doplní se sám při instalaci (hook `_nastav_seo`) |
| titulek stránky je česky i v cizích jazycích | `/cenik` na `/de`, `/en`, `/ru`; `/nas-tym` a `/rezervacni-system` na `/ru` | titulky jsou v šabloně a přeložené v `i18n/*.po` |
| názvy směn a poznámky jsou česky ve všech jazycích | `/rozpis-lekaru` na `/de`, `/en`, `/ru` | doplní krok 4 (`preklady-dat.py`) |

Meta popis Odoo bere z pole `website_meta_description` na **záznamu stránky**,
ne z `<t t-set="meta_description">` v šabloně — ten tiše ignoruje. Proto ho
zapisuje instalační hook, ve všech čtyřech jazycích, a **už vyplněné pole
nikdy nepřepíše** — co si klinika napsala sama, zůstane.

## Ceník se nasadí i s obsahem

Sekce ceníku, úkony a ceny **jsou součástí modulu** (`elite_vet_web/data/cenik.json`),
takže po instalaci vznikne přesně to, co je vidět na lokále — hlavička stránky,
sekce a jejich úkony včetně ikon. Ikony se hledají podle externího ID, ne podle
čísla záznamu: to je na každé instalaci jiné.

Zakládá se to **jen při první instalaci**. Když už v databázi nějaká sekce je,
hook nedělá nic — upgrade tedy nikdy nepřepíše to, co klinika mezitím změnila.

**Co je zatím jen česky.** Sekce „Víkendové a pohotovostní příplatky" a její
úkony mají ve všech jazycích český text — německý, anglický i ruský návštěvník
je uvidí česky, dokud je někdo nepřeloží. Přeloží se v adminu: Ceník → Sekce,
přepnout jazyk vpravo nahoře a přepsat. Totéž štítek „Ceník" v hlavičce.
Skript `kontrola-stranek.js` to hlásí jako 3 problémy na /cenik — je to tohle,
ne chyba modulu.

## Na co si dát pozor později

**Změna textu v šabloně mění zdroj.** Šablony jsou anglicky právě proto, aby se
úpravou nerozbily ostatní jazyky. Když přidáš nový text, je potřeba doplnit ho
i do `i18n/*.po` příslušného modulu — jinak se v ostatních jazycích ukáže
anglicky.

**Nikdy nezakládej `en_US.po`.** To není jeden z jazyků, ale zdroj. Zápisem do
něj se přepíše originál a čeština, která vlastní překlad nemá, zdědí angličtinu.
Přesně tohle jednou shodilo celý rozpis do angličtiny.

**Ceník se při upgradu převede na sekce.** Nadpis stránky, popisek a spodní
rámeček dosud ležely natvrdo v šabloně. Migrace z nich udělá první sekci a zařadí
do ní všechny úkony, ve všech čtyřech jazycích — stránka vypadá stejně jako před
nasazením. Když už nějaká sekce s úkony existuje, migrace nedělá nic.

**Smazání položky menu si vyžádá restart.** Když v Web → Upravit → Menu smažeš
položku, Odoo si drží starou nabídku v paměti a stránky začnou vracet 500.
Spraví to `docker compose restart odoo`, nic víc. Stalo se to dvakrát, pokaždé
to vypadalo jako rozbitý web.

**Nová složka `static/` nebo změna Pythonu potřebuje restart, ne jen `-u`.**
Upgrade modulu přenačte data a šablony, ale mapu statických souborů a kód
v paměti ne.
