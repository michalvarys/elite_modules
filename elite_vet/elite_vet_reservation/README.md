# Rezervace

Odoo 18 modul. Nahrazuje rezervační systém WinVet: ordinace, ordinační doba,
rozpis lékařů, úkony a rezervace jsou v Odoo, na webu `/rezervacni-system`
běží vlastní průvodce místo iframu.

Aplikace **Rezervace** má položky: **Tabule**, **Čekající z webu**,
**Rezervace**, **Rozpis lékařů**, **Klienti**, **Mazlíčci**, **Konfigurace**
(Ordinace, Výjimky ordinační doby, Úkony) a **Nastavení rezervace**.

## Denní práce recepce

1. **Tabule** – jeden den, sloupec na každou ordinaci. Šrafované = zavřeno,
   v hlavičce sloupce je, kdo slouží. Klik do prázdna = nová rezervace
   v tom čase. Přetažení přesune rezervaci na jiný čas nebo ordinaci.
2. **Čekající z webu** (levý panel tabule) – každá žádost z webu. Buď ji
   přetáhněte do sloupce (potvrdí se v tom čase), nebo otevřete, vyberte
   ordinaci a klikněte **Potvrdit**. **Odmítnout** pošle klientovi e-mail.
3. Po návštěvě **Proběhla** / **Nedorazil** (volitelné, kvůli přehledům).

## Co nastavit jednou

| Kde | Co |
|---|---|
| Konfigurace → Ordinace | název, barva, *Rezervovatelná online* (Sál odškrtnout), záložka **Ordinační doba** (týdenní šablona, přestávka = dva řádky), záložka **Výjimky** (svátek = zavřeno, nebo jiné hodiny) |
| Konfigurace → Úkony | název, délka, barva, *Nabízet online*, ve kterých ordinacích, instrukce pro klienta (nalačno…), záloha |
| Rozpis lékařů | kdo kdy v které ordinaci slouží; podle toho web nabízí „k lékaři“ a tabule ukazuje jména |
| Nastavení rezervace | krok slotů, nejdřív za X hodin, nejdál X dní, zrušení klientem do X hodin, e-mail pro upozornění, připomínky, zálohy, texty nad formulářem a souhlasu |

## Blokace (oběd, operace, zavřeno)

Tabule → **Nová blokace**: důvod, ordinace (prázdné = všechny), od–do,
případně *Opakovat týdně do*. Blokace se na webu nenabízí.

## E-maily

Klient dostane: přijato (z webu), potvrzeno (s odkazem na zrušení), změna
termínu, zrušeno, připomínka (pokud je zapnutá). Klinika dostane každou novou
žádost z webu na e-mail z Nastavení. Šablony: Nastavení → Technické →
E-mailové šablony, hledat „Rezervace:“.

## Překlady

Zdroj je angličtina, čeština/němčina/ruština jsou v `i18n/`. Názvy úkonů,
ordinací a instrukce se překládají přímo v záznamu (přepnout jazyk vpravo
nahoře a přepsat).

## Nasazení

V produkčním `odoo.conf` za reverzní proxy musí být `proxy_mode = True`, jinak by
limit rezervací na IP adresu počítal adresu proxy za všechny klienty dohromady.

## Co modul neumí (zatím)

Platební brána pro zálohy, import klientů z WinVetu (pole *ID ve WinVetu* je
připravené), SMS.
