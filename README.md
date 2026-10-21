
„Zavřeno" má zaškrtnutou **Celodenní poznámku**, takže se u něj nezadává lékařka
ani čas. Stejně se dá založit i `Den otevřených dveří` nebo `Sanitární den`.
# elite_modules

Odoo 18 moduly a Docker sestava, která je používá. Moduly jsou seřazené
po projektech.

```
elite_modules/
├── docker-compose.yml     Odoo 18 + PostgreSQL
├── config/odoo.conf       addons_path, připojení k databázi
└── elite_vet/             klinika Elite Vet
    ├── elite_vet_calendar/   Rozpis služeb lékařů
    ├── elite_vet_reservation/   Rezervační kalendář (nahrazuje WinVet)
    └── elite_vet_team/       Stránka Náš tým
```

Celý repozitář je v kontejneru namountovaný do `/mnt/modules`.

**Nový modul stejného projektu** = nová podsložka v `elite_vet/`. Nic se nenastavuje.

**Nový projekt** = nová složka vedle `elite_vet/` a jeden záznam navíc
v `addons_path` v [config/odoo.conf](config/odoo.conf):

```ini
addons_path = /mnt/modules/elite_vet,/mnt/modules/dalsi-projekt,/usr/lib/python3/dist-packages/odoo/addons
```

## Spuštění

```bash
git clone https://github.com/goatrental/elite_modules.git
cd elite_modules
docker compose up -d
```

Odoo běží na `http://localhost:8069`. Nasazení na existující server je
v [DOCKER.md](DOCKER.md).

## elite_vet — klinika Elite Vet

### `elite_vet_calendar` — Rozpis služeb

Aplikace **Rozpis služeb** a veřejná stránka `/rozpis-lekaru` s měsíčním
kalendářem. Aplikace má tři položky a nic víc.

**Rozpis** — jeden řádek má tři údaje:

| Pole | Hodnota |
|---|---|
| Datum | den služby |
| Lékařka | výběr ze seznamu |
| Směna | výběr z typů směn |

**Lékařky** — jméno a konec.

**Typy směn** — tady se mění čas i barva směny. Změna se hned promítne na web,
do vysvětlivek i do bublin u jmen.

| Název | Od | Do | Barva |
|---|---|---|---|
| Ranní služba | 8:00 | 14:00 | zelená |
| Odpolední služba | 14:00 | 20:00 | oranžová |
| Noční služba | 20:00 | 8:00 | fialová |
| Víkendová služba | 10:00 | 18:00 | růžová |
| Zavřeno *(celodenní poznámka)* | — | — | červená |

Typ se zaškrtnutou **Celodenní poznámkou** není služba lékařky — nezadává se u něj
lékařka ani čas a na webu se vypíše přes celou buňku. Stejně se dá založit
`Den otevřených dveří` nebo `Sanitární den`, každý ve své barvě.

Detaily v [elite_vet/elite_vet_calendar/README.md](elite_vet/elite_vet_calendar/README.md).

### `elite_vet_team` — Náš tým

Aplikace **Náš tým** a veřejná stránka `/nas-tym`. Klinika si sama spravuje lidi
včetně fotek, přeskládává je a zakládá sekce — do kódu se kvůli příchodu nebo
odchodu člověka nesahá.

| Položka | K čemu |
|---|---|
| Členové týmu | kanban s fotkami; přetažením se mění pořadí i sekce |
| Sekce | nadpisy na stránce; kotva do odkazu se dopočítá z názvu |
| Popisky podrobností | číselník pro Vzdělání, Praxe, Specializace… |

Fotka není povinná — bez ní se vykreslí kolečko s iniciálami, které se spočítají
ze jména (tituly se přeskakují). Kdo odejde, se nemusí mazat, stačí ho
archivovat.

Po instalaci je stránka naplněná tím, co na ní bylo předtím: 4 sekce, 8 lidí,
38 podrobností.

Detaily v [elite_vet/elite_vet_team/README.md](elite_vet/elite_vet_team/README.md).

### `elite_vet_reservation` — Rezervace

Aplikace **Rezervace** nahrazuje WinVet: ordinace, ordinační doba, rozpis
lékařů, úkony a rezervace jsou v Odoo a na `/rezervacni-system` běží vlastní
průvodce místo iframu. Recepce pracuje s Tabulí (sloupec na ordinaci) a frontou
žádostí z webu; stránka je česky, německy a rusky.

**Nasazení:** v produkčním `odoo.conf` za reverzní proxy musí být
`proxy_mode = True`, jinak by limit rezervací na IP adresu počítal adresu proxy
za všechny klienty dohromady.

Detaily v [elite_vet/elite_vet_reservation/README.md](elite_vet/elite_vet_reservation/README.md).


dokumentace: 
https://claude.ai/artifact/Pc5MFy27S6h7AZC1Hgx9Ex