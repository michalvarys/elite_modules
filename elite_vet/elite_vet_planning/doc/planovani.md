# Plánování služeb – návod pro vedení a tým

**K čemu je tento návod.** Popisuje měsíční plán směn celého týmu. Má dvě části:

- **Část A** je pro toho, kdo rozpis dělá (Správce rozpisu): Plánování, Personál, Dostupnost
  a absence, Úseky plánu, Požadavky na směny, bilance hodin, export a tisk.
- **Část B** je pro každého člena týmu: Moje směny a Moje dostupnost.

Nastavení lékařek, ordinací a rezervací popisuje
[Návod pro správce](../../elite_vet_reservation/doc/nastaveni.md).

| Kde v menu | Kdo to vidí | Co tam je |
|---|---|---|
| **Rozpis služeb → Plánování** | Správce rozpisu | Měsíční plán, Požadavky na směny, Bilance hodin, export, tisk |
| **Rozpis služeb → Personál** | Správce rozpisu | Role, zkratka, úvazek, barva, dovolená, účet |
| **Rozpis služeb → Dostupnost a absence** | Správce rozpisu | Seznam všech záznamů o dostupnosti a absencích |
| **Rozpis služeb → Úseky plánu** | Správce rozpisu | Úseky (Recepce, Ordinace 1…), jejich směny a časy |
| **Moje směny → Moje dostupnost** | Každý člen týmu s účtem | Vlastní dostupnost a naplánované směny |

Právo **Správce rozpisu** se nastavuje v **Nastavení → Uživatelé**, část **Rozpis služeb**.

---

# Část A – pro toho, kdo dělá rozpis

## 1. Jak to funguje

Plán není nic nového vedle rozpisu. Každý člověk, kterého v plánu přiřadíte do směny, je
obyčejná směna v **Rozpis služeb → Rozpis**. Nic se proto nezadává dvakrát.

Doporučený postup na každý měsíc:

1. Tým si v **Moje dostupnost** zaklikne, kdy může.
2. Vy zapíšete absence do **Požadavků na směny**.
3. V plánu přiřadíte lidi do směn.
4. Podíváte se na **Bilanci hodin**.
5. Plán vytisknete nebo vyexportujete.

Všechno se ukládá hned. Nahoře je vidět **Ukládání…** a pak **Všechny změny uloženy**,
žádné tlačítko Uložit tu není.

## 2. Personál

**Rozpis služeb → Personál** (nebo tlačítko **Personál** přímo v Plánování). Je tu celý tým
a řádky se upravují přímo v seznamu. Přetažením za úchyt vlevo měníte pořadí.

| Sloupec | Význam |
|---|---|
| **Jméno** | Celé jméno, jak se ukazuje v plánu a na webu. |
| **Zkratka** | Štítek v plánu. Spočítá se ze jména (bez titulů) a jde přepsat. |
| **Role** | Lékař, Sestra, Recepce, Výpomoc / stáž. Podle role se lidé řadí v plánu i v Požadavcích na směny. |
| **Úvazek (h/týden)** | Z něj se počítá fond hodin (kapitola 9). |
| **Barva** | Barva štítku v plánu, stejná jako v kalendáři rezervací. |
| **Účet** | Přihlašovací účet člověka. Bez něj nefunguje Moje dostupnost. Jeden účet patří jen jednomu člověku. |
| **Dovolená na rok (dny)** | Nárok na kalendářní rok. |
| **Zbývá (dny)** | Nárok minus záznamy **D** v letošním roce. Počítá se každý záznam D. |
| **V plánování** | Odškrtněte u lidí, kteří se neplánují. V plánu, v Požadavcích ani v bilanci pak nejsou. |

Skryté sloupce **Lékařka (rezervace)** a **Aktivní** zapnete ikonou vpravo v hlavičce seznamu.
Kdo má zaškrtnuto **Lékařka (rezervace)**, je lékařka pro rezervace; zaškrtnutím se mu role
sama přepne na Lékař.

## 3. Úseky plánu

**Rozpis služeb → Úseky plánu.** Úsek je blok řádků v plánu. Při instalaci se založí Recepce,
Ordinace 1, Ordinace 2, Sál a Stáž / výpomoc. Pořadí změníte přetažením.

U úseku vyplňte:

| Pole | Význam |
|---|---|
| **Název** | Např. Ordinace 1. |
| **Druh** | **Úsek / místnost**, nebo **Stáž / výpomoc**. Do Stáže / výpomoci jde vepsat i jméno někoho mimo tým; tyto směny na web nejdou. |
| **Ordinace v rezervacích** | Ordinace, do které se propíše služba lékařky v tomto úseku. Prázdné (např. Recepce) = nepropisuje se. |
| **Role nahoře v nabídce** | Které role se při výběru člověka nabízejí první. Píše se anglicky, oddělené čárkou: `doctor` lékař, `nurse` sestra, `reception` recepce, `helper` výpomoc. |
| **Aktivní** | Odškrtnutý úsek se v plánu neukazuje. |

Dole jsou **směny** úseku, každá je jeden řádek plánu:

| Sloupec | Význam |
|---|---|
| **Název** | Např. Ranní. |
| **Od**, **Do** | Výchozí čas směny. |
| **Dny** | **Po–Pá**, **So–Ne**, nebo **Každý den**. V ostatní dny je políčko v plánu šrafované. |
| **Typ směny v rozpisu** | Typ z **Rozpis služeb → Typy směn**, pod kterým se směna zapíše. Určuje barvu a legendu na webu. |

## 4. Obrazovka Plánování

Nahoře šipkami **‹ ›** přepínáte měsíc. Vpravo jsou tlačítka **Personál**, **Export CSV**
a **Tisk**. Pod lištou je panel **Požadavky na směny** (kapitola 6), pod ním plán a dole
**Bilance hodin** (kapitola 9).

**Plán** má v řádcích úseky a jejich směny, ve sloupcích dny měsíce. Dny obou tabulek jsou
přesně nad sebou a posouvají se do stran spolu.

| Co vidíte | Význam |
|---|---|
| Šedý sloupec | Víkend. |
| Žlutý sloupec | Státní svátek (název ukáže bublina nad dnem). Svátky se počítají samy. |
| Červený text pod dnem | Celodenní poznámka z Rozpisu služeb, např. Zavřeno. |
| Šrafované políčko | Tato směna v ten den neplatí. |
| Barevný štítek | Člověk ve směně. U jiného než výchozího času je i čas. |
| Červený rámeček štítku | Pozor: člověk má ten den absenci nebo nemůže, nebo se lékařka nepropisuje do rezervací. Důvod ukáže bublina. |
| Čárkovaný rámeček | Služba zadaná přímo v Rezervace → Rozpis lékařů. |
| Řádek **Absence** | Kdo má ten den D, NV, L, PN nebo Š. |
| Řádek **Z rozpisu – bez úseku** | Směny, které se nehodí do žádného úseku. Jen pro čtení, aby se nic neztratilo. |

Směny zadané v Rozpisu služeb se v plánu ukazují ve směně, která jim nejlíp sedí (podle
ordinace, typu a času).

### Převzít služby z Rozpisu lékařů

Tlačítko **Převzít služby z Rozpisu lékařů (počet)** se ukáže, když má měsíc služby zadané ručně
v Rozpisu lékařů. Převede je na směny v plánu, takže se dál plánují tady; „Jen tyto úkony“
a poznámka u nich zůstanou. Hláška ukáže „Převzato X služeb, přeskočeno Y (ordinace bez úseku
nebo kolize).“

### Kopírování týdne

V hlavičce každého pondělí je malá ikona **⧉**. Zkopíruje do tohoto týdne směny z týdne
předchozího. Přeskočí člověka, který už v té směně je nebo má ten den absenci či **Nemůžu**.
Kopírují se jen dny zobrazeného měsíce. Hláška ukáže „Zkopírováno X směn, přeskočeno Y.“

## 5. Přidání člověka do směny

1. Klikněte do políčka v plánu. Otevře se okno se jménem úseku, směny a dne.
2. Podle potřeby vyberte čas v **Čas nové směny**: výchozí čas směny, rychlé volby (10–18, 8–14,
   9–15, 14–20) nebo vlastní čas ve tvaru 8:00 nebo 14:30.
3. Klikněte na člověka. Hned se přidá. Dalším klikem přidáte dalšího do stejného políčka.
4. Zavřete tlačítkem **Hotovo**.

Lidé jsou seskupení podle role. U jména je vidět, co o něm ten den víme: zadanou dostupnost,
absenci a další směny. Kdo má absenci nebo **Nemůžu**, je bledší, ale přidat ho jde; plán
člověka nezakáže, jen upozorní červeným rámečkem.

Člověk, který už v políčku je, má nahoře v okně řádek. Tam mu změníte čas nebo ho odeberete
tlačítkem **Smazat** (nebo křížkem **×** přímo na štítku v plánu). Takhle jde změnit a smazat
i směna z Rozpisu služeb a ručně zadaná služba z Rozpisu lékařů.

V úseku **Stáž / výpomoc** je navíc políčko na jméno praktikanta nebo brigádníka, který není
v Personálu, a tlačítko **Přidat**.

## 6. Požadavky na směny

Panel nad plánem: v řádcích lidé podle role, ve sloupcích dny. Rozbalíte a sbalíte ho kliknutím
na název, velikost změníte tažením za spodní okraj. Prohlížeč si obojí pamatuje.

Klik do políčka otevře volbu záznamu. Můžete přidat **Poznámku ke dni**, záznam odebrat tlačítkem
**Smazat záznam**, nebo u existujícího záznamu změnit jen poznámku (**Uložit jen poznámku**).
Rychlejší je klávesnice: šipkami se pohybujete mezi políčky, písmenem zapíšete záznam,
**Del** ho smaže, **Enter** otevře volbu.

| V políčku | Záznam | Klávesa | Kdo ho zadává |
|---|---|---|---|
| ✓ | Můžu | M | člen týmu i vedení |
| R | Jen ráno | R | člen týmu i vedení |
| O | Jen odpoledne | O | člen týmu i vedení |
| × | Nemůžu / volno | V | člen týmu i vedení |
| D | Dovolená | D | jen vedení |
| NV | Náhradní volno | N | jen vedení |
| L | Lékař | L | jen vedení |
| PN | Nemoc (PN) | P | jen vedení |
| Š | Školení / kongres | S | jen vedení |

Tečka **•** v políčku znamená, že si to člověk zadal sám, tužka **✎**, že je u dne poznámka.
Na konci řádku jsou součty **D** a **NV** za měsíc a pole **Poznámka k měsíci**. Šipkami **▲ ▼**
u jména posunete člověka v rámci jeho role.

## 7. Dostupnost a absence

**Rozpis služeb → Dostupnost a absence** je stejná data jako Požadavky na směny, ale jako seznam
přes všechny měsíce: **Datum**, **Člen týmu**, **Záznam**, **Poznámka** a **Zadal(a) sám/sama**.
Hodí se k hledání: filtry **Absence** a **Dovolená**, seskupení podle **Člen týmu** a **Záznam**.
Řádky jde upravovat přímo. Jeden člověk má na jeden den jen jeden záznam.

## 8. Jak se plán dostane do kalendáře rezervací

Sám. Když přidáte lékařku do směny v úseku s ordinací, vznikne jí služba v **Rezervace → Rozpis
lékařů** (označená **Z rozpisu služeb**), je vidět v **Rezervace → Kalendář** a podle ní web nabízí
termíny. Změna času nebo smazání v plánu se hned promítne i tam.

Musí platit všechno z tohoto:

1. Člověk má v Lékařkách zaškrtnuto **Lékařka – přijímá rezervace**.
2. Úsek má vyplněnou **Ordinaci v rezervacích**.

Sestry, recepce a výpomoc se do rezervací nepropisují.

**Ranní a odpolední v jedné ordinaci = jedna služba.** Když má lékařka v jeden den v téže ordinaci
směny, které se překrývají nebo na sebe navazují, v rezervacích z nich je jedna služba (8–16
a 12–20 dá 8–20). Slučují se jen směny z plánu. Ručně zadané směny, které se překrývají ve stejné
ordinaci, skončí hláškou „Směnu … nejde propsat do rezervací: …“.

**Kontrola.** V okně políčka je u lékařky zeleně „V kalendáři rezervací: …“, nebo červeně důvod,
proč tam není:

| Hláška | Co s tím |
|---|---|
| „… nemá v Lékařkách zaškrtnuto „Lékařka – přijímá rezervace““ | Zaškrtněte to v Rozpis služeb → Lékařky. Pak směnu smažte a přidejte znovu. |
| „… úsek … nemá v Úsecích plánu vyplněnou ordinaci.“ | Vyplňte ordinaci u úseku. Pak směnu smažte a přidejte znovu. |
| „… směna nemá ordinaci.“ | Smažte směnu a přidejte ji znovu. |
| „V kalendáři rezervací chybí. Uložte směnu znovu (změňte a vraťte čas).“ | Změňte čas a vraťte ho zpět. |

**Web /rozpis-lekaru.** Z plánu se tam ukazují jen služby lékařek v úsecích, ne recepce, sestry
ani výpomoc. Ručně zadané směny a celodenní poznámky se ukazují dál. U směny je na webu čas
jejího typu (Typy směn), ne čas z plánu.

## 9. Bilance hodin

Tabulka pod plánem, jeden řádek na člověka:

| Sloupec | Jak se počítá |
|---|---|
| **Úvazek** | Hodiny za týden z Personálu. |
| **Fond** | Pracovní dny měsíce (po–pá bez státních svátků) × úvazek / 5. |
| **Odpracováno** | Hodiny směn + D, L a Š v pracovní den (každý den úvazek / 5). Překryv směn v jeden den se počítá jednou: 8–16 a 12–20 je 12 hodin. Bublina ukáže rozpad. |
| **Ranní** | Všední dny pod 12 hodin se začátkem před polednem. |
| **Odpolední** | Všední dny pod 12 hodin se začátkem od poledne. |
| **Celodenní (12 h)** | Všední dny s 12 a více hodinami. |
| **Víkendy** | Odsloužené soboty a neděle, v závorce hodiny. |
| **Absence** | Počty D, NV, L, PN a Š. |
| **Saldo** | Odpracováno − fond. Plus je zeleně, minus červeně. |

NV a PN se do odpracovaných hodin nepočítají. Započítávají se i služby zadané ručně v Rozpisu
lékařů. Noční směna se počítá do půlnoci.

## 10. Export a tisk

**Export CSV** stáhne soubor `rozpis-sluzeb-RRRR-MM.csv` pro Excel. Obsahuje plán, řádek Absence,
bilanci a požadavky.

**Tisk** otevře tisk prohlížeče, na šířku na A4. Vytiskne se plán s řádkem Absence a **také Bilance
hodin**. Požadavky na směny a tlačítka se netisknou. Bilanci z tisku vynechat nejde; když ji na
nástěnce nechcete, vyberte v dialogu tisku jen stránky s plánem.

---

# Část B – pro každého člena týmu

## 11. Moje dostupnost

Otevřete **Moje směny → Moje dostupnost**. Otevře se příští měsíc, protože se plánuje dopředu;
šipkami **‹ ›** přepnete jiný.

Pokud vidíte hlášku „Váš účet není propojený s členem týmu“, požádejte vedení, ať vás propojí.

Nahoře vidíte **Úvazek**, **Fond měsíce**, **Naplánováno** a **Zbývá dovolené**. Pod tím je kalendář
měsíce.

**Jak zadat dostupnost:**

1. Klikněte na den.
2. Případně napište poznámku, třeba „chci dovolenou“ nebo „do 14:00“.
3. Vyberte **Můžu**, **Jen ráno**, **Jen odpoledne** nebo **Nemůžu / volno**.

Záznam odstraníte tlačítkem **Smazat** v tomtéž okně. Tlačítko **Zbytek měsíce: Můžu** vyplní
všechny dny od dneška do konce zobrazeného měsíce, které ještě nemají záznam. Pak stačí
opravit výjimky.

**Co si zadat nejde:**

- Minulé dny už měnit nejde.
- Dovolenou, náhradní volno, lékaře, nemoc a školení zapisuje vedení. V kalendáři mají zámek 🔒
  a nejdou změnit. Přání napište do poznámky ke dni, nebo se domluvte s vedením.

**Moje směny.** Naplánované směny vidíte v modrém štítku u dne, s úsekem a časem. Mění je jen
vedení. Do **Naplánováno** se počítají i služby zadané v Rozpisu lékařů a dny D, L a Š, takže
číslo může být vyšší než součet štítků.
