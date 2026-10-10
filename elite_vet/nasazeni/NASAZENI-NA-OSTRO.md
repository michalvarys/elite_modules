# Nasazení Elite Vet na ostrý web

Postup na jedno spuštění. Všechno, co se dřív muselo doklikat ručně, dělá modul sám.

Ověřeno 24. 9. 2026 na databázi postavené tak, aby se podobala ostrému webu:
ruční stránky na všech adresách, zbylé dědící pohledy `gen_key.*` po starém
přepínači jazyků, položka nabídky mířící na kotvu odpočtu. Do toho se moduly
nainstalovaly a web naběhl správně.

## 1. Stáhnout

```bash
cd <klon repa goatrental/modules> && git pull
```

Moduly leží ve složce `elite.vet/`. Zkopírovat do addons tak, aby `__manifest__.py`
byl **přesně jednu úroveň** pod cestou v `addons-path`.

## 2. Spustit

Podle toho, jestli už moduly na webu jsou:

```bash
# poprvé
odoo -d <db> -i elite_vet_web --stop-after-init

# už nainstalované
odoo -d <db> -u elite_vet_theme,elite_vet_team,elite_vet_calendar,elite_vet_web --stop-after-init
```

Pak restart kontejneru.

Instalovat stačí `elite_vet_web` — zbylé tři si Odoo přitáhne samo.

## 3. Co má být v logu

```
Ceník: zalozeno 3 bloku.
Do nabidky pribyl Kontakt (id ...).
Na '/' je N stranek a Odoo si mezi nimi vybira nahodne, takze vsechny dostaly sablonu modulu
Starsi stranky na adresach projektu odsunuty: /o-nas -> /o-nas-puvodni, ...
Zbytku s mrtvym xpath vypnuto: N
Dvojniku pohledu smazano: N
```

Řádky se `0` jsou v pořádku — znamenají, že nebylo co uklízet.

## 4. Ověřit

```bash
for p in / /o-nas /cenik /nas-tym /rozpis-lekaru /rezervacni-system; do
  printf '%-22s %s\n' "$p" "$(curl -s -o /dev/null -w '%{http_code}' https://www.elite-vet.cz$p)"
done
```

Všechno má vrátit `200`. Na domovské stránce má být mapa v kontaktech a v nabídce
položka **Kontakt**, která sjede ke kontaktní sekci.

## 5. Jazyky

Nastavuje si je modul sám. Při instalaci zapne `cs_CZ`, `de_DE`, `en_US`
a `ru_RU`, přiřadí je webu kliniky a nastaví češtinu jako výchozí jazyk.
Jazyk, který už zapnutý je, nechává být.

V logu je to vidět takto:

```
Jazyky webu srovnany. Zapnuto: cs_CZ, de_DE, ru_RU. Pridano k webu ...
Vychozi jazyk webu ... nastaven na cs_CZ.
```

Na ostrém webu jsou jazyky nastavené už teď, takže se tam nejspíš jen vypíše,
že není co dělat.

## 6. Čeho se nasazení nedotkne

`/aktualni-informace`, `/kariera-pro-lekare` a `/kariera-pro-absolventy` moduly
nedodávají, takže zůstanou přesně takové, jaké jsou.

## Co modul udělá se starými stránkami

Na adresách `/o-nas`, `/cenik`, `/rezervacni-system`, `/nas-tym` a `/rozpis-lekaru`
už na ostrém webu stránka je. Modul si vedle ní založí svoji, takže by na jedné
adrese byly dvě — a Odoo si mezi nimi vybírá **nahodile**:

```python
search(domain, order='website_id asc', limit=1)
```

Mezi stránkami téhož webu už žádné další řazení není. Jednou se proto ukáže nový
web, podruhé starý, a když padne na nezveřejněnou, vrátí 404.

Stará stránka se proto **přejmenuje na `<adresa>-puvodni` a odpublikuje**. Nic se
nemaže: obsah je pořád v databázi a dá se otevřít po zaškrtnutí *Zveřejněno*
v Nastavení → Technické → Web → Stránky.

Domovská stránka se přejmenovat nedá, tam to modul řeší opačně — všechny záznamy
na `/` dostanou šablonu modulu, takže je jedno, který si Odoo vybere.

## Pořadí: nejdřív moduly, potom téma

Na ostrém webu jsou tři věci, které samy o sobě hází 500 nebo shodí
aktualizaci tématu. Všechny tři opraví **instalace nebo upgrade našich
modulů**:

| chyba | co ji dělá |
|---|---|
| `object has no attribute 'emergency_active'` | stará kopie domovské stránky v databázi |
| `Prvek <xpath expr="//div[@class='ev-lang-panel']..."> nelze najít` | zbytky starého přepínače jazyků |
| `duplicate key ... theme_elite_arena.mobile_intro_enabled` | osiřelý systémový parametr cizího modulu |

**Proto se nejdřív nasadí moduly a teprve potom se případně klikne na
„Aktualizovat téma".** Obráceně to spadne stejně jako dosud, protože
oprava ještě neproběhla.

Ověřeno na devu na reálných datech: bez opravy aktualizace tématu spadla
přesně tou hláškou z ostrého webu, po upgradu našeho modulu prošla a hodnota
parametru zůstala nezměněná.

Kdyby se přesto objevila hláška o duplicitním klíči u jiného parametru, dá se
to spravit ručně — klíč je vždy vypsaný za `Key (key)=`:

```sql
INSERT INTO ir_model_data (module, name, model, res_id, noupdate)
SELECT '<modul>', '<nazev_zaznamu>', 'ir.config_parameter', id, true
FROM ir_config_parameter WHERE key = '<nazev.parametru>';
```

`<modul>` a `<nazev_zaznamu>` jsou na konci hlášky v cestě k souboru
a v `<record id="...">`.

## Když se něco nepovede

Nic se nemaže, takže zpátky vede:

1. staré stránky se vrátí přejmenováním z `<adresa>-puvodni` zpět a zaškrtnutím
   *Zveřejněno*,
2. moduly se dají odinstalovat v Aplikacích.

Zálohu databáze si přesto udělej předem.
