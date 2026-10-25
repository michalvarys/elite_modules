# Recepce v pokladně a Moji pacienti dnes – návod pro recepci, lékařky a vedení

**K čemu je tento návod.** Popisuje jeden pracovní den: recepce pracuje jen v pokladně **Recepce**
(příchody, čekárna, kartotéka, objednávání, placení), lékařka a sestra v **Moji pacienti dnes**
a kartě pacienta. Poslední část je pro **vedení** (role, zaměstnanci s PINem). Technické
podrobnosti pro správce jsou v [README modulu](../README.md), část „Pro správce“.

Navazující návody:

- [Pokladna a sklad](../../elite_vet_sale/doc/pokladna-a-sklad.md) – faktura, záloha, vratka,
  uzávěrka, příjem zboží,
- [Rezervace – návod pro recepci](../../elite_vet_reservation/doc/recepce.md) – tabule, žádosti
  z webu, průvodce rezervací,
- [Obrazovka Ordinace](ordinace.md) – účet pro každou ordinaci, pacienti podle ordinací, přiřazení
  do ordinace a Zavolat.

Cesta návštěvy:

| Stav | Kdo | Kde |
|---|---|---|
| Objednáno | web nebo recepce | rezervace (záložka **Objednat**, tabule, web) |
| Čeká | recepce | **Přijmout** v záložce Dnes, nebo **+ Bez objednání** v záložce Dnes |
| V ordinaci | lékařka / sestra | **Zavolat** na obrazovce Ordinace nebo v Moji pacienti dnes, nebo otevření karty pacienta |
| K pokladně | lékařka | **Hotovo, k pokladně** v kartě pacienta |
| Zaplaceno | recepce | **Zaplatit** v záložce Dnes |

---

# Část A – recepce

## 1. Začátek dne

Po přihlášení do Odoo se recepci rovnou otevře **pokladna Recepce** (nic nehledáte). Kdyby ne,
otevřete aplikaci **Prodejní místa** → pokladna **Recepce** → **Otevřít pokladnu**
(nebo **Pokračovat v prodeji**).

1. **Přihlaste se PINem.** Na zamčené obrazovce klikněte na **Odblokovat pokladnu** (nebo
   **Otevřít pokladnu**), napište svůj PIN a stiskněte Enter. Vpravo nahoře v pokladně pak vidíte
   své jméno – každé přijetí a každá platba se zapíše na vás.

   ![Přihlášení PINem](img/recepce-pin.png)

2. **Počáteční stav hotovosti.** První, kdo pokladnu ten den otevře, dostane okno **Otevření
   hotovosti**: spočítejte hotovost v šuplíku, zapište ji (nebo potvrďte navrženou částku)
   a klikněte **Otevřít pokladnu**. Dokud pokladna otevřená není, **Zaplatit** nic neudělá
   a ukáže upozornění.

Pokladna se otevře na záložce **Dnes**. Nahoře je lišta:

| Tlačítko | Co dělá |
|---|---|
| **Dnes** | přehled dne: kdo přichází, kdo čeká, co se platí |
| **Kartotéka…** | okno s klienty a zvířaty – jen hledání, prohlížení, nový klient a úpravy |
| **Objednat** | objednání termínu |
| **Pokladna** | běžná obrazovka pokladny (prodej zboží, tlačítko **Klient** u účtu – ukazuje jméno zákazníka účtu, např. „Klient: Jana Nováková“; Akce, Nabídka/Objednávka …) |
| **Tabule** | denní tabule ordinací v okně nad pokladnou (kapitola 5) |
| zámek | zamkne pokladnu (kapitola 7) |
| ☰ | menu pokladny (uzávěrka, objednávky …) |

## 2. Záložka Dnes

![Záložka Dnes](img/recepce-dnes.png)

Tři sloupce:

- **Přicházejí** – dnešní potvrzené rezervace, které ještě nepřišly, podle času: čas, zvíře,
  majitel, úkon, lékařka.
- **Čekárna a ordinace** – přijatí klienti: ordinace, lékařka (u neobjednaných případně
  „kterákoli lékařka“), jak dlouho čekají, a štítek **Čeká** nebo **V ordinaci**.
- **K pokladně** – účty, které lékařka uzavřela a které čekají na zaplacení, s částkou.

Ve státní svátek je u nadpisu dne červený štítek, např. „Státní svátek: Den vzniku samostatného
československého státu“. Je to jen připomínka, nic se neblokuje.
  Pod nimi je **Dnes zaplaceno** (počet).

Přehled se obnovuje sám: když lékařka zavolá pacienta nebo uzavře účet, změna je v pokladně
během pár vteřin (pro jistotu se navíc obnoví každých 30 s). Ručně ho obnoví šipka vpravo nahoře.

Šipky **‹ ›** vedle data ukážou předchozí / další den (např. kdo je objednaný zítra),
**Dnes** vás vrátí. U jiného dne než dneška tlačítka Přijmout a + Bez objednání nejsou – přijmout
jde jen dnešní návštěvu.

### Přijmout objednaného klienta

1. Klient přijde – najděte ho ve sloupci **Přicházejí**.
2. Klikněte **Přijmout**. Otevře se malé okno s polem **Interní poznámka pro ordinaci
   (nepovinné)** – např. „Klient spěchá“, „Kouše, opatrně“, „Přinesl vzorek moči“. Poznámku
   můžete nechat prázdnou.
3. Klikněte **Přijmout do čekárny** (nebo stiskněte Enter; nový řádek v poznámce je
   Shift+Enter). **Zrušit** okno zavře a klient zůstane v Přicházejí.
4. Klient se přesune do **Čekárny a ordinace** se štítkem **Čeká**. Lékařka ho hned vidí
   ve svém seznamu **Čekají**.

**Poznámka recepce** je interní: ukáže se žlutě v ordinaci – v Moji pacienti dnes, na obrazovce
Ordinace a nahoře v kartě pacienta u té návštěvy. Klient ji nikde nevidí, na účtence ani faktuře
není. U pacienta v **Čekárně a ordinaci** je vidět i v pokladně a tlačítkem **Poznámka**
(tužka) ji doplníte, opravíte nebo smažete (prázdné pole = smazat), dokud lékařka návštěvu
neuzavře. Stejné okno má **Přijmout** v tabuli (kapitola 5).

![Čekárna po přijetí](img/recepce-cekarna.png)

Když lékařka kartu otevřela dřív, než jste klienta přijali, Přijmout nic nezdvojí – použije se
záznam, který už existuje.

### Přijmout bez objednání (+ Bez objednání)

Klient přišel bez rezervace:

1. Klikněte **+ Bez objednání** u nadpisu **Přicházejí**. Otevře se Kartotéka s nadpisem
   „Přijmout bez objednání“.
2. Najděte klienta (nebo ho založte tlačítkem **+ Nový klient**, kapitola 3) a klikněte na zvíře.
3. Vyberte **Lékařku**: konkrétní, nebo **kterákoli** – takového pacienta vidí v Čekají všechny
   lékařky s poznámkou „kterákoli lékařka“ a ujme se ho ta, která ho zavolá.
4. Volitelně vyberte **Ordinaci**. Bez ní je pacient na obrazovce Ordinace v části Nepřiřazení
   a ordinace si ho vezme ([Obrazovka Ordinace](ordinace.md)).
   Volitelně napište **Interní poznámku pro ordinaci** (stejná poznámka recepce jako u Přijmout).
5. Klikněte **Přijmout**. Okno se zavře a zvíře je v **Čekárně a ordinaci** se štítkem **Čeká**
   (u pacienta s ordinací je vidět i ordinace).

   ![Přijmout bez objednání](img/recepce-bez-objednani.png)

### Klient k rezervaci: Klient… a Spárovat

Každá rezervace v **Přicházejí** má tlačítko **Klient…** – když přijde jiné zvíře nebo jiný
majitel, než je v rezervaci, opravíte to tady. Rezervace z webu, kterou ještě nikdo nepřiřadil
ke klientovi v kartotéce, má poznámku **nespárováno** a místo Klient… a Přijmout tlačítko
**Spárovat**.

1. Klikněte **Klient…** (nebo **Spárovat**). Otevře se Kartotéka s nadpisem „Klient k rezervaci
   21:00 Kontrola“ (čas a úkon rezervace). U rezervace s klientem je rovnou otevřená jeho karta
   s vybraným zvířetem z rezervace:

   ![Klient… u rezervace](img/recepce-klient-rezervace.png)

   U webové rezervace bez klienta Kartotéka hledá podle jména z webu:

   ![Spárovat webovou rezervaci](img/recepce-sparovat.png)

2. Vyberte správné zvíře – jiné zvíře majitele kliknutím, jiného klienta hledáním. Když klient
   v kartotéce není, založte ho tlačítkem **+ Nový klient** (kapitola 3).
3. Klikněte **Přiřadit k rezervaci** (jediné hlavní tlačítko okna). Zobrazí se „Klient je přiřazený k rezervaci …“, okno se
   zavře a Dnes ukáže rezervaci s novým klientem a zvířetem (webová už má **Přijmout**).

Rezervaci, ke které už je návštěva (klient je přijatý nebo lékařka otevřela kartu), nejde přiřadit
jinému zvířeti – „Rezervace už má návštěvu jiného zvířete.“

### Zaplatit

1. Ve sloupci **K pokladně** klikněte u klienta na **Zaplatit**.

   ![K pokladně](img/recepce-k-pokladne.png)

   Když ordinace k účtu napsala **poznámku pro recepci** (např. „Platí převodem“, „Doplatí
   zítra“, „Objednat na kontrolu za 14 dní“), je žlutě pod klientem už v K pokladně a po
   kliknutí na Zaplatit se nejdřív ukáže v okně **Poznámka z ordinace**. Přečtěte ji
   a klikněte **Pokračovat k platbě** (**Zpět** platbu neotevře). Poznámka je interní – na účtence
   ani faktuře není. Je vidět i v Kartotéce u otevřených účtů klienta.

2. Pokladna sama načte účet i se zákazníkem (majitelem) a otevře platbu – nic nehledáte
   v Akce → Nabídka/Objednávka.
3. Zvolte způsob platby (**Kartou**, **Hotově**, **Převodem**), případně zapněte **Faktura**,
   a klikněte **Potvrdit**. U karty opište částku do terminálu banky.

   ![Platba kartou](img/recepce-platba.png)

4. Zobrazí se **Platba byla úspěšná** a účtenka. Tlačítkem **Dnes** se vrátíte na přehled;
   klient z K pokladně zmizí a **Dnes zaplaceno** se zvýší.

   ![Účtenka](img/recepce-uctenka.png)

Dobré vědět:

- **Starší účty.** V K pokladně jsou všechny nezaplacené účty, i ze dřívějších dnů – ty mají
  u částky „z 21. 10.“. Klient, který zaplatí až zítra, tedy z pokladny nezmizí.
- **Záloha** (**Částečně zaplaceno**) zůstává v K pokladně se zbývající částkou; Zaplatit
  doplatí zbytek.
- **Každý účet má vlastní účtenku.** Když máte v pokladně rozdělaný jiný nákup, Zaplatit založí
  novou objednávku; dva klienti se na jedné účtence nikdy nesmíchají. Účet, který už je
  v některé otevřené objednávce, se otevře v ní.
- Fakturu, zálohu, vratku a opravu zaplaceného účtu popisuje návod
  [Pokladna a sklad](../../elite_vet_sale/doc/pokladna-a-sklad.md) (kapitoly 3–6).

## 3. Kartotéka

Kartotéka je okno nad pokladnou (rozdělaný nákup v pokladně zůstává, jak byl). Vždy dělá jen
**jednu věc** – podle toho, odkud ho otevřete. Nahoře v okně je napsané, k čemu klienta
vybíráte, a dole je nejvýš **jedno hlavní tlačítko** (a Zavřít):

| Odkud otevřete | Nadpis okna | Hlavní tlačítko – co udělá |
|---|---|---|
| lišta **Kartotéka…** | Kartotéka | žádné – jen hledání, prohlížení, nový klient a úpravy |
| **Objednat**, krok Klient a zvíře › **+ Nový klient** / **Upravit** / majitel bez zvířete | Vybrat klienta a zvíře pro objednání | **Vybrat** – klient a zvíře se zapíšou do formuláře Objednat (kapitola 4) |
| **Pokladna**, tlačítko **Klient** u účtu | Klient k účtu v pokladně | **Vybrat k účtu** – klient bude zákazníkem rozdělaného účtu |
| **Dnes**, **Klient…** / **Spárovat** u rezervace; detail na **tabuli** › **Klient…** | Klient k rezervaci 21:00 Kontrola | **Přiřadit k rezervaci** – klient a zvíře se zapíšou k té rezervaci (kapitola 2) |
| **Dnes**, **+ Bez objednání** | Přijmout bez objednání | **Přijmout** – s výběrem lékařky; zvíře jde do čekárny (kapitola 2) |

Tlačítka, která potřebují zvíře (Vybrat, Přiřadit k rezervaci, Přijmout), jsou šedá, dokud
zvíře nevyberete („Vyberte zvíře.“, u klienta bez zvířat „Přidejte zvíře (+ Nové zvíře).“);
s uhynulým zvířetem nejdou.

### Hledání

Napište jméno majitele nebo zvířete, telefon nebo číslo čipu a stiskněte **Enter** (nebo
**Hledat**). Stačí 2 znaky. Ve výsledcích jsou zvířata (ikona tlapky) a majitelé bez zvířat
(ikona osoby). Kliknutím otevřete kartu majitele.

### Karta majitele

![Kartotéka – karta majitele](img/recepce-kartoteka.png)

- Vlevo **klient**: jméno, telefon a e-mail, adresa, počet **otevřených účtů**, tlačítko
  **Upravit**.
- Vpravo **zvířata**: druh, plemeno, pohlaví, narození, čip, upozornění (oranžový štítek)
  a příští očkování. Uhynulá zvířata jsou na konci, vybledlá; s nimi nejde nic dělat.
- Kliknutím vyberete zvíře (rámeček) – pod ním je **Upravit <jméno>** (při Přijmout bez
  objednání i výběr **Lékařka**).
- **‹ Zpět na výsledky** vás vrátí k hledání.

### Nový klient, nové zvíře, úpravy

1. **+ Nový klient**: vyplňte jméno (povinné), telefon, mobil, e-mail, adresu. Rovnou můžete
   zadat i **první zvíře** (jméno a druh) – další přidáte potom.

   ![Nový klient](img/recepce-novy-klient.png)

2. **Uložit.** Otevře se karta nového klienta.
3. **+ Nové zvíře**: jméno a druh jsou povinné; pohlaví, plemeno, narození, čip a poznámka ne.
4. **Upravit** (u klienta) a **Upravit <jméno>** (u zvířete) otevřou stejný formulář s vyplněnými
   údaji. **Uložit** změny zapíše, **Zrušit** je zahodí.

Stejný telefon nebo e-mail jako jiný klient nevadí – nic se neslučuje. Kontakty zaměstnanců
a firem v kartotéce upravit nejde („Tento kontakt není klient kliniky.“).

### Vybrat k účtu (Pokladna › Klient)

Prodej bez návštěvy (např. krmivo) na jméno klienta: na záložce **Pokladna** naúčtujte zboží
a klikněte **Klient** u účtu. Kartotéka ukáže dosavadního zákazníka účtu (když nějaký je);
najděte klienta a klikněte **Vybrat k účtu**. Položky naúčtované bez zákazníka zůstanou a dostanou
tohoto klienta. Účet s položkami **jiného** klienta se nepřepíše – vznikne nový účet (dva klienti
se nikdy nesmíchají na jedné účtence).

Na tlačítku je jméno zákazníka účtu („Klient: Jana Nováková“), bez zákazníka jen „Klient“.
Standardní tlačítko zákazníka pokladny Recepce nemá; i **Zákazník** na obrazovce platby (a dotaz
na zákazníka u faktury) otevře tuto Kartotéku se stejnými pravidly.

![Klient k účtu v pokladně](img/recepce-klient-k-uctu.png)

## 4. Objednat

Objednání jde po očíslovaných krocích shora dolů. Hotový krok má číslo vybarvené, další krok
se ukáže, až je předchozí vyplněný.

1. **Klient a zvíře** – pište rovnou do pole hledání v kroku (jméno, telefon, čip nebo jméno
   zvířete, aspoň 2 znaky). Výsledky se ukážou pod polem samy, za každé zvíře jeden řádek, třeba
   „Rex (pes) · Jana Nováková · 777 123 456“ (uhynulá zvířata ani personál se nenabízejí).
   Kliknutím na řádek (nebo Enter na prvním) je zvíře vybrané a v kroku zůstane „Rex · Jana
   Nováková“. **Změnit** otevře hledání znovu, **Upravit** otevře Kartotéku na tomto klientovi
   (úprava kontaktu nebo zvířete, pak **Vybrat**).
   Nový klient: **+ Nový klient** vedle pole otevře Kartotéku rovnou na formuláři nového klienta
   (i s prvním zvířetem); po uložení klikněte **Vybrat**. Majitel bez zvířete má v hledání řádek
   „bez zvířete – přidat zvíře…“ – otevře formulář nového zvířete.
2. **Úkon** – nejčastější úkony posledních 30 dní jsou velká tlačítka (u každého délka), stačí
   kliknout. Ostatní najdete pod **Jiný úkon…** (seznam s hledáním); vybraný úkon se pak ukáže
   zvýrazněný vedle častých.
3. **Den** – nad řadou dnů je zelené tlačítko s **nejbližším volným časem**, třeba „Nejdřív: dnes
   14:30 · Ordinace 2 · MVDr. Malá“ – jedním kliknutím vyplní den, ordinaci i čas a stačí
   objednat. Řada sedmi dnů ukazuje u každého počet volných časů („10 volných“); **„nic
   volného“** je otevřený, ale plně obsazený den, šedé **„zavřeno“** den, kdy úkon nejde vůbec
   (ordinace zavřená, celodenní blokace, nebo nikdo ze služby, když je lékařka potřeba) – na ten
   kliknout nejde. Když vybraný den po výběru úkonu volno nemá, přeskočí výběr sám na první den
   řady s volnem. Státní svátek má v řadě dnů červený rámeček a nápis **svátek** (najetím myší
   jeho název); vybrat ho jde normálně. Šipky **‹ ›** posunou o týden (nejdřív na dnešek), kalendář pod nimi vybere jiné
   datum. Když vybraný den nemá volno, objeví se tlačítko s **nejbližším dalším volným dnem**.
   Chce-li klient konkrétní lékařku, klikněte vpravo na **jen lékařka…** a vyberte ji; dny,
   ordinace, časy i nejbližší volný čas se pak počítají jen pro ni. Křížkem u jejího jména filtr
   zrušíte.
4. **Ordinace** – jen když má úkon ten den volno ve více ordinacích. U každé je lékařka (pokud ji
   má celý den jedna) a počet volných časů. Když je volno jen v jedné, vybere se sama a tento krok
   se neukáže. Vybraná ordinace zůstane i po změně dne.
5. **Čas** – volné časy vybrané ordinace, rozdělené na dopoledne a odpoledne. Počítají se stejně
   jako na tabuli a na webu.

Dole je **souhrn** celé objednávky jednou větou, třeba „Rex · Kontrola · čt 22. 10. 2026 9:30 ·
Ordinace 2 · MVDr. Malá“ (ve státní svátek s červeným upozorněním „Státní svátek: …“ – objednat
jde normálně), pod ním nepovinná **poznámka** a jediné tlačítko **Objednat**. Zkontrolujte
souhrn a klikněte. Objeví se potvrzení „Objednáno: čt 22. 10. 2026 9:30 · Rex“; rezervace je
potvrzená a je na tabuli i v Přicházejí toho dne.

Potom se **formulář vyprázdní** pro dalšího klienta (klient a zvíře, úkon, lékařka, ordinace,
čas, poznámka); zůstane jen den. Zelené potvrzení zmizí, jakmile začnete další objednání.

![Objednat – klient, časté úkony, nejbližší volný čas a řada dnů se „zavřeno“](img/recepce-objednat.png)

**E-mail klientovi:** když má majitel v kartotéce e-mail, dostane potvrzení rezervace
automaticky (stejné jako z průvodce na tabuli). Bez e-mailu se nic neposílá – termín mu řekněte.

Když mezitím termín obsadil někdo jiný (web, kolegyně), objeví se „Termín … už mezitím někdo
obsadil – vyberte jiný.“ a časy se načtou znovu. Uhynulé zvíře objednat nejde.

**Tabule** vedle Objednat otevře tabuli vybraného dne v okně nad pokladnou (kapitola 5); vybraný
klient zůstane.

V režimu **Přesunout rezervaci** (z tabule) vás zpět k běžnému objednání vrátí **Nepřesouvat**
nebo znovu kliknutí na **Objednat** v liště. Úkon a čas přesouvané rezervace se přitom zruší –
formulář začíná od výběru úkonu.
Při přesouvání chybí krok Klient a zvíře; souhrn ukazuje přesouvané zvíře a tlačítko je **Přesunout**.

## 5. Tabule

Tlačítko **Tabule** v liště (nebo **Tabule** vedle Objednat na záložce Objednat) otevře velké okno
s tabulí dne přímo nad pokladnou – pokladna ani rozepsaný účet pod ním se nemění a nic se
nepřepíná do jiné stránky.

![Tabule v pokladně](img/tabule-v-pokladne.png)

- **Sloupce** jsou ordinace (u každé lékařky ve službě s časem), vlevo časová osa, červená čára
  je teď. Šrafované je mimo ordinační dobu, šedé šrafované pruhy jsou blokace („jen web“ jsou
  světlé – recepce tam objednat smí).
- Svislý barevný pruh u levého okraje sloupce je **služba lékařky** (iniciály a čas).
- **Rezervace** mají barvu úkonu, proužek vlevo v barvě lékařky, iniciály lékařky, čas,
  zvíře (majitel), zkratku úkonu a štítek **k pokladně** / **zaplaceno**. Proběhlé a nedorazivší
  jsou bledé.
- Ve státní svátek je u data červený štítek „Státní svátek: …“ (když web ve svátky neobjednává,
  s „· web neobjednává“).
- **‹ Dnes ›** a pole s datem přepínají den; tabule se posune na „teď“ (dnes), u jiného dne na
  začátek. Při hodně ordinacích se tabule posouvá i do stran.
- Tabule se sama obnovuje (změna z webu, od kolegyně nebo z backendu se ukáže hned, záložně
  každých 30 s).
- **Zavřít** (nebo křížek) vás vrátí tam, kde jste byli.

### Klik na rezervaci

Otevře se okno s detailem: klient (a telefon), zvíře, úkon, lékařka, čas a ordinace, stav.

![Detail rezervace](img/tabule-detail.png)

- **Přijmout** – jen u dnešní rezervace, která ještě nemá návštěvu; zvíře je pak v čekárně
  (stejně jako Přijmout na záložce Dnes, i s oknem pro interní poznámku pro ordinaci). Webová rezervace bez spárovaného klienta se přijme až
  po **Klient…**.
- **Klient…** – Kartotéka pro tuto rezervaci (stejné jako Klient… na záložce Dnes, kapitola 2):
  vyberte klienta a zvíře a **Přiřadit k rezervaci**. Tabule zůstane otevřená pod ním.
  U proběhlé a nedorazivší rezervace Klient… není.
- **Přesunout** – okno se zavře a otevře se záložka Objednat v režimu **Přesunout rezervaci**:
  úkon a lékařka jsou předvyplněné, vyberte den a volný čas a klikněte **Přesunout**.
  **Nepřesouvat** režim ukončí.
- **Zrušit rezervaci** – zeptá se ještě v okně („Opravdu zrušit? Klientovi odejde e-mail
  o zrušení.“, nebo bez e-mailu „Opravdu zrušit tuto rezervaci?“) a po **Ano, zrušit rezervaci**
  rezervaci zruší. E-mail o zrušení odejde stejně jako při zrušení v backendu – jen když má
  rezervace e-mail.

Rezervace, která už má návštěvu (klient je přijatý), se přesunout ani zrušit nedá – Přesunout
a Zrušit rezervaci se u ní neukážou. U společného zákroku dvou lékařek se přesouvá jen hlavní
rezervace – kopie ve druhé ordinaci se posune s ní (u kopie Přesunout ani přetažení nejsou).

### Přetažení rezervace

Potvrzenou rezervaci můžete myší přetáhnout na jiný čas nebo do jiné ordinace (na dotykové
obrazovce použijte **Přesunout** v detailu). Po puštění se pokladna zeptá „Přesunout … z …
na …?“ (i s poznámkou, že klient dostane e-mail o změně termínu, když ho má). Teprve
**Přesunout** rezervaci přesune; **Zrušit** nechá vše, jak bylo. Platí stejná pravidla jako na backendové tabuli:
v ordinaci musí sloužit lékařka, která úkon dělá (jinak se lékařka vymění za tu, která tam
slouží), a čas musí být volný. Když to nejde, objeví se česká hláška (např. „Termín … je
obsazený“) a rezervace zůstane, kde byla. Při změně času dostane klient e-mail o přesunu,
pokud ho má.

### Klik do volného místa

Okno se zavře a otevře se **Objednat** s předvyplněným dnem a nahoře s pruhem „Z tabule:
ordinace, den, čas“. Vyberte úkon: když je ten čas pro úkon volný, je hned vybraný („Čas je
vybraný.“), jinak vyberte z volných časů dne. Vybraný klient (když jste přišli z Objednat)
zůstane.

Žádosti z webu, nové blokace a plánování dopředu zůstávají na backendové tabuli (vedení,
[návod Rezervace](../../elite_vet_reservation/doc/recepce.md)).

## 6. Konec dne – uzávěrka

1. Zkontrolujte, že v **K pokladně** nezůstal nikdo, kdo už odešel a měl platit (nezaplacené účty
   tam zůstanou i zítra).
2. Udělejte uzávěrku podle návodu
   [Pokladna a sklad – 7. Uzávěrka](../../elite_vet_sale/doc/pokladna-a-sklad.md#7-uzávěrka-konec-dne):
   ☰ → **Zavřít pokladnu**, spočítat hotovost, **Zavřít relaci**.

**Zavřít pokladnu** v menu ☰ vidí jen zaměstnanec s **pokročilým oprávněním** (nastavuje vedení,
kapitola 11) nebo zaměstnanec propojený s uživatelem Odoo, pod kterým je pokladna otevřená.
Když ho v menu nevidíte, přihlaste se PINem zaměstnance, který uzávěrku dělá.

## 7. Přepnutí obsluhy a zamčení

- **Zamčení:** ikona zámku vpravo nahoře (vedle jména). Pokladna se zamkne; nikdo nemůže nic
  udělat bez PINu. Zamykejte, když od pokladny odcházíte.
- **Přepnutí obsluhy:** zamkněte a druhá kolegyně se přihlásí svým PINem (**Odblokovat
  pokladnu**). Pokladna se vrátí na Dnes (nebo na Pokladnu, když jste byli tam). Rozdělané
  objednávky zůstávají.
- Kdo klienta přijal, je zapsané u návštěvy; kdo platbu přijal, je na účtence („Obsluha …“).

---

# Část B – lékařky a sestry

## 8. Moji pacienti dnes

Po přihlášení se lékařce a sestře otevře **Karta pacienta** (aplikace **Ordinace**). Pod polem
pro hledání je **Moji pacienti dnes** – lékařka vidí své pacienty (objednané i neobjednané),
sestra a účet bez spárované lékařky vidí všechny.

![Moji pacienti dnes](img/ordinace-dnes.png)

| Skupina | Kdo v ní je |
|---|---|
| **Čekají** | recepce je přijala, podle příchodu: „příchod 18:09 · čeká 6 min“, tlačítko **Zavolat**. Neobjednaní mají „bez objednání“; neobjednaní bez lékařky mají „**kterákoli lékařka**“ a vidí je všechny lékařky. |
| **V ordinaci** | zavolaní, „od 18:15“ |
| **Objednaní – ještě nepřišli** | dnešní rezervace, které recepce ještě nepřijala |
| **Hotovo dnes** | uzavřené návštěvy (Hotovo, k pokladně) |

Seznam se obnovuje sám, jakmile recepce někoho přijme (záložně každých 30 s).

Když recepce při příjmu napsala **poznámku recepce**, je u pacienta žlutě (s ikonou lístečku)
a v kartě pacienta žlutý pruh pod záhlavím „Poznámka recepce: …“. Je interní, klient ji nevidí.

## 9. Zavolat a ošetření

1. U pacienta v **Čekají** klikněte **Zavolat**. Pacient přejde do **V ordinaci**
   a otevře se jeho karta. Pacienta „kterákoli lékařka“ si tím vezmete vy – od té chvíle je
   jen ve vašem seznamu.
2. Stejně funguje, když kartu pacienta, který čeká, otevřete jinak (ze seznamu, z tabule,
   z hledání) – pacient se sám přesune do V ordinaci.
3. V recepci se u pacienta hned ukáže **V ordinaci**.

![Po zavolání](img/ordinace-v-ordinaci.png)

4. Zapište návštěvu a účet v kartě pacienta (**+ Úkon**, **+ Lék ze skladu**, balíček).
5. Pro recepci můžete nad tlačítkem **Hotovo, k pokladně** napsat **Poznámku pro recepci**
   (interní, klient ji neuvidí) – recepce ji uvidí u účtu v K pokladně a před platbou. Ukládá
   se sama; opravit nebo smazat ji jde i po uzavření záznamu (dokud není zrušený).
6. Na konci klikněte **Hotovo, k pokladně** a potvrďte. Pacient přejde do **Hotovo dnes**
   a recepce ho hned vidí ve sloupci **K pokladně**. Podrobně (štítky, znovuotevření,
   rozpracovaný účet v pokladně) to popisuje
   [Pokladna a sklad – 1. Jak se účet dostane k pokladně](../../elite_vet_sale/doc/pokladna-a-sklad.md#1-jak-se-účet-dostane-k-pokladně).

---

# Část C – vedení

## 10. Role a výchozí obrazovky

Role se přidělují v **Nastavení → Uživatelé** (skupiny Elite Vet: Recepce < Sestra < Lékařka <
Správce = Vedení; vyšší role má vše, co nižší – kromě pokladny a skladu, viz níže).

| Role | Po přihlášení | Menu |
|---|---|---|
| Recepce | pokladna Recepce | Prodejní místa (pokladna), Rezervace, Diskuze, ze Skladu jen Přehled skladu a Příjem zboží |
| Sestra, Lékařka | Karta pacienta (Moji pacienti dnes) | Ordinace, Rezervace, Diskuze – bez pokladny a skladu |
| Vedení | Přehled tržeb a výdajů | vše |

- **Pokladna a sklad (recepce)** je samostatné pole ve formuláři uživatele (oddíl „Elite Vet –
  pokladna“), mimo výběr role. Dává pokladnu, nabídky, Přehled skladu a Příjem zboží. Když
  uživateli nastavíte roli **Recepce**, dostane ho sám; když roli změníte na **Sestra** nebo
  **Lékařka**, odebere se (i s právy pokladny a skladu). Má-li zboží přijímat i sestra, zapněte
  jí ho ručně **po** nastavení role – ruční změna zůstane. Vedení ho má vždy.
- Lékařka a sestra dál uzavírají účty (**Hotovo, k pokladně**) a vidí stav platby v kartě
  pacienta i na tabuli; do pokladny ani do skladu se nedostanou.

- Výchozí obrazovka se nastaví sama, když uživateli přidělíte roli (nebo ji změníte). Vlastní
  výchozí obrazovku, kterou uživatel má nastavenou ručně, to nepřepíše.
- **Nastavit výchozí obrazovky:** Nastavení → Uživatelé → v seznamu zaškrtněte libovolného
  uživatele → **Akce → Nastavit výchozí obrazovky**. Nastaví výchozí obrazovky **všem** interním
  uživatelům podle role, nejen zaškrtnutým (vlastní zůstanou). Použijte, když jste měnili členy přímo ve formuláři skupiny.
- **Skrytá menu:** Prodej, Fakturace, Zaměstnanci, WinVet data, Rozpis služeb, Web a Přehledy
  vidí jen vedení, Aplikace jen správce systému; recepce nevidí Ordinaci; sestra a lékařka nevidí
  Prodejní místa ani Sklad. Lékařky vidí služby na tabuli.
- **Účetní** potřebuje roli **Vedení** – Fakturace je jen pro vedení.
- Každý, kdo ráno **otevírá pokladnu**, musí mít u svého uživatele vyplněný **e-mail**. Bez něj
  Odoo otevření odmítne („nakonfigurujte e-mailovou adresu odesílatele“).

## 11. Zaměstnanci s PINem

Kdo se do pokladny přihlašuje PINem, musí být **zaměstnanec** v aplikaci **Zaměstnanci**.

1. **Zaměstnanci → Nové**: jméno (to se ukazuje v pokladně a na účtence).
2. Záložka **Nastavení** → **PIN kód**: čtyři číslice, které si zaměstnanec pamatuje. Pole
   **Příslušný uživatel** propojí zaměstnance s jeho přihlášením do Odoo (nepovinné).
3. **Uložit.**

   ![Zaměstnanec s PINem](img/vedeni-zamestnanec-pin.png)

4. Povolte ho na pokladně: **Prodejní místa → Konfigurace → Nastavení**, nahoře vyberte
   pokladnu **Recepce**, část **Rozhraní PoS** → **Přihlásit se jako zaměstnanec**:
   - **Základní oprávnění** – recepční (přijímají, objednávají, platí),
   - **Pokročilé oprávnění** – kdo smí dělat uzávěrku, opravovat platby, vkládat a vybírat
     hotovost (vedení, případně vedoucí recepce).

   Když jsou obě pole prázdná, přihlásit se může každý zaměstnanec firmy.
5. **Uložit** (nahoře vlevo). Nový zaměstnanec se objeví v pokladně po jejím znovunačtení.

   ![Zaměstnanci na pokladně](img/vedeni-pokladna-zamestnanci.png)

**Před aktualizací modulů zavřete pokladnu** (uzávěrka). Za otevřené pokladny nejde přihlášení
PINem zapnout ani změnit a aktualizace to jen zapíše do logu.
