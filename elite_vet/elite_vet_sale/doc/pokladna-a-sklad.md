# Pokladna a sklad – návod pro recepci

**K čemu je tento návod.** Popisuje, jak účet z karty pacienta dojde do pokladny, jak ho
recepce zaplatí (kartou, hotově, převodem, se zálohou nebo fakturou), jak se dělá vratka
a uzávěrka, a jak recepce přijímá zboží čtečkou a hlídá sklad. Pokladnu a sklad má uživatel se
skupinou **Pokladna a sklad (recepce)** – recepce ji dostane s rolí, vedení ji má vždy; lékařka
a sestra do pokladny ani do skladu nevidí (zboží může přijímat sestra, jen když jí vedení skupinu
zapne ručně). Technické nastavení (pro
správce) je v [README modulu](../README.md), část „Pro správce“. Celý pracovní den recepce v pokladně
(záložky **Dnes**, **Kartotéka…**, **Objednat**, **Kalendář**) popisuje návod
[Recepce v pokladně](../../elite_vet_reception/doc/recepce-v-pokladne.md).

Kde co najdete:

- **Pokladna Recepce** – recepci se otevře sama po přihlášení do Odoo. Jinak aplikace **Prodejní
  místa** → pokladna **Recepce** → **Otevřít pokladnu** (nebo **Pokračovat v prodeji**, když už je
  otevřená).
- **Příjem zboží** – aplikace **Sklady → Příjem zboží**.
- **Přehled skladu** – aplikace **Sklady → Přehled skladu**.

Recepce má v aplikaci **Sklady** jen tyto dvě položky. Ostatní nabídky skladu a aplikaci
**Fakturace** vidí jen vedení.

> **Zkušební provoz.** Dokud ve WinVetu běží ostrý provoz, vede ceník a sklad WinVet. Odoo jeho
> stav po každé synchronizaci převezme. Prodej v pokladně i příjem zboží si můžete vyzkoušet,
> ale stav skladu se při další synchronizaci přepíše stavem WinVetu a příjem nezapisuje výdaj.
>
> **Jen pro čtení.** Správce systému může zapnout režim, ve kterém se pracuje jen ve WinVetu. V horní
> liště pokladny je pak štítek **Jen pro čtení**. Pokladna se otevře a všechno ukáže, ale platbu
> neuloží („Pokladna je zatím jen pro čtení – prodává se ve WinVetu. Účet se neuloží.“) a nic neuložíte
> ani v kartě pacienta. Vedení se tento režim netýká.

---

# Část A – recepce

## 1. Jak se účet dostane k pokladně

Účet vzniká v **kartě pacienta**. Lékařka (nebo sestra) přidá do části **Účet** úkony
(**+ Úkon**), léky (**+ Lék ze skladu**) nebo balíček (**Přidat balíček**) a upraví množství.

![Účet v kartě pacienta](img/karta-ucet.png)

Na konci návštěvy klikne **Hotovo, k pokladně** a potvrdí:

![Potvrzení Hotovo](img/karta-hotovo-potvrzeni.png)

*Obrázky z karty mají ještě starý název: místo **Tabule** je teď všude **Kalendář**.*

Od té chvíle:

- záznam je uzavřený a v kartě je štítek **Čeká na platbu · S00400** (číslo objednávky,
  pod kterým účet najdete v pokladně) s poznámkou „Recepce účet najde v pokladně pod tlačítkem
  Objednávka“ (to je **Akce → Nabídka/Objednávka**),
- v **kalendáři** má rezervace žlutý štítek **k pokladně**,
- v pokladně je účet na záložce **Dnes** ve sloupci **K pokladně**.

![Karta po Hotovo](img/karta-k-pokladne.png)

![Štítek k pokladně v kalendáři](img/tabule-k-pokladne.png)

Když lékařka záznam znovu otevře a doplní, nové **Hotovo** účet přepíše – pořád je to tatáž
objednávka, nic se nezdvojí. Má-li ale recepce účet právě rozpracovaný v pokladně, **Hotovo** skončí
hláškou „Recepce účet právě vyřizuje v pokladně – počkejte na dokončení platby.“ – počkejte,
až recepce platbu dokončí (nebo objednávku v pokladně zruší), a zkuste to znovu.

## 2. Zaplacení účtu (vyrovnání objednávky)

Nejkratší cesta je záložka **Dnes** → sloupec **K pokladně** → **Zaplatit**. Pokladna sama načte účet
i se zákazníkem a otevře platbu, takže pokračujete rovnou krokem 5 (podrobně v návodu
[Recepce v pokladně](../../elite_vet_reception/doc/recepce-v-pokladne.md), část Zaplatit).

Účet můžete najít i ručně na záložce **Pokladna**:

1. V pokladně klikněte vlevo dole na **Akce** a pak na **Nabídka/Objednávka**.

   ![Akce v pokladně](img/pokladna-akce.png)

   *Obrázky pokladny jsou ze starší verze: v horní liště jsou teď navíc záložky a tlačítko
   **Zákazník** se jmenuje **Klient**.*

2. Otevře se seznam objednávek. Najděte účet podle čísla (S…) nebo podle jména majitele
   a klikněte na řádek.

   ![Seznam objednávek](img/pokladna-objednavky.png)

3. V okně **Co chcete udělat?** zvolte **Vyrovnat objednávku**.

   ![Vyrovnat objednávku](img/pokladna-vyrovnat.png)

4. Položky účtu se načtou do pokladny i se zákazníkem (majitel). Zkontrolujte je
   a klikněte na **Platba**.

   ![Načtená objednávka](img/pokladna-objednavka-nactena.png)

5. Zvolte způsob platby: **Kartou**, **Hotově** nebo **Převodem**.
   - **Kartou:** pokladna není spojená s platebním terminálem. Částku z obrazovky
     (velké zelené číslo) **opište do terminálu banky** a nechte klienta zaplatit. To je
     jediný ruční krok.
   - **Hotově:** napište, kolik klient dal (nebo použijte +10/+20/+50); pokladna spočítá,
     kolik vrátit.
   - **Převodem:** platba převodem na účet kliniky.
6. Chce-li klient fakturu, zapněte **Faktura** (viz další kapitola).
7. Klikněte **Potvrdit**.

![Platba kartou s fakturou](img/pokladna-platba-kartou.png)

Zobrazí se **Platba byla úspěšná** a náhled účtenky. **Vytisknout účtenku** ji vytiskne,
**Nová objednávka** založí další prázdný účet, záložka **Dnes** vás vrátí na přehled. Pole s e-mailem a tlačítko vedle něj účtenku
**pošle klientovi e-mailem** – použijte ho, jen když o to klient stojí. Spletli jste se ve
způsobu platby? **Editovat platbu** ji ještě opraví.

![Po zaplacení](img/pokladna-uctenka.png)

Po zaplacení:

- v kartě pacienta je štítek **Zaplaceno**, v kalendáři zelený štítek **zaplaceno**,
- léky se odepíšou ze skladu, a to vždy ze šarže s **nejbližší expirací** – na šarži se
  pokladna neptá.

![Zaplaceno v kartě](img/karta-zaplaceno.png)

![Štítek zaplaceno v kalendáři](img/tabule-zaplaceno.png)

## 3. Faktura

Na platební obrazovce klikněte na **Faktura** (zaškrtávací políčko se zapne). Faktura se vystaví na
zákazníka z objednávky, tedy majitele pacienta. Po **Potvrdit** se faktura vytvoří jako
zaplacená (číslo INV/…); vedení ji najde i v Odoo v **Fakturace → Zákazníci → Faktury**.

Účet z karty pacienta nejde přepsat na jiného zákazníka. Když na něm v **Kartotéce** (tlačítko **Klient**
nebo **Zákazník** na platební obrazovce) vyberete jiného klienta, pokladna založí nový prázdný účet a ten
původní zůstane nezaplacený v **K pokladně**. Faktura na firmu proto vyjde jen tehdy, když je firma
v kartotéce sama majitelem pacienta, nebo u prodeje bez návštěvy, kde firmu vyberete tlačítkem **Klient**
před platbou (**Vybrat k účtu**). V ostatních případech se poraďte s vedením.

## 4. Záloha

1. **Akce → Nabídka/Objednávka** → účet → místo „Vyrovnat objednávku“ zvolte **Zaplatit zálohu
   (fixní částkou)** nebo **Zaplatit zálohu (v procentech)**.
2. Zadejte částku (nebo procento), **Platba**, způsob platby, **Potvrdit**.

Záznam má potom stav **Částečně zaplaceno** a v kalendáři zůstává štítek **k pokladně**
(po najetí myší „Částečně zaplaceno“). Zbytek doplatíte stejně jako celý účet
(**Dnes → K pokladně → Zaplatit**, nebo **Akce → Nabídka/Objednávka → Vyrovnat objednávku**) –
zaplacená záloha se odečte sama.

Na účet se zálohou už lékařka nemůže záznam znovu otevřít („Na účet už je zaplacená
záloha…“) – změny je třeba vyřešit v pokladně.

## 5. Vratka

Zaplacený záznam už nejde znovu otevřít ani zrušit. Když je potřeba vrátit peníze (vrácený lék,
chyba v účtu), udělejte **vratku v pokladně**:

1. Menu pokladny (☰ vpravo nahoře) → **Objednávky**, v hledání přepněte na zaplacené –
   nebo vlevo dole **Akce → Refundace** (otevře rovnou seznam zaplacených objednávek).
2. Najděte objednávku, vyberte řádky, které se vracejí, a klikněte na **Refundace**.
3. Zaplaťte vratku stejným způsobem, jakým klient platil (u karty vraťte peníze v terminálu).

Záznam v kartě zůstane **Zaplaceno** – vratka je samostatný doklad v pokladně.

## 6. Když lékařka znovu otevře už zaplacený účet

Může se stát, že lékařka záznam znovu otevře a recepce mezitím účet zaplatí. Až lékařka
klikne **Hotovo**, záznam se uzavře, ale **položky účtu se už nezmění** a do historie záznamu
se zapíše „Účet už byl zaplacen v pokladně – položky účtu se nezměnily.“ Pokud lékařka něco
přidala, zaplaťte to v pokladně zvlášť (nová objednávka), případně vraťte vratkou.

## 7. Uzávěrka (konec dne)

1. Menu pokladny (☰) → **Zavřít pokladnu**.
2. Přepočítejte hotovost v pokladně a napište ji do **Počítané** u Hotově. Karty a převody
   zkontrolujte proti výpisu z terminálu.
3. Rozdíl, pokud nějaký je, vysvětlete v poznámce.
4. Klikněte **Zavřít relaci**. Tržby dne se zaúčtují; další den otevřete pokladnu znovu.

Tohle je denní uzávěrka pokladny v Odoo. **Uzávěrka (PDF)**, kterou tiskne vedení, je něco jiného:
počítá se z dat WinVetu, viz návod
[Data a přehledy](../../elite_vet_winvet/doc/data-a-prehledy.md).

---

# Část B – příjem zboží a sklad (recepce)

## 8. Čtečka čárových kódů

Na léky je potřeba **2D čtečka** (čte DataMatrix na krabičkách), nastavená tak, aby
**posílala oddělovač skupin GS1 (FNC1)**. Bez něj se šarže a expirace z kódu nedají
spolehlivě rozdělit. V režimu „klávesnice“ čtečka posílá FNC1 jako **Ctrl+]** – Odoo ho
rozpozná. Jak to zapnout, najdete v návodu ke čtečce (obvykle naskenováním
nastavovacího kódu „GS1 / FNC1 → GS (0x1D)“ nebo „Ctrl+]“). Čtečka má za kódem posílat **Enter**.

Kontrola: naskenujte DataMatrix léku. Když se v řádku vyplní šarže i expirace, je čtečka
nastavená správně.

## 9. Příjem zboží

![Příjem zboží](img/prijem-radky.png)

*Obrázky jsou z aplikace **Ordinace**, kde tuto obrazovku má vedení. Recepce ji otevírá v aplikaci **Sklady**.*

1. Otevřete **Sklady → Příjem zboží**.
2. **Dodavatel:** začněte psát název; naposledy použití dodavatelé jsou nahoře. Nový
   dodavatel se založí jen se jménem.
3. Volitelně **Dodací list** – číslo dodacího listu (dá se i naskenovat).
4. **Pípejte.** Pole pro čtečku má kurzor pořád, nic nemusíte kliknout.
   - Kód z krabičky (DataMatrix) vyplní **produkt, šarži a expiraci**.
   - Obyčejný čárový kód (EAN) vyplní produkt; šarže a expirace se předvyplní z posledního
     příjmu – zkontrolujte je a případně opravte.
   - Další pípnutí stejné šarže přidá **+1 ks**. Množství jde změnit i tlačítky − / +. Řádek smažete
     ikonou koše.
   - **Neznámý kód:** otevře se okno **Neznámý kód** – vyhledejte produkt a vyberte ho.
     Kód se uloží a příště se pozná sám (stačí jednou).
   - **Chybí šarže:** u léku se šaržemi bez šarže v kódu se kurzor přesune do pole Šarže –
     napište ji (nebo ji naskenujte) a doplňte expiraci.
   - **Prošlá šarže:** řádek s prošlou expirací dostane červené upozornění **Prošlá šarže**.
     Zkontrolujte, jestli zboží opravdu přišlo prošlé; přijmout ho jde.
5. **Cena/MJ bez DPH** je předvyplněná poslední nákupní cenou – podle dodacího listu ji opravte.
6. Klikněte **Naskladnit**. Tlačítko je aktivní, až je vybraný dodavatel a každý řádek má šarži; dole
   napoví, co chybí („Vyberte dodavatele.“, „Doplňte šarži u 2 řádků.“). Zboží se naskladní na šarže
   s expiracemi a zapíše se výdaj (kategorie Léky a zdravotnický materiál) do **Přehledu tržeb
   a výdajů**, který vidí vedení. Zboží zdarma (cena 0) výdaj nezapíše.

![Výdaj z příjmu v Přehledu tržeb a výdajů](img/prehled-vydaje.png)

**Zkušební provoz.** Dokud sklad vede WinVet, je nahoře žluté upozornění. Příjem se provede,
ale **výdaj se nezapíše** a stav skladu se při další synchronizaci z WinVetu přepíše. Zboží
dál přijímejte i ve WinVetu.

![Upozornění zkušebního provozu](img/prijem-zkusebni-provoz.png)

## 10. Přehled skladu

**Sklady → Přehled skladu** ukazuje, co je na skladě, po šaržích: produkt, šarže, expirace
a množství. Řádky jsou seskupené podle produktu – kliknutím na produkt uvidíte jeho šarže.

![Přehled skladu](img/prehled-skladu.png)

*Na obrázcích je menu vedení; recepce má v aplikaci **Sklady** jen **Přehled skladu** a **Příjem zboží**.*

Řádek se záporným množstvím je červeně.

Ve vyhledávání (šipka vpravo v poli hledání) jsou filtry:

| Filtr | Co ukáže |
|---|---|
| **Dochází** | Zboží pod minimem z pravidla doplnění a zboží se záporným stavem (prodané, i když podle Odoo na skladě nebylo). |
| **Expiruje do 30 dní** | Šarže, které jsou na skladě a projdou během příštích 30 dní. |
| **Prošlé** | Šarže, které jsou na skladě a už prošly. |

![Filtry přehledu skladu](img/prehled-skladu-filtry.png)

Úplně vyprodané zboží (stav 0) v přehledu není – vedení ho najde v **Sklady → Operace →
Doplňování zboží → Doplňování**. Stejné filtry jsou i v **Sklady → Produkty → Šarže / sériová čísla**
(také jen pro vedení).

Minimum pro „Dochází“ nastaví vedení jako pravidlo doplnění u produktu
(Sklady → Operace → Doplňování zboží → Doplňování, nebo na kartě produktu → Min/Max).
