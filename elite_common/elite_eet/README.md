# Elite – EET 2.0

Jádro evidence tržeb EET 2.0 (zákon č. 180/2026 Sb., povinně od 1. 1. 2027). Modul sám nic neprodává.
Tržby do něj posílá pokladna přes modul `elite_eet_pos`, ten si přečtěte jako první.

Co modul dělá:

- **Nastavení EET pokladny** (`elite.eet.device`). Každá pokladna má vlastní: certifikát, EIČ, číslo
  evidenční jednotky, označení pokladny, prostředí (Playground nebo produkce), datum „EET od“ a mezní
  dobu odezvy.
- **Datová zpráva.** Sestaví ji podle XSD 4.1, zkontroluje proti schématu a velikosti 12 kB a podepíše
  WS-Security pokladním certifikátem.
- **Odeslání a záznam.** Každá tržba (`elite.eet.sale`) má stav Čeká, Evidováno nebo Chyba, POK a historii
  pokusů (`elite.eet.attempt`) i s odeslanou a přijatou zprávou.
- **Fronta.** Cron každou minutu pošle čekající tržby jako opakované zaslání: stejná data, nové UUID,
  `prvni_zaslani="false"`. Když EET u pokladny neodpoví, zbytek jejích tržeb se v tom běhu přeskočí, aby se
  nečekalo desetkrát na timeout.
- **Hromadná akce „Odeslat do EET“** v seznamu Tržby EET. Pošle označené tržby ve stavu Čeká a Chyba,
  evidované přeskočí.
- **Tlačítko „Ověřit spojení“** u nastavení pokladny. Pošle zprávu v ověřovacím módu, nic se neeviduje.
- **Upozornění vedoucímu pokladny** (aktivita na nastavení EET):
  - tržba skončila chybou,
  - tržba čeká déle než 24 hodin,
  - tržba je po lhůtě 48 hodin,
  - certifikát vyprší do 21 dnů.

  Cron hlídání běží každou hodinu a stejné upozornění nezakládá dvakrát.

Odesílání tržeb má jediný vstup, `elite.eet.sale._eet_send()`, a přenos je v `eet/transport.py`. Až EET
podpoří dávky, změní se jen tato dvě místa.

## Pravidla, která modul hlídá

- **Odeslání při zaplacení.** Tržba se odešle hned po uložení objednávky, ve vlastní transakci. Výpadek EET
  tak nezruší uložení objednávky a pokladna se zdrží nejvýš o mezní dobu odezvy (výchozí 3 s, minimum 2 s
  podle § 19).
- **Data tržby se po prvním pokusu nedají změnit.** Opakované zaslání tak posílá stejnou tržbu.
- **Kritická chyba (kód 2–8)** se automaticky neopakuje. Tržba čeká na opravu příčiny (např. certifikát)
  a na ruční „Odeslat do EET“.
- **Dočasná chyba (kód -1 a nižší) nebo žádná odpověď:** tržba zůstává ve frontě.
- **Ochrana produkce:**
  - Produkční adresu EET použije jen pokladna přepnutá na Produkce, a to jen s produkčním certifikátem.
    Nesoulad prostředí a certifikátu nejde uložit.
  - Při běhu testů produkci nic neodešle.
- **Certifikát a heslo** vidí jen správce systému. Do logu, chatteru ani pokusů se nedostanou.

Systémový parametr `elite_eet.playground_url_override` nahradí adresu Playgroundu, například
nedosažitelnou adresou při zkoušce výpadku. Na produkci nemá vliv. Nastavujte ho přes Odoo (Nastavení →
Technické → Systémové parametry), ne přímo v databázi: běžící server má parametry v mezipaměti.

## Oprávnění

| Skupina | Smí |
|---|---|
| EET / Uživatel (každý uživatel pokladny) | číst tržby a nastavení |
| EET / Správce (správce pokladny) | odesílat tržby, ověřovat spojení, měnit nastavení kromě certifikátu |
| Správce systému | nahrát certifikát a heslo |

## Testy

Testovací databáze se zakládá bez demo dat:

```bash
docker exec odoo odoo -c /etc/odoo/odoo.conf -d eet_test -i elite_eet_pos --without-demo=all --stop-after-init --http-port 8071
# testy bez sítě (oba moduly)
docker exec odoo odoo -c /etc/odoo/odoo.conf -d eet_test -u elite_eet,elite_eet_pos \
  --test-tags /elite_eet,/elite_eet_pos --stop-after-init --http-port 8071
# testy proti skutečnému Playgroundu (síť; spouští se jen výslovně)
docker exec odoo odoo -c /etc/odoo/odoo.conf -d eet_test -u elite_eet --test-tags eet_playground \
  --stop-after-init --http-port 8071
```

`tests/data/` obsahuje veřejná testovací data finanční správy: tři certifikáty Playgroundu (heslo
`aaaa1111`, platné do 14. 5. 2027) a jejich vzorové podepsané zprávy. Testy ověřují podpisy vzorů vlastním
kódem. Odpovědi `resp_*.xml` jsou skutečné odpovědi Playgroundu, kromě `resp_error_temp.xml`
a `resp_fault.xml`.

### Ověřeno proti Playgroundu (12. 11. 2026)

- Všechny tři testovací certifikáty dostanou POK končící `-ff` a `test="true"`.
- Ověřovací mód vrací chybu s kódem 0. Záporná tržba i voucherové položky projdou.
- Pozměněná zpráva dostane kód 4 „Neplatny podpis SOAP zpravy“.
- EIČ jiné než v certifikátu: POK s varováním 1.
- **Pozor při úpravách podpisu:** otisk se musí počítat ze zprávy načtené z hotových bajtů. Kanonizace stromu
  sestaveného v paměti (lxml) občas vynechá deklarace jmenných prostorů. Server pak vrátí kód 4, přestože
  vlastní kontrola v témže procesu projde. Hlídá to test `test_first_signature_in_fresh_process`.
- **Na pokladně v prohlížeči:**
  - zaplacená objednávka dostala POK do 1 s;
  - při nedostupném EET (2 s) pokladna platbu dokončila a tržba zůstala „Čeká“;
  - po obnovení spojení ji fronta do minuty evidovala jako opakované zaslání.

## Co je mimo tento modul

- Faktury placené mimo pokladnu.
- Tisk POK na účtenku (EET 2.0 ho nevyžaduje).
- Pověřování jiným poplatníkem.
- Automatická obnova certifikátu přes API CA EET. Je to druhá fáze; zatím jen upozornění 21 dní předem
  a nový certifikát se nahraje ručně.
