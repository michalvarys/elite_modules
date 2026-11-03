# Elite Vet – Plánování služeb

Rozšiřuje **Rozpis služeb** (`elite_vet_calendar`) a **Rezervace** (`elite_vet_reservation`).
Nic nového vedle rozpisu nevzniká: každé přiřazení v plánu je směna v Rozpisu služeb
(`elite.vet.shift`) s odkazem na směnu plánu (`planning_slot_id`).

## Kde co je

| Menu | Kdo | Co |
|---|---|---|
| Rozpis služeb › Plánování | Správce rozpisu | Rozpis místností (měsíc × úseky), Požadavky na směny, bilance hodin, export CSV, tisk |
| Rozpis služeb › Personál | Správce rozpisu | role, zkratka, úvazek, barva, dovolená, účet |
| Rozpis služeb › Dostupnost a absence | Správce rozpisu | seznam všech záznamů (filtry Absence, Dovolená) |
| Rozpis služeb › Úseky plánu | Správce rozpisu | úseky (Recepce, Ordinace 1, …), jejich směny a časy, ordinace v rezervacích |
| Moje směny › Moje dostupnost | každý interní účet propojený s členem týmu | zaklikání dnů Můžu / Jen ráno / Jen odpoledne / Nemůžu, vlastní směny |

## Propisování

* Lékařka v úseku s ordinací → směna dostane ordinaci → Rezervace z ní udělají službu
  v kalendáři rezervací (`models/shift.py` v `elite_vet_reservation`).
* Ranní + odpolední směna téže lékařky ve stejné ordinaci v jeden den = **jedna** služba
  (8–16 + 12–20 → 8–20). Slučují se jen směny z plánu; ručně zadané překrývající se směny
  dál hlásí kolizi jako dřív.
* Sestry, recepce a výpomoc se do rezervací nepropisují a na webu /rozpis-lekaru se nezobrazují
  (`web_visible`). Ručně zadané směny a celodenní poznámky se zobrazují jako dřív.
* Na webu je u směny čas jejího **typu** (Typy směn), ne čas z plánu.

## Bilance

* Fond = pracovní dny měsíce (po–pá bez státních svátků) × úvazek / 5.
* Odpracováno = hodiny směn (překryv v jednom dni se počítá jednou) + D, L, Š v pracovní den × úvazek / 5.
* NV a PN se do odpracovaných hodin nepočítají. Saldo = odpracováno − fond.
* Celodenní = všední den s 12 h a více; víkend = so + ne.

## Testy

```
odoo -d <db> --test-tags /elite_vet_planning --stop-after-init
```
