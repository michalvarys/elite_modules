# Rozpis služeb

Odoo 18 modul. Přidává aplikaci **Rozpis služeb** a veřejnou stránku
**`/rozpis-lekaru`** s měsíčním kalendářem.

Aplikace má tři položky menu — **Rozpis**, **Lékařky**, **Typy směn** — a nic víc.

## Rozpis

Vyplní se tři věci a je hotovo:

| Pole | Hodnota |
|---|---|
| **Datum** | den služby |
| **Lékařka** | výběr ze seznamu |
| **Směna** | výběr z typů směn |

Časy se tady nezadávají, nese je typ směny. Seznam se dá psát rovnou v tabulce
(klik do řádku, vyplnit, Enter na další), nebo se vpravo nahoře přepne na
**kalendář** a kliká se do dní.

**Státní svátky se nezadávají.** V kalendáři Rozpisu služeb (i v Rezervace › Rozpis lékařů
a v kalendáři Rezervace) je název svátku v buňce dne sám, na webu /rozpis-lekaru také (stejným
písmem jako celodenní poznámky, červeně). Lékařka, která ve svátek slouží, je v buňce dál. Když
na ten den ručně zadáte celodenní poznámku (třeba „Zavřeno“), na webu se ukáže jen ona, ne
dvakrát. Svátky se počítají v kódu (`models/holidays.py`), nezakládají se žádné záznamy.

**Zavřeno, svátek, den otevřených dveří:** vybere se typ, který má zaškrtnutou
**Celodenní poznámku**. Lékařka se nevyplňuje — pole samo zmizí — a do
**Poznámky** se napíše text, například `Státní svátek`. Na webu se vypíše přes
celou buňku barvou toho typu. Když poznámku necháte prázdnou, použije se název typu.

## Lékařky

Jméno, karta v Náš tým a **Účet**. Odsud se nabízejí při zadávání směny.

**Účet** je přihlašovací účet toho člena týmu (jen interní uživatel, jeden účet patří nejvýš
jednomu člověku). Podle něj Odoo pozná, kdo je přihlášený: Moji pacienti dnes, obrazovka Ordinace,
kdo pacienta převzal (modul Recepce). Na formuláři uživatele se ukáže jen pro čtení jako **Člen
týmu**. Účty pro všechny najednou založí vedení tlačítkem **Vytvořit účty** (modul Recepce, návod
v `elite_vet_reception/doc/ordinace.md`).

Lékařku, která už na klinice nepracuje, není nutné mazat — stačí ji
archivovat, minulé směny zůstanou v pořádku.

## Typy směn

Tady se mění **čas i barva směny**. Změna se hned promítne na web, a to na obě
místa najednou — do vysvětlivek nahoře i do bublin u jmen v kalendáři.

Předvyplněno při instalaci:

| Název | Od | Do | Barva |
|---|---|---|---|
| Ranní služba | 8:00 | 14:00 | zelená |
| Odpolední služba | 14:00 | 20:00 | oranžová |
| Noční služba | 20:00 | 8:00 | fialová |
| Víkendová služba | 10:00 | 18:00 | růžová |
| Zavřeno *(celodenní poznámka)* | — | — | červená |

Typ směny jde i přidat — `Sanitární den`, `Den otevřených dveří`. Barva se vybírá
ze seznamu, takže se v ní nedá udělat překlep. Přetažením za úchyt vlevo se mění
pořadí ve vysvětlivkách. Typy s celodenní poznámkou se ve vysvětlivkách na webu
nezobrazují.

Zaškrtnutí **Celodenní poznámky** znamená, že typ není služba lékařky — zavřeno,
státní svátek, sanitární den, den otevřených dveří. Nevybírá se u něj lékařka
ani čas (pole se schovají) a na webu se vypíše přes celou buňku barvou typu.

## Co se objeví na webu

Stránka ukazuje **aktuální a následující měsíc**. Přelomem měsíce se posunou
samy. Čísla dnů, prázdné buňky i názvy měsíců se počítají samy.

V buňce dne je u služby jen barevná tečka a jméno lékařky. **Ikony specializací v buňce
nejsou** (bylo jich moc a kalendář byl nepřehledný) – jsou v bublině u jména spolu s názvem
směny a časem:

* na počítači se bublina ukáže po najetí myší na jméno, klikem na jméno zůstane otevřená;
* na mobilu a tabletu (a na úzkém okně, kde se kalendář posouvá do strany) je čas směny pod
  jménem jako dřív a bublina s ikonami se ukáže ťuknutím na jméno; ťuknutí jinam, Esc nebo
  posunutí stránky ji zavře;
* z klávesnice: Tab na jméno bublinu ukáže, Enter / mezerník ji otevře nebo zavře.

V bublině jsou ikony s názvy specializací; slouží-li na směně víc lékařek, je u ikon i jméno.
Lékařka bez specializací (bez propojené karty v Náš tým) v bublině ikony nemá.

Státní svátky se v buňce dne vypíšou samy (název svátku česky, i na německé, anglické
a ruské verzi stránky). Měsíc bez jediné zadané směny se ale dál nezobrazuje.

## Navigace

Odkazy v horní liště i v mobilním menu se berou z **menu webu**, ne z kódu
stránky. Mění se v Odoo: **Web → Upravit → Menu**. Modul si při instalaci
založí položku *Rozpis služeb* mířící na `/rozpis-lekaru`; jde přejmenovat,
přesunout i smazat.

## Pro správce

* Modely: `elite.vet.shift` (řádek rozpisu), `elite.vet.doctor` (lékařka),
  `elite.vet.shift.type` (typ směny).
* Ukládá se **datum**, ne čas — odpadá tím přepočet časových zón.
* Šablona má pojistku `'elite.vet.shift' in request.env`; kdyby model chyběl,
  stránka se vykreslí prázdná místo chyby 500.
* Barvy jdou do stránky jako inline styl z typu směny, v CSS nejsou natvrdo.
* Záznam stránky `website.page` je publikovaný rovnou modulem.
* Multi-website: `website_id` není nastavené, stránka je na všech webech
  v databázi. Pro omezení jen na Elite Vet doplňte pole do záznamu `website.page`.

## Více webů v jedné databázi

Stránka i odkaz v menu se při instalaci **přiřadí jednomu webu**, ne všem.
Modul hledá web, jehož doména obsahuje `elite-vet`; když ho nenajde, vezme ten,
který má v názvu nebo doméně „vet" a zároveň ne „arena". Který web to byl,
napíše do logu.

Změnit to jde v **Web → Konfigurace → Stránky** u pole *Web*, odkaz v menu pak
v **Web → Upravit → Menu**.

## Uživatelská práva

Modul má vlastní skupinu **Správce rozpisu** (kategorie *Rozpis služeb*).
Kdo ji nemá, aplikaci v Odoo vůbec nevidí. Nastavuje se v
**Nastavení → Uživatelé**.

Nasazení přes Docker: [../../DOCKER.md](../../DOCKER.md).
