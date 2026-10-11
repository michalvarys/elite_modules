# Rezervace – návod pro správce (nastavení a údržba)

**K čemu je tento návod.** Provede vás prvním nastavením rezervačního systému a jeho
běžnou údržbou: lékařky, úkony, ordinace a ordinační doba, rozpis lékařů, nastavení
webové rezervace a e-maily. Je pro vedoucí kliniky nebo toho, kdo má na starosti
nastavení. Denní práci recepce popisuje [Návod pro recepci](recepce.md), logiku výpočtu
termínů [Jak to funguje](jak-to-funguje.md).

Doporučené pořadí prvního nastavení: **práva → lékařky → specializace → ordinace
a ordinační doba → úkony → rozpis lékařů → nastavení rezervace → kontrolní seznam**.

---

## 1. Práva uživatelů

V **Nastavení → Uživatelé** u každého člověka v části **Rezervace** zvolte:

| Skupina | Co smí |
|---|---|
| **Recepce** | Tabule, nová rezervace, čekající z webu, rezervace, blokace, klienti a mazlíčci. Rozpis lékařů, ordinace a úkony jen vidí. |
| **Správce rezervací** | Vše jako Recepce a navíc **Konfigurace** (Ordinace, Výjimky ordinační doby, Úkony, Nastavení rezervace, Časté dotazy), úpravy **Rozpis lékařů** a akce **Zkopírovat na další týden**. |

Správce systému (administrátor) má Správce rezervací automaticky.

Lékařky a specializace se upravují v aplikacích **Rozpis služeb** a **Náš tým**.
K nim je potřeba mít práva i v těchto aplikacích.

---

## 2. Lékařky

![Seznam lékařek](img/lekarky.png)

Seznam lidí je v **Rozpis služeb → Lékařky**. Je v něm celý tým (i sestry a recepce),
protože se z něj skládá i veřejný rozpis služeb. Rezervace ale smí dostat jen lékařka.

U každé veterinární lékařky:

1. Otevřete ji v **Rozpis služeb → Lékařky**.
2. Zaškrtněte **Lékařka – přijímá rezervace** (v seznamu sloupec „Lékařka (rezervace)“).
3. Zkontrolujte **Karta v týmu** – propojení na její kartu na stránce Náš tým.
   Z karty se berou specializace.

Co příznak dělá:

- jen lékařky s příznakem jde zapsat do **Rozpis lékařů**,
- jen ty se nabízejí klientům na webu (záložka Podle lékaře) a v průvodci recepce.

Při instalaci se příznak nastavil všem s titulem „MVDr.“ a karta v týmu se propojila
podle shodného jména. Dál už je to na vás.

## 3. Specializace (kdo co umí)

Specializace se nastavují **na kartě lékařky v Náš tým → Členové týmu**, pole
**Specializace**. V Rozpisu služeb jsou jen vidět (nedají se tam měnit).

Specializace mají dva účely:

- na webu se podle nich řadí záložka **Podle specializace** (nabízí se jen obor,
  který má aspoň jedna lékařka),
- podle nich systém pozná, **kdo který úkon dělá** (viz Úkony).

Nová specializace se zakládá v **Náš tým → Specializace** (nebo Rozpis služeb → Specializace),
ikona v **Ikony**.

---

## 4. Ordinace a ordinační doba

![Seznam ordinací](img/ordinace.png)

**Rezervace → Konfigurace → Ordinace.** Každá ordinace je jeden sloupec na tabuli.

| Pole | Význam |
|---|---|
| **Název** | Jak se ordinace jmenuje na tabuli a v e-mailu klientovi. |
| **Barva** | Barva pruhu nad sloupcem tabule. |
| **Rezervovatelná online** | Odškrtněte u sálu a místností, kam se klienti z webu objednávat nemají. Na tabuli pak mají štítek „interní“. |
| **Pořadí** | Pořadí sloupců na tabuli (v seznamu lze i přetahovat). |
| **Poznámka** | Jen pro vás. |

V seznamu je sloupec **Ordinační doba** se souhrnem, např. „Po–Pá 8:15–19:30 · Ne 10:15–17:45“.

### Záložka Ordinační doba (týdenní šablona)

![Detail ordinace](img/ordinace-detail.png)

1. **Přidat položku** → **Den**, **Od**, **Do**.
2. Den bez řádku = zavřeno.
3. **Přestávka** = dva řádky na stejný den, např. 8:00–12:00 a 13:00–18:00.
   Řádky se nesmí překrývat.
4. **Platí od / Platí do** (skryté sloupce, zapnete ikonou vpravo v hlavičce tabulky) –
   pro letní a zimní režim. Připravte druhou sadu řádků s platností a nic nemusíte mazat.
   Prázdné = platí stále.

### Záložka Výjimky (jeden den jinak)

Výjimka má přednost před šablonou.

| Případ | Co vyplnit |
|---|---|
| Svátek, inventura, školení | **Datum**, zaškrtnout **Zavřeno celý den**, **Poznámka** |
| Kratší / jiné hodiny | **Datum**, **Od**, **Do** |
| Mimořádně otevřeno (např. sobota) | **Datum**, **Od**, **Do** – výjimka umí otevřít i den, který šablona nemá |

Na jeden den a ordinaci jde jen jedna výjimka. Výjimky všech ordinací najdete
přehledně v **Konfigurace → Výjimky ordinační doby**.

Výjimka platí pro jednu ordinaci. Zavíráte-li celou kliniku, zadejte ji u každé
ordinace (nebo použijte blokaci bez ordinace na tabuli).

---

## 5. Úkony

![Seznam úkonů](img/ukony.png)

**Rezervace → Konfigurace → Úkony.** Úkon je důvod návštěvy, který si klient vybírá.
Seznam lze upravovat přímo v řádcích; pořadí se mění přetažením.

| Pole | Význam |
|---|---|
| **Název** | Co klient vidí na webu a v e-mailu. Překládá se (viz Překlady). |
| **Délka (min)** | Jak dlouho úkon trvá. Násobek 5 minut. |
| **Zkratka** | 1–3 znaky na kartě v tabuli (V, P, KA…). |
| **Barva** | Barva karty na tabuli. |
| **Nabízet online** | Odškrtnuté = jen pro recepci, na webu se nenabízí. |
| **Ordinace** | Kde se úkon dělá. Prázdné = ve všech ordinacích rezervovatelných online. |
| **Specializace** | **Kdo úkon dělá**: jen lékařky s aspoň jednou z těchto specializací. Prázdné = kterákoli lékařka. |
| **Kdo dělá** (sloupec v seznamu) | Kontrola: jména lékařek, které úkon dělají. „kterákoli lékařka“ = úkon bez specializace. „žádná lékařka – zkontrolujte specializace“ = úkon nikdo nedělá a **na webu nebude mít žádné termíny**. |
| **Instrukce pro klienta** | Např. „Zvíře přiveďte nalačno“. Ukáže se na webu a v e-mailu s potvrzením a v připomínce. |
| **Vyžaduje zálohu** / **Záloha** | Částka zálohy. Ukazuje se jen při zapnutých zálohách (viz Nastavení rezervace). |

Tip: Úkon, který nechcete nabízet, raději **archivujte** (Akce → Archivovat) než mažte.
Úkon použitý v rezervacích smazat nejde.

---

## 6. Rozpis lékařů

![Rozpis lékařů](img/rozpis-lekaru.png)

**Rezervace → Rozpis lékařů.** Kdo kdy ve které ordinaci slouží. Podle rozpisu:

- web nabízí termíny „k lékaři“ a úkony se specializací,
- recepce vidí v hlavičce sloupců tabule, kdo slouží,
- tabule navrhuje „Potvrdit → Ordinace · lékařka“.

Rozpis lékařů je samostatný od veřejného **Rozpisu služeb** (ten zná jen typ směny,
tady je potřeba ordinace a přesný čas).

### Zadání služeb

1. Klikněte **Nové** (nebo přidejte řádek v seznamu).
2. **Datum**, **Lékařka**, **Ordinace**, **Od**, **Do**.
3. Volitelně (skryté sloupce): **Jen tyto úkony** – v této službě dělá lékařka jen
   vybrané úkony (prázdné = všechny, které umí); **Poznámka**.

Jedna lékařka nemůže mít dvě služby přes sebe. Ve stejné ordinaci mohou sloužit
dvě lékařky současně.

Seznam má výchozí filtr **Od dneška**, seskupit lze podle **Den**, **Lékařka**,
**Ordinace**. Vpravo nahoře lze přepnout na týdenní kalendář.

### Kopírování týdne

1. V seznamu označte služby, které chcete zopakovat (např. filtrujte týden a zaškrtněte vše).
2. **Akce → Zkopírovat na další týden**.
3. Služby se zkopírují o 7 dní dál. Kopie, která by se překrývala s jinou službou téže
   lékařky, se přeskočí; stejně tak služba lékařky, která už nepřijímá rezervace.
   Hláška ukáže „Zkopírováno X, přeskočeno Y.“

---

## 7. Nastavení rezervace

![Nastavení rezervace](img/nastaveni.png)

**Rezervace → Konfigurace → Nastavení rezervace**, část **Vlastní rezervační systém**.

| Pole | Výchozí | Co dělá |
|---|---|---|
| **Krok slotů (min)** | 15 | Po kolika minutách se nabízejí začátky (8:15, 8:30…). Násobek 5. Zároveň mřížka tabule. |
| **Nejdříve za (hodin)** | 24 | Na web nejde objednat dřív než za tolik hodin. Recepce toto omezení nemá. |
| **Nejdál dopředu (dní)** | 60 | Jak daleko dopředu web nabízí termíny. Recepce může až ~400 dní. |
| **Klient může zrušit do (hodin před)** | 12 | Do kolika hodin před termínem funguje odkaz na zrušení v e-mailu. **0** = klient rušit odkazem nemůže. |
| **Online jen tam, kde slouží lékař** | vypnuto | Zapnuto: web nabízí termín jen v čase, kdy má ordinace v Rozpisu lékařů zapsanou službu. Vypnuto: úkony bez specializace se nabízejí podle ordinační doby, i když rozpis chybí. |
| **E-mail pro upozornění** | info@elite-vet.cz | Sem chodí upozornění na každou novou žádost z webu a na zrušení klientem. Prázdné = nic nechodí. |
| **Posílat připomínku** | vypnuto | Zapne připomínkový e-mail klientům. |
| **Připomínka (hodin před)** | 24 | Kolik hodin před termínem připomínka odejde (ukáže se po zapnutí). |
| **Zálohy zapnuté** | vypnuto | Dokud je vypnuté, záloha se nikde neukazuje. |
| Text nad rezervačním průvodcem | – | Text nad rezervací na webu (pole bez popisku, s nápovědou v šedé). |
| Souhlasím se zpracováním údajů… | – | Text souhlasu pod formulářem na webu (pole bez popisku). Prázdné = výchozí věta. |

Ve stejném formuláři jsou i starší části:

- **Telefon na recepci** – **Telefon na recepci** a **Recepce jak se zobrazí**. Používá se,
  když je na zrušení odkazem pozdě („zavolejte na recepci“).
- **Odkaz na rozpis služeb pod rezervací** – text a tlačítko pod rezervací na webu.
- **Rezervační systém (odkaz na WinVet)** a **Hláška, dokud se rezervace načítá** patří
  ke starému vloženému WinVetu. Vlastní rezervace je nepoužívá.

**Zálohy:** online platební brána zatím **není**. Při zapnutých zálohách se na webu ukáže
částka a klient dostane informaci, že platební údaje mu pošle recepce.

---

## 8. E-mailové šablony

Šablony najdete v **Nastavení → Technické → E-mailové šablony** (je potřeba zapnout
režim vývojáře), hledejte „Rezervace:“.

| Šablona | Kdy odchází |
|---|---|
| Rezervace: přijato z webu | klientovi po odeslání žádosti |
| Rezervace: nová z webu (klinika) | klinice na E-mail pro upozornění |
| Rezervace: potvrzeno | klientovi při potvrzení |
| Rezervace: změna termínu | klientovi při přesunu potvrzené rezervace |
| Rezervace: zrušeno | klientovi při zrušení (a klinice při zrušení klientem) |
| Rezervace: připomínka | klientovi X hodin před termínem (běží každou hodinu) |

Šablony jsou psané anglicky a přeložené do češtiny, němčiny a ruštiny. Klient dostane
e-mail v jazyce, ve kterém rezervoval. Upravujete-li text, upravte ho ve všech jazycích
(přepínač jazyka u pole). Adresa v potvrzení (Hybešova 167/18, Karlovy Vary) je přímo
v textu šablony.

Odesílatel je e-mail firmy (**Nastavení → Firmy → e-mail**).

---

## 9. Překlady

Web je ve čtyřech jazycích. Názvy úkonů, ordinací, instrukce pro klienta, důvod
blokace a texty v nastavení se překládají přímo v záznamu:

1. Vpravo nahoře přepněte svůj jazyk (nebo u pole klikněte na zkratku jazyka).
2. Přepište text.
3. Uložte a přepněte zpět.

Recepce na tabuli vidí vždy české názvy.

---

## 10. Kontrolní seznam před spuštěním

- [ ] Lékařky mají **Lékařka – přijímá rezervace** a propojenou **Karta v týmu**.
- [ ] Na kartách v Náš tým jsou **Specializace**.
- [ ] V **Úkony** nemá žádný online úkon v „Kdo dělá“ text „žádná lékařka“.
- [ ] Ordinace mají ordinační dobu, sál má odškrtnuté **Rezervovatelná online**.
- [ ] Svátky na nejbližší měsíce jsou zadané jako **Výjimky**.
- [ ] **Rozpis lékařů** je vyplněný aspoň na **Nejdál dopředu (dní)** dopředu.
- [ ] **Nastavení rezervace**: e-mail pro upozornění, telefon na recepci, rozhodnutí
      o „Online jen tam, kde slouží lékař“ a připomínkách.
- [ ] Zkušební rezervace z webu: dorazily oba e-maily (klientovi i klinice)?
- [ ] Zkušební zrušení odkazem z e-mailu funguje.
- [ ] Uživatelé mají skupinu **Recepce** nebo **Správce rezervací**.

### Technické nastavení serveru (pro správce Odoo)

- `proxy_mode = True` v `odoo.conf`, běží-li Odoo za reverzní proxy (nginx). Jinak
  limit 5 odeslání za 10 minut z jedné IP adresy počítá všechny klienty jako jednu
  adresu proxy a začne odmítat žádosti.
- **Odchozí poštovní server** (Nastavení → Technické → Odchozí poštovní servery)
  musí být nastavený a funkční; e-maily jdou přes frontu (cron „Mail: Email Queue Manager“).
- **E-mail firmy** musí být vyplněný – je odesílatelem všech rezervačních e-mailů.
- Správná **webová adresa** (`web.base.url`) – z ní se skládá odkaz na zrušení v e-mailu.
- Po aktualizaci modulu s novými překlady:
  `odoo -u elite_vet_reservation --i18n-overwrite` (bez toho se nové překlady
  e-mailových šablon a textů nepřepíšou).
- Cron **Rezervace: připomínky klientům** běží každou hodinu (dělá něco jen při zapnutých připomínkách).
- Živá aktualizace tabule potřebuje funkční websocket (`/websocket` přes proxy,
  v produkci workers + gevent port). Bez něj se tabule obnovuje jednou za minutu.
