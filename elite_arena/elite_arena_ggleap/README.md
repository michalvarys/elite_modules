# Herna – data z ggLeapu

Odoo 18 modul. Odoo si samo stahuje data z ggLeap Public API a plní z nich tabulky
a přehled herny. ggLeap nemá webhooky, takže stahování běží cronem každých 15 minut.
Synchronizace jen čte. Do ggLeapu Odoo zapíše jedině herní pass, který někdo přidá
hráči ručně (viz [Herní passy](#herní-passy)).

## Nastavení

1. V administraci ggLeapu: **Settings → API → Public API** → zkopírovat AuthToken.
2. V Odoo: **Herna → Konfigurace → Nastavení** → vložit token → **Uložit a otestovat spojení**.
   Formulář uložený token už nikdy neukáže. Uloží se v `ir.config_parameter`
   `elite_arena_ggleap.auth_token`, který vidí jen správce systému.
3. **Uložit a synchronizovat teď** spustí první běh na pozadí.
   - Při prvních bězích se stahuje historie (`history_days`, výchozí 365 dní).
   - ggLeap vrací zhruba posledních 6 měsíců aktivity.
   - Detail hráče stojí jeden dotaz na každého hráče. Stahuje se po dávkách, výchozí dávka je 30 hráčů na běh.
   - Kompletní stažení tak trvá několik hodin.

Přístup řídí skupiny v kategorii **Herna (ggLeap)**:

- **Data a přehled** vidí všechno, ale nic nemění.
- **Přidělovat passy** navíc přidává hráčům herní passy do účtu v ggLeapu.
- **Správce** navíc nastavuje propojení, spouští synchronizaci a opravuje druh produktu.

## Limity a běh

- **Rate limit:** tarif Basic dovolí 20 dotazů za minutu a 10 000 dotazů denně. Limit platí pro všechny nástroje se stejným tokenem.
  - Modul drží výchozí 18 dotazů za minutu.
  - Modul si počítá dotazy za den a nad `daily_limit` (výchozí 5 000) přestane.
- **Délka běhu:** běh skončí po `run_seconds` (výchozí 100 s) a další běh pokračuje od uloženého kurzoru.
  - Na serveru s workery musí být délka běhu menší než `limit_time_real_cron`.
  - Tento limit má výchozí hodnotu 120 s.
- **Jen jeden běh naráz:** zaručuje to zámek `pg_try_advisory_lock`.
- **Chyby:** každá oblast běží ve vlastním savepointu. Chyba jedné oblasti se zapíše do **Stavu synchronizace** a pošle se zpráva do chatteru. Ostatní oblasti doběhnou.
- **Běžná zátěž:** jeden běh stojí asi 10–15 dotazů, tedy přibližně 1 000–1 400 dotazů denně.

## Co se stahuje

| Oblast | Endpoint ggLeapu | Model | Jak |
|---|---|---|---|
| Počítače | `/machines/get-all` | `elite.arena.ggleap.machine` | každý běh celé |
| Produkty | `/pos/products/get-all` | `elite.arena.ggleap.product` | každý běh celé |
| Hráči | `/users/summaries` | `elite.arena.ggleap.player` | každý běh celé; kdo chybí, je *smazaný v ggLeap* |
| Herní sezení | `/activity-logs/search` (LoggedIn, LoggedOut, RemoteLoggedIn, RemoteLoggedOut, CreatedUser) | `elite.arena.ggleap.visit` | od kurzoru po 7 dnech, překryv 15 min |
| Konec sezení bez odhlášení | `/sessions/get-user-sessions` | `elite.arena.ggleap.visit` | po dávkách hráčů, sezení starší než 12 h |
| Prodeje | `/transactions/search` | `elite.arena.ggleap.transaction` + `.line` | od kurzoru po 14 dnech, překryv 3 dny kvůli vratkám |
| Rezervace | `/bookings/get-bookings` | `elite.arena.ggleap.booking` | okno od předevčírka na `bookings_ahead` dní |
| Detail hráče | `/users/user-details` | `elite.arena.ggleap.player` | jednou pro každého nového hráče |
| Herní passy | `/users/gamepasses/list` | `elite.arena.ggleap.gamepass` | jednou pro každého hráče, pak znovu po každé návštěvě (`gamepasses_per_run`, výchozí 10) |

Pravidla párování a výpočtu:

- **Klíč záznamu:** vše se páruje podle ID z ggLeapu. Zapisují se jen změněné hodnoty.
- **Herní sezení** (model `elite.arena.ggleap.visit`, menu *Herní sezení*):
  - Začátek dá přihlášení, konec odhlášení na stejném PC nebo konzoli.
  - Na PC jde o `LoggedIn`/`LoggedOut`.
  - Konzole a simulátory (PS5 „L“/„R“, SIM) používají `RemoteLoggedIn`/`RemoteLoggedOut` a mají místo PC `DeviceUuid` a `DeviceName`.
  - Vzdálená přihlášení jsou častá, starší skript `ggleap_pull.py` je nepočítal.
  - Když ggLeap odhlášení nezapíše (typicky došel čas), doplní se konec z `/sessions/get-user-sessions`. Stojí to 1 dotaz na hráče a běží to po dávkách (`sessions_per_run`).
  - Hosté bez účtu jsou sezení s příznakem *Host*.
- **Návštěva** = jeden den, kdy hráč přišel. Víc sezení za večer, například třikrát koupená hodina na PS5, je jedna návštěva. Každé sezení hosta je jedna návštěva.
  - Podle návštěv se počítají skupiny hráčů i karta *Návštěvy* v přehledu.
  - Mapa *Kdy se chodí* ukazuje první příchod dne.
- **Prodej se počítá do tržeb** jen se stavem *Zaplaceno* nebo *Částečně vráceno*. Vrácené prodeje se nepočítají.
- **Druh položky:**
  - Herní balíček (Offer) je *Hraní*. Pokud má nulovou cenu nebo „free / zdarma“ v názvu, je to *Hraní zdarma*.
  - Zboží (Generic) je *Občerstvení*.
  - Druh opravený ručně v Konfigurace → Produkty už synchronizace nepřepíše.
- **Herní čas položky** = množství × herní čas produktu, například „3 Hodiny“ × 2 = 6 h.
- **Částka položky** = skutečně zaplaceno.
  - Hodnoty položek z ggLeapu jsou ceníkové, proto se přepočtou tak, aby dávaly dohromady cenu prodeje.
  - Hodina zdarma „koupená“ za coiny má v ggLeapu hodnotu 1 000, ale stojí 0 Kč.
  - Ceníková hodnota zůstává v poli *Hodnota podle ceníku*.

## Herní passy

Pass je předplacený herní čas na účtu hráče. Vzniká koupí u pokladny (1 Hodina, 3 Hodiny…),
jako výhra za coiny, nebo ho přidá někdo z Odoo.

- **Kde je vidět:**
  - Kontakt → záložka **Herna**: platné passy, zbývající čas a tlačítko *Zbývá v passech*.
  - Formulář hráče: záložka *Herní passy*.
  - **Herna → Hráči → Herní passy**: všechny passy s filtry *Platné*, *Přidané z Odoo* a *Nezačaté*.
  - Kontakt má uložené pole *Herna: zbývá v passech (h)* a filtr *Herna: má nevyčerpaný pass*.
- **Stav:** *Platný*, *Vyčerpaný*, *Propadlý* (po datu platnosti) nebo *Odebraný* (v ggLeapu smazaný).
- **Načítání:**
  - Passy hráče stojí 1 dotaz. Cron je načte jednou pro každého hráče, nejdřív nedávné návštěvníky.
  - Po každé návštěvě je načte znovu, a to až 6 hodin od příchodu a nejvýš jednou za hodinu, protože se během hraní odečítá čas.
  - Krok běží před detaily hráčů, aby ho jejich první stahování nezdrželo.
  - Tlačítko **Načíst passy z ggLeapu** je načte hned.
- **Přidat pass** (kontakt → Herna, nebo formulář hráče):
  - **Produkt:** pass vychází z produktu typu herní pass. Výchozí je hodina zdarma za 0 Kč („1 HODINA FREE“).
  - **Omezení:** pass převezme omezení produktu, tedy skupiny PC a dny. Například PS5 pass platí jen na PS5.
  - **Čas a platnost:** čas, platnost (výchozí 14 dní, nastavení *Přidaný pass platí*) a kdy začne běžet jdou změnit.
  - **Zápis:** Odoo zavolá `POST /users/gamepasses/add` s `X-Correlation-Id`. Dvojklik tedy pass nepřidá dvakrát.
  - Pass se hned uloží s příznakem *Přidán z Odoo*, kdo ho přidal a proč. Ke kontaktu se zapíše poznámka.
- Odebrat pass jde zatím jen v administraci ggLeapu. Po dalším načtení bude v Odoo *Odebraný*.

## Skupiny hráčů

Skupinu dostane každý hráč po každém běhu. Počítá se stejně jako ve skriptech
dotazníku (`arena-email/scripts/survey_recipients.py`). Hranice dní jsou v Nastavení.

| Skupina | Klíč | Pravidlo |
|---|---|---|
| Chodí pravidelně | `aktivni_stali` | víc návštěv, poslední před méně než 30 dny |
| Nový, zatím jednou | `jednou_nedavno` | 1 návštěva před méně než 30 dny |
| Přestává chodit | `ohrozeni` | víc návštěv, poslední před 30–90 dny |
| Ztracený | `ztraceni` | víc návštěv, poslední před 90 a více dny |
| Přišel jen jednou | `jednou_davno` | 1 návštěva před 30 a více dny |
| Ještě nehrál | `nikdy` | žádná návštěva |

Poslední návštěva je pozdější z dvou údajů: poslední stažené přihlášení a `LastSeen` z detailu hráče. Díky tomu se počítá i hráč, který chodil jen před začátkem stažené historie.

## Kontakty

- **Párování hráče s kontaktem:** hledá se v tomto pořadí a použije se první shoda.
  1. Kontakt s `ggleap_uuid`.
  2. Kontakt s interní referencí (`ref`) = ID hráče. Tak kontakty zakládají skripty dotazníku.
  3. Kontakt se stejným e‑mailem, který ještě není propojený s jiným hráčem.
- **Nový kontakt:** když se nic nenajde a je zapnuté *Zakládat kontakty*, založí se kontakt. Hráč bez e‑mailu i jména kontakt nedostane.
  - Jméno se vezme z ggLeapu. Pokud je celé malými písmeny, převede se na velká počáteční písmena („karel novák“ → „Karel Novák“).
  - Kontakt dostane štítek *Hráč herny (ggLeap)*.
- **Existující kontakt** si při prvním propojení nechá svoje jméno a e‑mail. Doplní se jen prázdné údaje.
- **Pozdější změny:** když se v ggLeapu později změní e‑mail, telefon nebo jméno, přepíše se do kontaktu jen ten změněný údaj. Úpravy v Odoo ostatních údajů vydrží.
- **Údaje z herny na kontaktu:** kontakt má pole *Herna: skupina / poslední návštěva / návštěv / utratil / dní od návštěvy*.
  - Pole jsou uložená, takže jdou použít ve filtrech, v e‑mailingu i v automatizacích.
  - Kontakt dostane také záložku **Herna** a tlačítko *Návštěv herny*.
  - Ve vyhledávání kontaktů jsou filtry *Hráči herny*, *Herna: přestává chodit / ztracený / přišel jen jednou*.
- **Znovu spárovat kontakty** ve Stavu synchronizace projde znovu hráče bez kontaktu. Hodí se po ručním založení kontaktů nebo po zapnutí *Zakládat kontakty*.

Souhlas s marketingem ggLeap neposílá. Odhlášení řeší Odoo e‑mailing přes blacklist.

## Přehled herny

**Herna → Přehled** je klientská akce `elite_arena_ggleap.dashboard` (OWL a Chart.js).
Data počítá `elite.arena.ggleap.dashboard.get_data(od, do, srovnání_od, srovnání_do)`.
Dny se počítají v časovém pásmu uživatele, výchozí je Europe/Prague.

- **Věta nahoře** shrne období: kolik návštěv, od kolika hráčů, kolik utratili a srovnání s minulým obdobím.
- **Tržby jsou jen z pokladny ggLeapu.** Občerstvení se v herně markuje jinde: ggLeap má od dubna do října 3 prodeje jídla a jeho finanční report za říjen ukazuje 0 Kč za „snacks“. Když je občerstvení pod 1 % tržeb, věta nahoře na to upozorní.
- **Karty:**
  - tržby,
  - návštěvy,
  - různí hráči,
  - noví hráči,
  - noví, kteří se vrátili do 30 dní,
  - odehrané hodiny,
  - rozdané hodiny zdarma,
  - rezervace.

  Každá karta ukazuje změnu oproti srovnávanému období. Kliknutí otevře záznamy.
- **Tržby a návštěvy v čase:** sloupce jsou tržby podle druhu, čára je počet návštěv. Delší období se zobrazí po měsících.
- **Kdo k nám chodí a kdo odchází:** počty ve skupinách ke dnešku. Kliknutí otevře seznam hráčů.
- **Kdy se chodí:** mapa den × hodina příchodu.
- **Další panely:** co se prodává, nejlepší hráči období, jak platí (hotově, kartou, z kreditu) a vytížení počítačů.

## Menu

- **Přehled**
- **Hráči:** Hráči, Kontakty hráčů, Herní passy
- **Herní sezení**
- **Tržby:** Tržby podle položek, Prodeje
- **Rezervace**
- **Konfigurace:** Nastavení, Stav synchronizace, Produkty, Počítače

## Testy

```bash
docker exec odoo odoo -d <testovací_db> -i elite_arena_ggleap --test-tags /elite_arena_ggleap \
    --stop-after-init --http-port 8079
```

Testy používají falešného klienta, který vrací připravená data a filtruje období jako skutečné API. Do ggLeapu se při nich nic neposílá.

Pokrývají:

- celý běh synchronizace,
- párování kontaktů,
- spojení přihlášení a odhlášení do návštěvy,
- vratky,
- druhy položek,
- idempotenci druhého běhu,
- smazané hráče,
- chybu jedné oblasti,
- ručně nastavený druh produktu,
- herní passy: stav, součty, omezení produktu, obnovu po návštěvě, odebrání v ggLeapu, přidání z Odoo (dvojklik, chyba API),
- čísla přehledu.
