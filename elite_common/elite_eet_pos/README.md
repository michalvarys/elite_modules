# Elite – EET 2.0 pro pokladnu

Napojení evidence tržeb EET 2.0 (modul `elite_eet`) na pokladnu Odoo. Je pro Elite Arenu a Elite Trafiku,
povinně od 1. 1. 2027.

## Jak to funguje

1. Pokladní na pokladně potvrdí platbu.
2. Objednávka se uloží na serveru a hned potom se tržba odešle do EET.
3. U objednávky (Další informace → EET) a v Pokladna → EET → Tržby EET je stav a POK.
4. Neodeslané tržby posílá fronta každou minutu. O chybách a tržbách čekajících přes 24 hodin dostane vedoucí
   pokladny aktivitu.

Pokladna bez zapnutého nastavení EET se chová jako dřív. Modul u ní nic nemění.

### Co se do EET posílá

- **Jen objednávky zaplacené na obrazovce pokladny** a jen s časem zaplacení po „EET od“. Objednávky
  z importu (historie z Dotykačky v `elite_trafika_dotykacka`) ani objednávky založené v administraci se
  nikdy neposílají.
- **Částka tržby** je součet plateb způsoby se zapnutým „Evidovat v EET“. Vrácené peníze (řádek „vráceno“
  u hotovosti) se odečtou: 1000 Kč hotově za nákup 250 Kč je tržba 250 Kč.
- **Interní záznamy** (za které se nic neplatí, ale částka má být v systému) se markují způsobem platby,
  který má „Evidovat v EET“ vypnuté. Objednávka zaplacená jen takto do EET nejde. Smíšená objednávka pošle
  jen evidovanou část.
- **Vratka** z pokladny je samostatná záporná tržba s časem vrácení.
- **Pořadové číslo tržby** je číslo objednávky bez diakritiky a za `#` interní číslo objednávky, například
  `Pokladna Bar c. 1/0001#57`. Odoo dává všem vratkám jedné objednávky stejný název a dlouhý název pokladny
  by jinak usekl číslování; takhle je číslo vždy jedinečné.
- **Chyba EET nikdy nezastaví uložení objednávky.** Kdyby tržba výjimečně nevznikla, vedoucí pokladny
  dostane aktivitu „Tržba EET nevznikla“.
- **Odložená platba na účet zákazníka** (typ Pay Later) má „Evidovat v EET“ ve výchozím stavu vypnuté.
- **Vouchery na blíže neurčené zboží:**
  - Produkt voucheru má zaškrtnuté „Předplacený kredit/voucher na neurčené zboží“. Jeho prodej jde do EET
    i jako `urceno_cerp_zuct`.
  - Uplatnění takového voucheru se markuje způsobem platby s „Čerpání předplaceného kreditu/voucheru“. Jde
    do `cerp_zuct` a je součástí tržby.
  - Dárkový poukaz na konkrétní zboží nebo službu se neoznačuje. Je to běžný prodej.
- **Dárkové karty a e-peněženka** z modulu Věrnostní programy Odoo nejsou podporované. Arena ani Trafika je
  nepoužívají. Objednávka s nimi by se poslala jen podle plateb.

### Pokladna offline

Když pokladna ztratí spojení se serverem, objednávky si drží v prohlížeči a pošle je po obnovení. Tržba pak
vznikne až na serveru, s časem zaplacení, a do EET jde jako opakované zaslání. Dorazí-li objednávka
na server víc než 5 minut po zaplacení, zpráva nese `prvni_zaslani="false"`.

Zákon ale chce první pokus nejpozději při zaplacení. **Obsluha proto nesmí zavírat pokladnu, dokud jsou
objednávky čekající na synchronizaci** (pokladna je ukazuje v horní liště). Zjistí-li výpadek internetu,
má co nejdřív obnovit spojení. Pokladní systém pak tržby pošle sám, nejpozději do 48 hodin.

## Nastavení (pro každou pokladnu zvlášť)

1. **Evidenční jednotka a certifikát.** V portálu MOJE daně (DIS+) založte evidenční jednotku a vydejte
   pokladní certifikát (.p12 a heslo). Certifikát platí rok.
2. **Nastavení pokladny.** Pokladna → EET → Nastavení pokladen EET → Nový:
   - vyberte pokladnu;
   - doplňte EIČ a číslo evidenční jednotky (označení pokladny se doplní z jejího názvu);
   - jako správce systému nahrajte certifikát a heslo;
   - nechte prostředí Playground.
3. **Ověření.** Klikněte na „Ověřit spojení“. Má se objevit „Spojení s EET funguje.“
4. **Ostrý provoz.** Přepněte prostředí na Produkce (vyžaduje produkční certifikát), nastavte „EET od“ na
   1. 1. 2027 0:00 a zaškrtněte Zapnuto.
5. **Způsoby platby.** Zkontrolujte „Evidovat v EET“: Hotově a Kartou ano, interní způsob ne.

Zkušební odesílání do produkce je možné od 1. 12. 2026. V lednu 2027 běží pilotní režim, ale evidence je
už povinná.

## Nasazení na produkci

**Produkční databáze má zapnutá demo data.** Před instalací se musí vypnout, jinak Odoo nahraje demo data
závislých modulů:

```bash
# 1. záloha
docker compose exec db pg_dump -U odoo -Fc odoo > odoo_pred_eet.dump
# 2. vypnout demo data (jen příznak modulů, žádná data se nemažou)
docker compose exec db psql -U odoo -d odoo -c "UPDATE ir_module_module SET demo = false WHERE demo;"
# 3. instalace
cd elite_modules && git pull
docker compose exec odoo odoo -d odoo -i elite_eet_pos --stop-after-init --no-http
docker compose restart odoo
```

Server musí mít `/mnt/modules/elite_common` v `addons_path`. Názvy služeb a databáze upravte podle serveru.
Na produkci nespouštějte testy.

Modul nepřepisuje nic u existujících firem a pokladen. Přidá jen:

- pole u pokladny, způsobu platby, produktu a objednávky;
- menu Pokladna → EET;
- dvě skupiny práv: uživatelé pokladny dostanou EET / Uživatel, správci pokladny EET / Správce.

Dokud pokladna nemá zapnuté nastavení EET, nic se neodesílá.

## Před ostrým provozem je potřeba rozhodnout

- **Poplatník za Trafiku je SL FORTIS s.r.o.** (IČO 18020984, DIČ a EIČ CZ18020984; rozhodnuto 12. 11. 2026).
  Evidenční jednotka a certifikát Trafiky se zakládají v DIS+ této firmy. Pozor: v Odoo je Elite Trafika
  vedená jako pobočka firmy Elite, takže účetnictví a DPH tržeb Trafiky jsou teď v knihách Elite. To je
  potřeba vyřešit s účetní; EET to nijak neovlivní.
- **Které vouchery Areny jsou na blíže neurčené zboží** (VOUCHER 500 Kč a 1000 Kč?). Jen ty se označí.
- **Kredit hráčů v ggLeapu.** Dobití se prodává na pokladně Odoo a eviduje se. Zda je čerpání kreditu
  v ggLeapu další evidovanou tržbou, má posoudit účetní. Modul ho neřeší.

## Testy

Viz README modulu `elite_eet`. Testy pokladny jsou v `tests/test_pos_eet.py` a `tests/test_pos_views.py`.
