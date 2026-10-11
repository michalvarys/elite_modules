# Rezervace – návod pro recepci

**K čemu je tento návod.** Popisuje denní práci s rezervacemi v Odoo: tabuli, žádosti z webu,
zakládání a přesouvání rezervací, blokace a e-maily klientům. Je pro recepci, nepotřebujete
k němu žádné technické znalosti. Jak se počítají volné termíny, vysvětluje
[Jak to funguje](jak-to-funguje.md).

Vše najdete v aplikaci **Rezervace**. Nahoře je nabídka: **Tabule**, **Nová rezervace**,
**Čekající z webu**, **Rezervace**, **Rozpis lékařů**, **Klienti**, **Mazlíčci**
(a **Konfigurace**, kterou vidí jen správce).

---

## 1. Tabule

![Tabule](img/tabule.png)

Tabule ukazuje **jeden den**. Každá ordinace má svůj sloupec, vlevo je časová osa.

### Pohyb po dnech

- **‹** a **›** – předchozí / další den.
- Políčko s datem – skok na libovolný den.
- **Dnes** – návrat na dnešek.
- Vedle nadpisu dne je řada **dnů v týdnu** (po–ne). Kliknutím přejdete na daný den.
  Vybraný den je zelený, dnešek má červený rámeček.

Tabule nemá týdenní mřížku. Když chcete vidět celý týden najednou, otevřete
**Rezervace** a přepněte vpravo nahoře na zobrazení kalendáře (barvy podle ordinace).

### Co na tabuli vidíte

| Co | Význam |
|---|---|
| Světle šedé šrafování | Ordinace je zavřená (mimo ordinační dobu nebo výjimka). |
| Tmavě šedý šrafovaný pruh | Blokace (např. „Oběd“). Blokace pro všechny ordinace se táhne přes všechny sloupce. |
| Barevná karta | Rezervace. Barva patří úkonu (např. vakcinace zelená, problém modrý). |
| Písmeno vlevo na kartě | Zkratka úkonu (V = vakcinace, P = zdravotní problém, S = stomatologie…). |
| Čas · jméno | Např. „9:00–9:15 · Rex (Jana Nováková)“ = mazlíček (majitel). |
| Druhý řádek | Název úkonu (jen u delších karet). |
| 🌐 | Rezervace přišla z webu. |
| Zkratka vpravo (např. **GC**) | Iniciály lékařky. Po najetí myší uvidíte celé jméno. |
| Bledší karta | Proběhla nebo Nedorazil. |
| Štítky v hlavičce sloupce | Kdo v ordinaci slouží a od kdy do kdy, např. „MVDr. Georgiana Chihaia 08:15–14:00“. |
| „interní“ u názvu | Ordinace, kam se klienti z webu objednat nemohou (např. Sál). |
| Červená čára | Aktuální čas (jen u dneška). Čas je i na ose. |

Zrušené rezervace se na tabuli neukazují.

Najedete-li myší na kartu, zobrazí se podrobnosti: úkon, lékařka, telefon, e-mail
a popis problému. Kliknutím na kartu otevřete celou rezervaci.

### Živá aktualizace

Tabuli není třeba obnovovat. Když kdokoli (kolegyně na druhém počítači, klient z webu)
něco změní, tabule se sama překreslí. Při nové žádosti z webu vyskočí vpravo nahoře
upozornění „Nová žádost z webu: …“, které zůstane, dokud ho nezavřete. Kdyby spojení vypadlo, tabule se pro jistotu
obnoví sama každou minutu.

---

## 2. Čekající žádosti z webu

Žádost, kterou klient pošle z webu, ještě **není potvrzená** a **neblokuje termín**.
Čeká, až ji recepce potvrdí. Najdete ji:

- v levém panelu tabule **Čekající z webu (počet)**,
- v nabídce **Čekající z webu** (seznam všech čekajících, i starších).

![Seznam čekajících z webu](img/cekajici-seznam.png)

Každá karta v panelu ukazuje požadovaný den a čas, délku, jméno, telefon a e-mail,
vybranou lékařku (pokud si ji klient zvolil) a popis problému.

### Potvrzení jedním klikem (doporučeno)

Pod kartou jsou zelená tlačítka **Potvrdit → Ordinace · lékařka**, např.
„Potvrdit → Ordinace 1 · MVDr. Daniela Píšková“. Systém je nabízí jen tam, kde je
požadovaný čas volný a kde slouží lékařka, která úkon dělá.

1. Vyberte vhodné tlačítko a klikněte.
2. Rezervace se zapíše do ordinace v požadovaném čase a klient dostane e-mail
   s potvrzením.

Když se objeví text **„Požadovaný čas už není volný – otevřete a přeplánujte.“**,
termín mezitím někdo obsadil. Text **„Požadovaný čas už uplynul – otevřete
a přeplánujte.“** znamená, že termín už začal. V obou případech postupujte podle
části „Úprava žádosti“.

### Přetažení do sloupce

Kartu můžete myší přetáhnout do sloupce ordinace na zvolený čas. Pustíte-li ji,
rezervace se rovnou **potvrdí** v tomto čase a ordinaci a klient dostane potvrzení.

- Pozor: kartu pouštíte na den, který je právě na tabuli. Chcete-li jiný den,
  nejdřív si ho na tabuli otevřete.
- Při přetažení se kontroluje, že čas je volný a že v té ordinaci v tu dobu slouží
  lékařka, která úkon dělá (nebo ta, kterou si vybral klient). Když ne, objeví se
  červená hláška „V 9:00 v Ordinace 1 neslouží lékařka, která dělá …“ a nic se neuloží.
  Slouží-li tam jediná taková lékařka, zapíše se k rezervaci sama.

### Úprava žádosti (tlačítko **Upravit**)

1. Klikněte na **Upravit**. Otevře se formulář rezervace.
2. Vyplňte **Ordinace**, případně změňte **Začátek** a **Lékařka**.
3. Klikněte na **Potvrdit** (nahoře vlevo).

Bez vyplněné ordinace potvrdit nejde. Při potvrzení se klient a mazlíček automaticky
dohledají v kartotéce (podle e-mailu, pak telefonu), nebo se založí noví.

Doporučení: když potvrzujete jiný čas, než si klient vybral, zavolejte mu.
E-mail mu přijde jako běžné potvrzení s novým časem.

### Odmítnutí (tlačítko **Odmítnout**)

1. Klikněte na **Odmítnout**.
2. Potvrďte dotaz „Odmítnout rezervaci …? Klientovi odejde e-mail o zrušení.“

Žádost se zruší a klient dostane e-mail, že termín je zrušený, s odkazem na nové objednání.

---

## 3. Nová rezervace (průvodce)

Rezervaci po telefonu nebo na místě zakládejte průvodcem. Otevřete ho:

- tlačítkem **Nová rezervace** na tabuli nebo v horní nabídce, nebo
- **kliknutím do prázdného místa ve sloupci** tabule – pak je předvyplněná ordinace a čas.

Průvodce má 4 kroky: **Co a kdy → Volný čas → Klient → Shrnutí**.
Mezi kroky se pohybujete tlačítky **Dále** a **Zpět**, **Zavřít** průvodce zruší.

### Krok 1 – Co a kdy

![Průvodce – krok 1](img/pruvodce-1.png)

1. **Úkon** – povinné.
2. **Lékařka** – nepovinné. Nabízí se jen lékařky, které daný úkon dělají.
   Necháte-li prázdné, systém vezme kteroukoli, která úkon dělá a v tu dobu slouží.
3. **Datum** – předvyplněný je den otevřený na tabuli.
4. Klikněte **Dále**.

Pokud jste průvodce otevřeli kliknutím do tabule a čas v ordinaci je volný,
krok 2 se přeskočí a jdete rovnou na klienta. Když volný není, krok 2 se otevře
se žlutým upozorněním, proč se předvyplněný čas nepoužil.

### Krok 2 – Volný čas

![Průvodce – krok 2](img/pruvodce-2.png)

Seznam volných časů v daný den: **Čas**, **Ordinace**, **Lékařka**.

1. U vhodného řádku klikněte **Vybrat**.
2. Jiný den: **‹ Předchozí den**, **Další den ›**, nebo **Další volný den**
   (najde nejbližší den, kdy je pro úkon volno).

Recepce může objednávat i na dnešek a daleko dopředu – omezení pro web
(„nejdříve za X hodin“, „nejdál X dní“) tady neplatí. Průvodce nabízí i ordinace,
které nejsou online (např. Sál), pokud mají ordinační dobu.

### Krok 3 – Klient

![Průvodce – krok 3](img/pruvodce-3.png)

1. Zvolte **Existující klient** nebo **Nový klient**.
2. Existující: do **Vyhledat klienta** napište jméno, telefon nebo e-mail
   (telefon stačí i část, mezery nevadí). Má-li klient jen jednoho mazlíčka,
   doplní se sám; jinak ho vyberte v poli **Mazlíček**.
3. Nový: vyplňte **Jméno a příjmení** a aspoň **Telefon** nebo **E-mail**.
   Pokud už klient se stejným e-mailem nebo telefonem v kartotéce je, použije se
   ten a nový se nezakládá.
4. Nový mazlíček: **Nový mazlíček – jméno** a **Druh**.
5. Volitelně **Popis problému** a **Interní poznámka** (klient ji nevidí).
6. **Poslat klientovi potvrzení e-mailem** – zaškrtne se samo, když je vyplněný e-mail.
   Odškrtněte, pokud klient e-mail nechce.
7. Klikněte **Dále**.

### Krok 4 – Shrnutí

Zkontrolujte úkon, termín, ordinaci, lékařku, klienta, kontakt, mazlíčka
a zda odejde e-mail. Klikněte **Uložit rezervaci**. Rezervace je hned potvrzená
a objeví se na tabuli.

Pokud mezitím termín někdo obsadil, uložení skončí hláškou o obsazeném termínu.
Vraťte se **Zpět** a vyberte jiný čas.

---

## 4. Přesun a změna délky

### Přesun přetažením

1. Chyťte kartu na tabuli a přetáhněte ji na jiný čas nebo do jiné ordinace.
2. Čas se zaokrouhlí na nejbližší krok (obvykle 15 minut).

Přetahovat jde jen v rámci zobrazeného dne. Na jiný den přesunete rezervaci
ve formuláři: klikněte na kartu a změňte **Začátek**.

Je-li cílový čas obsazený, objeví se červená hláška „Termín … v ordinaci … je obsazený: …“
a karta zůstane na původním místě. Stejně tak u rezervace, když v cílové ordinaci
a čase neslouží lékařka, která úkon dělá („V … v … neslouží lékařka, která dělá …“).
Neslouží-li tam dosavadní lékařka, zapíše se ta, která tam slouží (blokace jdou
přesunout kamkoli).

Klient s e-mailem dostane po přesunu potvrzené rezervace na jiný čas automaticky
e-mail **o změně termínu**. Při změně jen ordinace (stejný čas) e-mail nechodí.

### Prodloužení

Přetažením okraje karty délku změnit **nejde**. Postup:

1. Klikněte na kartu.
2. Změňte **Konec**.
3. Uložte.

Pozor: když ve formuláři změníte **Začátek** nebo **Úkon**, **Konec** se přepočítá
na běžnou délku úkonu. Prodloužení proto nastavujte až jako poslední.

---

## 5. Stav rezervace: proběhla, nedorazil, zrušení

![Formulář rezervace](img/rezervace-formular.png)

Ve formuláři rezervace jsou nahoře tlačítka:

| Tlačítko | Kdy je vidět | Co udělá |
|---|---|---|
| **Potvrdit** | Čekající z webu | Potvrdí (musí být vyplněná ordinace), pošle potvrzení. |
| **Poslat potvrzení** | Potvrzená s e-mailem | Pošle potvrzovací e-mail znovu. |
| **Proběhla** | Potvrzená | Označí návštěvu jako proběhlou (karta zbledne). |
| **Nedorazil** | Potvrzená | Označí, že klient nepřišel (karta zbledne). E-mail neodchází. |
| **Zrušit** | Čekající nebo potvrzená | Zruší rezervaci. Má-li klient e-mail, odejde mu e-mail o zrušení (budete na to upozorněni). Termín se uvolní. |
| **Spárovat klienta** | Rezervace bez klienta | Dohledá nebo založí klienta a mazlíčka z údajů z webu. |

Vpravo je stav: **Čekající z webu → Potvrzená → Proběhla**.

Proběhla / Nedorazil jsou nepovinné, slouží pro přehled. Pod formulářem je historie
změn a zpráv (kdo co kdy změnil).

---

## 6. Blokace (oběd, porada, zavřená ordinace)

Blokace zabere čas v ordinaci, takže se tam nedá objednat ani z webu, ani průvodcem.

### Nová blokace

1. Na tabuli klikněte **Nová blokace**.
2. Vyplňte **Důvod blokace** (např. „Oběd“).
3. **Ordinace** – vyberte jednu, nebo nechte prázdné = **všechny ordinace**.
4. **Začátek** a **Konec**.
5. Opakování: **Opakovat týdně do** – blokace se zkopíruje na stejný den v týdnu
   každý týden až do zadaného data (nejvýš na rok dopředu). Pole je jen při zakládání.
6. Uložte.

Blokaci nejde založit přes již potvrzenou rezervaci – nejdřív rezervaci přesuňte.

### Zrušení blokace

1. Klikněte na blokaci na tabuli.
2. Klikněte **Zrušit blokaci**.

Opakovaná blokace jsou samostatné kopie – každý týden se ruší zvlášť.
Všechny najdete v **Rezervace** s filtrem **Jen blokace**.

---

## 7. Klienti a mazlíčci

- **Klienti** – kartotéka klientů kliniky. Na kartě klienta je záložka **Mazlíčci**
  (jméno, druh, plemeno, poznámka) a pole **ID ve WinVetu** (zatím se nevyplňuje).
- **Mazlíčci** – seznam všech zvířat s majitelem.

Klient a mazlíček se zakládají sami: při potvrzení žádosti z webu a při uložení
průvodce. Klient se hledá nejdřív podle e-mailu, pak podle telefonu (posledních
9 číslic), takže stejný člověk se nezakládá dvakrát. Mazlíček se hledá podle jména
u téhož majitele.

Tip: Když klient napíše z webu jiný e-mail nebo telefon než minule, vznikne nový
klient. Pak je dobré karty ručně sloučit nebo opravit.

---

## 8. E-maily klientům

E-maily odcházejí automaticky v jazyce, ve kterém klient rezervoval na webu
(čeština, němčina, ruština, angličtina). Odcházejí přes frontu pošty, takže
mohou dorazit s několikaminutovým zpožděním.

| E-mail | Kdy odchází | Komu |
|---|---|---|
| Přijato z webu | Klient odešle žádost na webu | klientovi |
| Nová rezervace z webu | Klient odešle žádost na webu | klinice (adresa z nastavení), s odkazem na frontu Čekající z webu |
| Potvrzeno | **Potvrdit**, potvrzení z tabule, přetažení žádosti do sloupce, uložení průvodce (je-li zaškrtnuté), **Poslat potvrzení** | klientovi; obsahuje čas, ordinaci, lékařku, instrukce k úkonu a odkaz na zrušení |
| Změna termínu | Potvrzené rezervaci se změní začátek (samotná změna ordinace e-mail neposílá) | klientovi |
| Zrušeno | **Zrušit**, **Odmítnout**, zrušení klientem | klientovi; při zrušení klientem i klinice |
| Připomínka | X hodin před termínem, je-li zapnutá v nastavení | klientovi |

E-mail odchází jen tehdy, když má rezervace vyplněný e-mail. **Nedorazil** a
**Proběhla** e-mail neposílají. Změna lékařky ani délky e-mail neposílá.

Kdy použít **Poslat potvrzení**: klient tvrdí, že e-mail nedostal, nebo jste
v průvodci e-mail nejdřív neposlali a klient ho teď chce.

---

## 9. Zrušení klientem odkazem z e-mailu

V e-mailu s potvrzením, změnou termínu a připomínkou je odkaz na zrušení.

- Klient na něm potvrdí zrušení a rezervace se sama zruší (důvod zrušení: Klient).
- Klient dostane e-mail o zrušení, klinika kopii na adresu pro upozornění.
- Tabule se hned aktualizuje, termín je znovu volný.
- Zrušit odkazem jde jen do určité doby před termínem (nastavení „Klient může zrušit
  do“, obvykle 12 hodin). Později se klientovi ukáže, ať zavolá na recepci,
  a telefon recepce.

---

## 10. Časté situace

### Termín je obsazený

- Hláška „Termín … v ordinaci … je obsazený: …“ znamená, že v tom čase už je
  potvrzená rezervace nebo blokace. Nic se neuložilo.
- Vyberte jiný čas nebo jinou ordinaci. Průvodce sám nabízí jen volné časy.
- Čekající žádosti z webu termín neblokují – dvě žádosti na stejný čas se mohou sejít.
  Potvrdit jde jen jednu, u druhé zmizí návrhy a je třeba ji přeplánovat.

### Klient chce ke konkrétní lékařce

1. V průvodci vyberte v kroku 1 **Lékařka**.
2. Krok 2 ukáže jen časy, kdy tato lékařka slouží.
3. Pokud lékařka v seznamu chybí, daný úkon nedělá (nemá potřebnou specializaci).

Kdo kdy slouží, vidíte v hlavičce sloupců tabule nebo v **Rozpis lékařů**.
Na webu si klient lékařku vybírá v záložce **Podle lékaře**.

### Lékařka onemocněla

1. **Upravit rozpis** – v **Rozpis lékařů** smažte nebo přepište její služby
   (např. na zastupující lékařku). Úpravy rozpisu smí jen **Správce rezervací**;
   recepce rozpis jen vidí.
2. Web od té chvíle přestane nabízet časy, které vyžadují právě ji.
3. **Přeplánovat** – rezervace, které už na ni byly, zůstávají. Najdete je na tabuli
   podle jejích iniciál.
   - Přebírá-li je jiná lékařka: otevřete rezervaci a změňte **Lékařka** (klientovi
     e-mail neodchází – zavolejte mu, pokud na lékařce záleží).
   - Musí-li se termín posunout: přetáhněte kartu nebo změňte **Začátek**
     (klient dostane e-mail o změně termínu).
   - Nelze-li jinak: **Zrušit** (klient dostane e-mail o zrušení).

### Zavřeno celý den nebo část dne

- Jednorázově na pár hodin: **Nová blokace** (bez ordinace = celá klinika).
- Celý den (svátek, školení): správce zadá výjimku ordinační doby
  (viz [Nastavení](nastaveni.md)).

### Žádost z webu je v minulosti

Žádosti, jejichž termín už skončil, z panelu na tabuli zmizí, ale zůstávají
v nabídce **Čekající z webu**. Otevřete je a buď je přeplánujte a potvrďte,
nebo **Zrušit**.

### Záloha

Online platba zálohy zatím **není**. Je-li u úkonu záloha a zálohy jsou zapnuté,
rezervace má stav zálohy „Čeká na zálohu“ a platební údaje klientovi posílá recepce.
