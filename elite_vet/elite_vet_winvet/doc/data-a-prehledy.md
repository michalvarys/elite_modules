# Data a přehledy – návod pro vedení

**K čemu je tento návod.** Popisuje aplikaci **WinVet data**: jak číst přehled tržeb, výdajů a zisku,
jak si data rozebrat a vyexportovat, jak zapisovat výdaje, tisknout uzávěrku a regletu skladu a co
dělat, když Odoo hlásí problém s přenosem z WinVetu. Aplikaci **WinVet data** vidí jen vedení.

**Odkud data jsou.** Tržby, doklady, platby, zálohy, ceník a sklad se zapisují ve WinVetu. Do Odoo je
posílá program, kterému říkáme most. V aplikaci **WinVet data** se tato data nedají měnit, opravují se
ve WinVetu a při dalším přenosu se změna ukáže tady. Jediné, co zapisujete přímo v Odoo, jsou
**výdaje**, protože WinVet zná jen tržby.

**Jak čerstvá data jsou.** Přehled ukazuje nahoře „data z WinVetu do …“, Regleta skladu datum
posledního pohybu a **Stav synchronizace** čas posledního příjmu dat. Když se data přenášejí ze zálohy
WinVetu, jsou stará jako ta záloha – dnešní tržby v takovém případě ještě nevidíte.

Co v menu najdete:

| Položka | K čemu je |
|---|---|
| **Přehled** | Tržby, výdaje a zisk za období, grafy, srovnání (kapitola 1) |
| **Tržby** | **Uzávěrka**, **Tržby podle položek**, **Úkony**, **Léky a zboží** (kapitoly 2 a 6) |
| **Regleta skladu** | PDF pro účetní (kapitola 7) |
| **Výdaje** | Zápis výdajů (kapitola 3) |
| **Doklady**, **Platby**, **Zálohy** | Doklady, přijaté platby a zálohy klientů z WinVetu (kapitoly 4 a 5) |
| **Návštěvy**, **Očkování**, **Ceník**, **Uživatelé WinVet** | Údaje z WinVetu ke čtení |
| **Kalendář z WinVetu** | Objednávky z WinVetu (kapitola 8) |
| **Stav synchronizace**, **Změny struktury WinVetu** | Jestli přenos funguje (kapitoly 9 až 11) |
| **Konfigurace** | **API klíč** pro most a **Kategorie výdajů** |

---

## 1. Přehled

**WinVet data → Přehled** se otevře s nadpisem **Přehled tržeb a výdajů**.

### Co zobrazit a za jaké období

Vlevo nahoře přepínáte **Tržby i výdaje**, **Jen tržby** a **Jen výdaje**. Volbu si pamatuje váš
prohlížeč. Dokud není zapsaný žádný výdaj, začíná přehled na **Jen tržby**.

Období vyberete tlačítkem nebo vlastními daty v polích vpravo:

| Tlačítko | Srovnává se s |
|---|---|
| **Dnes**, **Včera** | stejným dnem před týdnem |
| **Tento týden** | stejnou částí minulého týdne |
| **Minulý týden** | týdnem před ním |
| **Tento měsíc** (výchozí) | stejnou částí minulého měsíce |
| **Minulý měsíc** | předminulým měsícem |
| **Letos** | stejnou částí loňského roku |
| **Od začátku** | nesrovnává se |
| vlastní data | stejně dlouhým obdobím těsně před tím |

Pod nadpisem je vidět, jaké období a s čím se srovnává a do kterého dne jsou data z WinVetu.

### Dlaždice

| Dlaždice | Co znamená |
|---|---|
| **Tržby (položky)** | Součet položek dokladů z WinVetu podle data položky, tedy podle data návštěvy. Bez ohledu na to, jestli už je doklad zaplacený. |
| **Výdaje bez DPH** | Součet výdajů bez DPH. |
| **Zisk (tržby − výdaje)** | Tržby minus výdaje za stejné období. Záporný je červeně. |
| **Úkony**, **Léky a zboží** | Část tržeb podle druhu položky. |
| **Přijaté platby** | Platby podle data platby. Může se od tržeb lišit: doklad bez úhrady je v tržbách, ale ne v platbách, a platba může přijít jiný den než návštěva. |
| **Návštěvy s účtem** | Počet návštěv, které mají v období položku účtu. |
| **Průměr na návštěvu** | Tržby děleno návštěvami s účtem. |
| **Počet výdajů**, **Průměrně za den** | Jen v režimu **Jen výdaje**. |

> **Zisk je orientační.** Tržby jsou částky z dokladů včetně DPH, výdaje se počítají bez DPH. Nejde
> o účetní výsledek a počítá jen s výdaji, které jsou zapsané v Odoo.

Pod částkou je změna proti srovnávanému období: ▲ / ▼ s procenty, „nové“, když srovnávané období bylo
nulové, nebo „víc než 10×“. Zelená je změna k lepšímu, červená k horšímu. U výdajů je tedy růst červeně.

### Grafy a tabulky

- **Tržby, výdaje a zisk v čase** (podle režimu **Tržby v čase** nebo **Výdaje v čase**) – po dnech,
  u období delšího než 62 dní po měsících.
- **Výdaje podle kategorií** a **Největší výdaje** – deset nejvyšších výdajů.
- **Podle toho, kdo zapsal** – tržby podle uživatele WinVetu.
- **Formy platby** a **Druhy zvířat**.
- **Nejčastější úkony** a **Nejprodávanější léky a zboží** – deset položek s nejvyšší částkou, vedle
  ní je počet.

### Rozkliknutí

Kliknutím na dlaždici, řádek tabulky nebo část grafu (uživatel, forma platby, druh zvířete, kategorie
výdajů) se otevřou záznamy, ze kterých číslo vzniklo, už omezené na vybrané období. Odtud je můžete
dál třídit a exportovat (kapitola 2). Zpět se dostanete přes drobečkovou navigaci vlevo nahoře.

Tlačítko **Zapsat výdaj** vpravo nahoře otevře nový výdaj, přehled se po uložení sám přepočítá.

## 2. Tržby: kontingenční tabulky, grafy a export

**WinVet data → Tržby** má tři pohledy na stejná data:

- **Tržby podle položek** – všechny položky, řádky jsou měsíce, sloupce druh položky.
- **Úkony** – jen úkony, řádky jsou položky, sloupce měsíce.
- **Léky a zboží** – jen léky a zboží, řádky jsou položky, sloupce měsíce, s množstvím i částkou.

Vpravo nahoře přepínáte kontingenční tabulku, graf a seznam.

**Kontingenční tabulka.** V **Měřítka** vyberete, co se sčítá: **Částka** (s DPH), **Základ
DPH**, **DPH** nebo **Množství**. Kliknutím na název řádku nebo sloupce přidáte další členění.

**Filtry a seskupení** jsou pod šipkou vpravo v poli hledání:

- Filtry **Úkony**, **Léky a zboží**, **Ostatní** a **Datum**.
- **Seskupit**: **Měsíc**, **Týden**, **Den**, **Druh položky**, **Forma úhrady**, **Sazba DPH**,
  **Položka**, **Zapsal(a)**, **Lékařka**, **Druh zvířete**, **Majitel**.
- V **Oblíbené** jsou připravené pohledy pro všechny: **Úkony podle měsíců**, **Léky a zboží podle
  položek** a **Tržby podle toho, kdo zapsal**.

**Forma úhrady** se bere z dokladu: **Hotově**, **Kartou**, **Převodem**, **Jinak**, **Kombinovaně**
(víc forem na jednom dokladu) nebo **Bez úhrady** (žádná platba s nenulovou částkou).

**Export.** V kontingenční tabulce je ikona pro stažení, která uloží tabulku do Excelu (**Stáhnout
xlsx**). V seznamu klikněte na ozubené kolo vedle názvu a zvolte **Exportovat vše**, nebo zaškrtněte
řádky a dejte **Akce → Export**.

## 3. Výdaje

Výdaje zapisujete ručně: **WinVet data → Výdaje → Nový**, nebo **Zapsat výdaj** v Přehledu.

| Pole | Co vyplnit |
|---|---|
| **Popis** | např. Nájem říjen, Faktura od dodavatele |
| **Datum**, **Kategorie** | povinné |
| **Částka s DPH** | celá částka, kterou klinika zaplatila; musí být větší než nula |
| **DPH** | **Bez DPH**, **12 %** nebo **21 %**. **Bez DPH** použijte i u dodavatele, který není plátce. **Bez DPH** níž ve formuláři ukáže částku, která jde do zisku. |
| **Zaplaceno** | jak se platilo (výchozí **Převodem**) |
| **Dodavatel**, **Číslo dokladu**, **Poznámka** | nepovinné |
| **Opakovat měsíčně do** | jen při zakládání, viz níže |

**Pravidelné platby.** U nájmu vyplňte **Opakovat měsíčně do**. Výdaj se zkopíruje na stejný den každého
dalšího měsíce až do tohoto data, nejvýš na 36 měsíců. Každá kopie je samostatný výdaj, takže jde
upravit nebo smazat zvlášť. Kopie s budoucím datem se započítají až ve svém měsíci.

**Doklad.** Fotku nebo PDF přiložte sponkou v pravém panelu. Filtr **Bez přiloženého dokladu** ukáže,
kde doklad chybí.

**Přehledy.** Seznam má filtr **Tento měsíc**, seskupení podle kategorie, dodavatele a měsíce, a umí
kontingenční tabulku a graf. Export funguje stejně jako v kapitole 2.

**Kategorie výdajů** upravíte v **Konfigurace → Kategorie výdajů**: název, barvu v grafu a to, jestli je
aktivní. Kategorii, která už má výdaje, nejde smazat, můžete ji jen vypnout.

**Výdaje z příjmu zboží.** Dokud sklad vede WinVet, příjem zboží v Odoo výdaj nezapisuje. Po přechodu
na sklad v Odoo se výdaj zapíše sám, viz návod
[Pokladna a sklad](../../elite_vet_sale/doc/pokladna-a-sklad.md). Nákupy si do té doby zapisujte ručně,
aby je zisk zahrnoval.

## 4. Doklady

**WinVet data → Doklady** je seznam dokladů z WinVetu: **Účet majitele**, **Doklad PODP** (příjmový
doklad), **Faktura vydaná** a **Vratka**. Otevřený doklad ukazuje položky a platby.

- **Celkem** a **Zaplaceno** jsou částky z dokladu, **Ze zálohy** je část zaplacená ze zálohy klienta.
- **Forma úhrady** se počítá z plateb, **Forma na dokladu** je to, co je na dokladu zapsané ve WinVetu.
  U vratky říká, jak se vracelo. U dokladu bez platby to samo o sobě neznamená, že peníze přišly.
- Seskupit jde podle měsíce, typu, formy úhrady, toho, kdo doklad založil, a majitele.
- Filtr **Nedoplacené** ukáže všechny doklady s kladnou částkou, ne jen ty nezaplacené. Zaplacené porovnejte
  se sloupcem **Zaplaceno**. Doklady bez platby spolehlivě ukáže seskupení podle **Forma úhrady** →
  **Bez úhrady**.

## 5. Platby a zálohy

**WinVet data → Platby** ukazuje přijaté platby podle data platby. Otevře se kontingenční tabulka: řádky
jsou měsíce, sloupce forma úhrady. Filtry jsou **Hotově**, **Kartou**, **Převodem**, **Vrácené** a **Datum**.
Sloupec **Ze zálohy** ukazuje část platby zaplacenou ze zálohy.

**WinVet data → Zálohy** ukazuje zálohy klientů: kdy a jak byly přijaté, kolik se čerpalo, vrátilo a co
zbývá. Filtr **S zůstatkem** ukáže zálohy, které klient ještě nevyčerpal. Otevřená záloha ukazuje čerpání
do dokladů. Přijatá záloha není platba, proto v **Platby** není. WinVet u vrácení zálohy formu úhrady nevede,
Odoo ji proto bere jako hotovost.

## 6. Uzávěrka (PDF)

**WinVet data → Tržby → Uzávěrka**, nebo tlačítko **Uzávěrka (PDF)** v seznamech **Tržby podle položek**,
**Doklady** a **Platby**.

1. Zvolte **Tento měsíc**, **Minulý měsíc**, **Dnes**, **Včera** nebo **Jiné období** a případně upravte
   **Od** a **Do**.
2. Klikněte **Vytisknout PDF**.

Sestava je z dat WinVetu, není to denní uzávěrka pokladny v Odoo. Obsahuje:

1. **Tržby podle dokladů** – příjmové doklady, faktury a vratky podle data dokladu, vratky se odečítají.
   Zahrnuje i doklady bez úhrady.
2. **Přijaté platby a vratky** – podle formy úhrady: nové úhrady dokladů, přijaté zálohy, vrácené částky
   a příjmy po vrácení. Čerpání zálohy není nový příjem.
3. **Denní rozpis** – jen u období delšího než jeden den a jen dny s nějakými daty.
4. **Faktury a doklady bez úhrady.**
5. **Zálohy** – přijaté v období, jejich čerpání, vrácení a zůstatek ke konci období.
6. **Tržby podle položek a formy úhrady.** Převody nedoplatku z dřívějšího dokladu nejsou položky a jsou
   vypsané zvlášť pod tabulkou **Peněžní řádky mimo položky**.
7. **Rozpis DPH** – základ a daň podle sazby na řádcích dokladů.

U jednodenní uzávěrky denní rozpis chybí, takže se další části číslují o jedno níž. Na konci jsou řádky
pro podpis **Předal/a** a **Převzal/a**.

## 7. Regleta skladu (PDF pro účetní)

**WinVet data → Regleta skladu**: zvolte **Minulý měsíc** (výchozí), **Tento měsíc**, **Tento rok**,
**Minulý rok** nebo **Jiné období** a klikněte **Vytisknout PDF**.

Sestava za období ukazuje:

1. **Souhrn** – počáteční stav, příjem, výdej a konečný stav po skupinách, bez DPH a s DPH.
2. **Příjemky v období** s dodavatelem a **Rekapitulace DPH příjmu**.
3. **Pohyb po položkách** – množství a hodnoty každé položky.
4. **Položky se záporným stavem** – jen když nějaké jsou. Vydalo se z nich víc, než se přijalo: chybí
   příjemka, nebo je výdej zadaný ve špatném množství či jednotce. Opravit je to potřeba ve WinVetu.

Dobré vědět:

- Data jsou stará jako poslední přenos. Datum posledního pohybu je v záhlaví sestavy.
- **Hodnota se liší od WinVetu.** WinVet přičítá příjem s DPH, ale odečítá výdej bez DPH. Regleta počítá
  obě strany stejně, vysvětlení je na konci sestavy v části **Jak se počítá**.
- Když období končí posledními daty, je pod souhrnem kontrola, u kolika položek konečné množství souhlasí
  s WinVetem. Položky, které se liší, je potřeba ověřit ve WinVetu.
- Když sestava píše, že z WinVetu nepřišly žádné pohyby skladu, je potřeba novější verze mostu. Obraťte se
  na správce.

## 8. Kalendář z WinVetu

Objednávky zapsané ve WinVetu se ukazují v **Kalendáři** v Odoo i v pokladně jako šedé šrafované karty se
štítkem **WinVet** a obsazují termín pro objednávání v Odoo. Recepce je vidí tam (viz návod
[Recepce v pokladně](../../elite_vet_reception/doc/recepce-v-pokladne.md)). Přenáší se období od včerejška
na 60 dní dopředu a jen jedním směrem, do WinVetu Odoo nic nezapisuje.

V **WinVet data → Kalendář z WinVetu** má vedení:

- **Záznamy** – seznam přenesených záznamů jen ke čtení. Filtry **Dnes**, **Od dneška** (výchozí), **S časem**,
  **Celodenní**, **Bez ordinace**, **Se zvířetem z kartotéky**.
- **Kalendáře → ordinace** – který kalendář WinVetu patří ke které ordinaci. Přiřadí se sám podle názvu.
  Když ordinaci vyberete ručně, přenos ji už nezmění. Kalendář bez ordinace se v Kalendáři neukazuje
  a nic neblokuje.
- **Činnosti → úkony** – která činnost WinVetu odpovídá kterému úkonu. Filtr **Bez úkonu** ukáže, co
  zbývá přiřadit.
- **Zapnout / vypnout** – **Vypnout kalendář z WinVetu** schová záznamy z kalendáře, přestanou blokovat
  termíny a nové se neukládají (hodí se pro přechod na objednávání v Odoo). **Smazat přenesené záznamy**
  smaže přenesené záznamy jen v Odoo, ve WinVetu zůstanou; když je kalendář zapnutý, další přenos je
  znovu naplní.

## 9. Stav synchronizace

**WinVet data → Stav synchronizace** ukazuje, jestli přenos běží.

- **Poslední příjem dat** a **Poslední hlášení stavu** – kdy se most naposledy ozval. Když se tyto časy
  nemění, most neběží nebo se nedostane k Odoo. Odoo na to samo neupozorní, proto se sem občas podívejte.
- **Verze mostu**, **Verze WinVetu**, **Zdroj dat** (live = živá databáze, backup = záloha).
- **Zablokované oblasti** – co most kvůli změně ve WinVetu nečte.
- **Zpráva mostu** a **Poslední chyba** – text pro správce.

Záložky:

- **Poslední běh** – po oblastech (majitelé, doklady, platby…) kolik záznamů je nových, změněných, smazaných
  a přeskočených. **Přeskočené** jsou žlutě.
- **Změny struktury** – aktuální rozdíly proti schválenému stavu.
- **Otisky struktury** – technické údaje pro správce.
- **Zrcadlo skladu** – kdy se naposledy převzal sklad z WinVetu a upozornění na rozdíly, např. když vrstvy
  skladu nesedí na stav položky.

## 10. Změny struktury WinVetu

Po aktualizaci WinVetu se může změnit jeho databáze. Most to při každém běhu kontroluje a rozdíly zapíše do
**WinVet data → Změny struktury WinVetu**. Seznam ukazuje jen **Neprověřené**. Filtr **Blokující a žurnál**
vybere to důležité.

| Závažnost | Co to znamená |
|---|---|
| **Blokující** | Dotčená oblast se nečte, její data v Odoo zůstávají stará. |
| **Žurnál změn** | Přenos změn není spolehlivý, most místo něj posílá všechno. Data jsou v pořádku, jen přenos trvá déle. |
| **Upozornění** | Změna v tabulce, kterou most čte, ale čtení běží dál. |
| **Informace** | Změna mimo to, co most čte. Jen na vědomí. |

Přepínač **Prověřeno** si označíte, že změnu někdo zkontroloval. Na přenos nemá vliv.

## 11. Co dělat při upozornění

Vedení dostane aktivitu **WinVet – zkontrolujte synchronizaci** a na **Stavu synchronizace** se objeví
červený pruh **Pozor:**. Stává se to, když se aktualizoval WinVet, některá oblast je zablokovaná nebo se
změnila struktura tabulek, které most čte.

1. Otevřete **Stav synchronizace** a přečtěte si pruh a **Zablokované oblasti**.
2. Počítejte s tím, že data zablokovaných oblastí jsou stará. Přehledy z nich mohou být neúplné, dokud
   se blokace nevyřeší. WinVetu se nic nestalo a ostatní oblasti se přenášejí dál.
3. Předejte text upozornění správci. Ten ověří novou verzi WinVetu a v mostu ji schválí. Vy nic schvalovat
   nemusíte. Po schválení se zablokované oblasti samy doplní.
4. **Potvrdit upozornění** klikněte, až o věci správce ví. Tlačítko jen schová pruh a uzavře aktivitu,
   problém tím nevyřeší. Stejná blokace se znovu nehlásí, takže po potvrzení sledujte **Zablokované oblasti**.

Když upozornění není, ale čísla nesedí:

- Podívejte se na „data z WinVetu do …“ a na **Poslední příjem dat**. Starší čas znamená, že přenos neběží.
- **Poslední chyba** nebo **Přeskočené** v **Poslední běh** předejte správci.
