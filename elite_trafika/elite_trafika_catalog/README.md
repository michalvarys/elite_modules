# Elite Trafika – katalog

Odoo 18 modul se stránkou `/katalog`. Lidé si prohlédnou výrobky a klepnutím na srdíčko označí, co se jim
líbí. Podle počtů se trafika rozhoduje, co naskladní. Rezervace ani prodej na webu zatím nejsou.

## Co modul dělá

| Oblast | Chování |
|---|---|
| Brána 18+ | Bez potvrzení věku se výrobky nezobrazí; potvrzení si prohlížeč pamatuje 30 dní (nezbytná cookie `elite_trafika_18`). Je to prohlášení návštěvníka, ne ověření věku. |
| Výrobky | 28 položek T9HC z euphoria.eu: květy a bylinné směsi 1 g a 3 g, aroma tyčinky po 1 ks. Filtry: V prodejně a podle druhu. |
| Líbí se mi | Ukládá výrobek, zdroj a čas. Žádné jméno, e-mail, IP adresu ani identifikátor prohlížeče. Stav srdíčka zná jen prohlížeč návštěvníka. |
| Web | Katalog je jen na webu, jehož název je v parametru `elite_trafika_catalog.website` (výchozí „Elite Trafika“); jinde je `/katalog` 404. Prázdný parametr katalog zobrazí na všech webech databáze. |
| Správa | Web → Katalog trafiky: Výrobky v katalogu a Zájem podle zdroje. Přístup má návrhář webu. |

Modul závisí jen na `website`, takže nepotřebuje pokladnu a jde nainstalovat na server webu elite-trafika.cz
i na elite-company.cz. Výrobky se nahrávají jen při instalaci (`noupdate`), úpravy v Odoo aktualizace nepřepíše.

## Odkazy podle zdroje

Zdroj je v odkazu. Povolená jsou malá písmena, číslice, `-` a `_`, nejvýš 32 znaků; ostatní se uloží jako `web`.

```
https://www.elite-trafika.cz/katalog?zdroj=instagram
https://www.elite-trafika.cz/katalog?zdroj=facebook
https://www.elite-trafika.cz/katalog?zdroj=restaurace
```

Pro každou restauraci lze použít vlastní zdroj, např. `?zdroj=restaurace-nazev`.

## Co v katalogu není a proč

- **T9HC Solid:** Euphoria u Solid Caramello píše, že ho prodává jen do Španělska, Itálie a Francie. Vynechané jsou
  všechny Solidy, u ostatních upozornění není, ale jde o stejný typ výrobku.
- **BULK, 100 g a displeje po 20 ks:** velkoobchodní balení.
- **Ceny:** Euphoria je ukazuje jen registrovaným B2B odběratelům a prodejní ceny máme jen u části zboží.
- **Účinky a použití:** výrobce květy a bylinné směsi uvádí jako neurčené ke konzumaci. Pole Vůně proto popisuje jen
  vůni. Na obalech ale je označení „Super strong“.

„V prodejně“ mají výrobky, které jsou v pokladně se stejným EAN i názvem. Skutečný stav skladu modul nesleduje,
při změně nabídky se pole upravuje ručně. Solid Black Afghan a Caramello mají v pokladně EAN u jiného zboží
(MILKDRY 2g, LaMousse 1g), proto se podle něj nespárovaly.

## Před zveřejněním

Modul nic neřeší za právníka. Ověřte hlavně:

- jestli je T9HC v Česku legální; zdroje, které jsme našli, o tom jasně nemluví a HHC je zakázané;
- jestli se na katalog nevztahuje zákaz reklamy (psychomodulační látky, tabákové výrobky);
- jestli reklama na Metě neporuší její pravidla, která platí i pro stránku, na kterou reklama vede;
- jestli smíme obrázky a značky Euphorie veřejně používat (mají být od ní, ne z jiného e-shopu).

## Nasazení

```bash
# 1. záloha
# 2. databáze se zapnutými demo daty: jen příznak modulů, žádná data se nemažou
psql -d odoo -c "UPDATE ir_module_module SET demo = false WHERE demo;"
# 3. instalace; složka elite_trafika musí být v addons_path
odoo -d odoo -i elite_trafika_catalog --stop-after-init --no-http
# 4. restart Odoo
```

Název webu musí sedět s parametrem `elite_trafika_catalog.website`. Na produkci nespouštějte testy.

## Obrázky

Fotky jsou z euphoria.eu, zmenšené na 800 × 800 px na bílém podkladu. Data i obrázky vytvoří znovu
`scripts/gen_data.py`.

## Testy

```bash
O="docker exec odoo odoo -d trafika_catalog_test --http-port 8092 --stop-after-init --without-demo=all"
$O -i website
$O -i elite_trafika_catalog --test-tags /elite_trafika_catalog
```

Testy kontrolují server. Srdíčko a filtry běží v prohlížeči, po změně `static/src/catalog.js` je vyzkoušejte ručně.
