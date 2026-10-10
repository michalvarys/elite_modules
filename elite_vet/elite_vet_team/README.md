# Náš tým

Odoo 18 modul. Přidává aplikaci **Náš tým** a veřejnou stránku **`/nas-tym`**.

Celý obsah stránky je v Odoo, ne v kódu. Klinika si sama přidává a odebírá lidi,
nahrává fotky, přepisuje pozice a popisy a mění pořadí.

Aplikace má tři položky: **Členové týmu**, **Sekce**, **Popisky podrobností**.

## Členové týmu

Výchozí pohled je kanban s fotkami, seskupený po sekcích. Kartu jde přetáhnout
do jiné sekce, v seznamu se přetažením za úchyt mění pořadí na stránce.

Formulář odpovídá kartě na webu:

| Pole | Kde se objeví |
|---|---|
| Fotka | kolečko vlevo; bez fotky se vykreslí iniciály |
| Jméno a titul | nadpis karty |
| Pozice | řádek pod jménem |
| Štítek na kartě | tmavý štítek, například *Odborná garantka*; prázdný = není |
| E-mail | zelený odznáček s odkazem; prázdný = není |
| Popis | odstavec vidět hned |
| Podrobnosti | rozbalovací část pod tlačítkem *Vzdělání, praxe a specializace* |

**Iniciály se počítají ze jména** a tituly se přeskakují, takže
`MVDr. Kateřina Kadavá` dá `KK`, ne `MK`.

Kdo odejde, nemusí se mazat — stačí odškrtnout **Aktivní** a karta ze stránky
zmizí. Historie zůstane.

## Sekce

Nadpisy na stránce: Veterinární lékařky, sestry, recepce, management. Jdou
přejmenovat, přeskládat i přidat nové. Prázdná sekce se na webu nezobrazí.

**Kotva** je krátký text v adrese (`/nas-tym#lekarky`), aby šlo poslat odkaz
přímo na část stránky. Nemusí se vyplňovat — dopočítá se z názvu, diakritika
a mezery se odstraní. Když už stejná kotva existuje, přidá se číslo.

Odkazy nahoře na stránce se ze sekcí generují samy.

## Popisky podrobností

Číselník pro *Vzdělání*, *Praxe*, *Specializace* a podobně. U člověka se pak
vybírá ze seznamu místo přepisování — odpadají překlepy a nesourodé varianty,
a překlad se dělá jednou pro popisek, ne u každého člověka znovu.

Zapnutý přepínač **Předvyplnit** znamená, že se ten řádek u nového člověka
nabídne rovnou prázdný. Po instalaci je zapnutý u pěti nejběžnějších, takže
nový člověk má připravené:

```
Vzdělání · Praxe · Specializace · Další vzdělávání · Jazyky
```

Nevyplněný řádek se na web nedostane, takže přebývající nevadí. Nový popisek
jde založit i rovnou při psaní u člověka.

## Překlady

Pozice, štítek, popis, popisky i texty podrobností jsou přeložitelné běžným
režimem **Přeložit** v Odoo. Jména a e-maily ne — ty se nepřekládají.

Pozor: **každé přepsání archu stránky smaže překlady.** U tohohle modulu se
ale arch nemění, obsah je v databázi, takže se to netýká běžné práce.

## Po instalaci

Modul se naplní tím, co bylo na původní ruční stránce: **4 sekce, 8 lidí,
38 podrobností**. Klinika nezačíná u prázdného seznamu.

Zakládá se to jednou při instalaci, ne jako data modulu. Kdo se smaže,
se po aktualizaci modulu **nevrátí**.

## Pro správce

* Modely: `elite.vet.team.member`, `elite.vet.team.section`,
  `elite.vet.team.fact`, `elite.vet.team.fact.label`
* Fotky přes `image.mixin`; na webu se servírují jako
  `/web/image/elite.vet.team.member/<id>/image_512`
* Veřejný přístup pro čtení má `base.group_public` i `base.group_portal` —
  bez toho by fotky viděl jen přihlášený admin
* Záznam stránky `website.page` je publikovaný rovnou modulem
* Multi-website: `website_id` není nastavené, stránka je na všech webech
  v databázi

**Před instalací na web, kde už `/nas-tym` existuje jako ručně vytvořená
stránka, se ta stránka musí smazat** — jinak se URL srazí a instalace spadne.

Nasazení přes Docker: [../../DOCKER.md](../../DOCKER.md).

## Více webů v jedné databázi

Stránka se při instalaci **přiřadí jednomu webu**, ne všem. Modul hledá web,
jehož doména obsahuje `elite-vet`; když ho nenajde, vezme ten, který má v názvu
nebo doméně „vet" a zároveň ne „arena". Který web to byl, napíše do logu.

Změnit to jde kdykoliv v **Web → Konfigurace → Stránky** u pole *Web*. Stránka
bez přiřazeného webu se zobrazí na všech doménách v databázi, což na sdílené
instalaci nechcete.

## Uživatelská práva

Modul má vlastní skupinu **Správce týmu** (kategorie *Náš tým*). Kdo ji nemá,
aplikaci v Odoo vůbec nevidí. Nastavuje se v **Nastavení → Uživatelé**
u konkrétního člověka.
