# Elite – restaurační pokladna (základ)

Společný kód restauračních pokladen. Restaurace jsou datové moduly ve složce `elite_restaurace/`
(`elite_imi_pos`, `elite_jack_pos`, další např. Loket), každý obsahuje:

- `skupiny.csv` – skupiny pokladny (hlavní skupina a podskupiny),
- `zbozi.csv` – lístek: `kod`, `skupina`, `nazev`, `cena` (s DPH), `dph`, `sklad`, `alergeny`,
- `data/setup.xml` – firma, mateřská firma, název pokladny, zkratka skladu, sál a počet stolů.

`data/*_data.xml` se generuje ze CSV:

```bash
python3 elite_common/elite_restaurant_pos/scripts/gen_data.py elite_restaurace/elite_imi_pos "IMI Restaurant"
```

## Co nastavení udělá

| Oblast | Nastavení |
|---|---|
| Firma | najde firmu podle názvu, jinak ji založí (jako pobočku, když je zadaná mateřská firma); přístup dostane admin |
| Účetnictví | česká osnova a ceny včetně DPH, jen pokud firma ještě účetnictví nemá |
| DPH | `jidlo` 12 %, `alkohol` 21 %, `nealko` (nápoje na místě) 21 % do 31. 12. 2026, od 1. 1. 2027 12 % (zákon č. 180/2026 Sb.) |
| Sklad | vlastní sklad restaurace (zkratka z `setup.xml`); `sklad = ano` mají lahve a plechovky, ostatní se neskladují |
| Pokladna | režim restaurace: sál se stoly, tisk účtu před platbou, dělení účtu, platby Hotově a Kartou |

Sazby DPH zboží se nastaví při instalaci i při každé aktualizaci modulu podle `zbozi.csv`.
Přechod nealka na 12 % udělá naplánovaná akce „Restaurace: DPH nealko 12 % od 1. 1. 2027“
(1. 1. 2027 v 0:01, pak se sama vypne). Nealko s sebou zůstává na 21 %; rozvoz přes Jídlo pod nos
jde mimo tyto pokladny.

Pokladnu, sál a stoly modul zakládá jen jednou; další úpravy (rozmístění stolů, tiskárny do kuchyně
a baru) se dělají v Odoo a aktualizace je nepřepíše. Zboží a skupiny se nahrávají jen při instalaci.
