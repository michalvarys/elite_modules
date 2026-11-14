# Elite – tisk uzávěrky pokladny

Sdílený modul pro všechny pokladny (Aréna, Trafika). V okně **Zavřít pokladnu** místo tlačítka
„Daily Sale“ (stažení PDF reportu) je tlačítko **Vytisknout uzávěrku**. Zmizí i tisk denního prodeje
přes IoT tiskárnu, uzávěrka ho nahrazuje. Tlačítko Cash In/Out zůstává.

Uzávěrka jde na účtenkovou tiskárnu pokladny; bez tiskárny se otevře tisk prohlížeče. Dá se
vytisknout kolikrát chcete, i před uzavřením a bez něj.

## Zpětný tisk ze směny

V backendu **Pokladna → Směny** má formulář směny tlačítko **Vytisknout uzávěrku** (a je i v menu
Tisk, takže jde vybrat víc směn naráz). Rovnou otevře dialog tisku prohlížeče s uzávěrkou
ve formátu účtenky (80 mm), bez náhledu a bez stahování PDF. Report jde i stáhnout jako PDF
(`action_report_closing_receipt`, papír 80 mm); každá uzávěrka je v `div.article`, jinak Odoo
v PDF rozbije češtinu. U uzavřené směny je navíc čas uzavření, **spočítaná
hotovost** a **rozdíl** proti tomu, co mělo být v kase.

Šablona zpětného tisku (`report/closing_receipt_report.xml`) má stejný obsah jako účtenka
v pokladně (`static/src/closing_receipt/closing_receipt.xml`); při změně upravit obě.

## Co je na uzávěrce

- pokladna, směna, kdy se otevřela (u zpětného tisku i kdy se uzavřela), kdo uzavírá
- tržba celkem
- platby podle způsobu platby
- hotovost v kase: počáteční stav, přijato v hotovosti, vklady a výběry, kolik má být v kase
- DPH podle sazeb (základ, daň), už po odečtení vratek
- slevy, vratky, zaokrouhlení (jen když nějaké jsou)
- prodej podle kategorií pokladny; zaškrtnutím „Na uzávěrce vypsat i jednotlivé zboží“ i po kusech

Všechny částky jsou s DPH. Tržba, DPH a kategorie se berou ze stejného výpočtu jako report denního
prodeje Odoo (`report.point_of_sale.report_saledetails`); platby po způsobech a hotovost počítá modul
sám stejně jako okno zavírání, protože starší sestavení Odoo 18 vrací z reportu jiné klíče a po
uzavření směny Odoo přidá do pohybů hotovosti tržbu a rozdíl při počítání (ty se vynechají). Data
vrací `pos.session.get_elite_closing_receipt()`, výpočet běží s právy superuživatele po ověření
přístupu ke směně (pokladní nemá práva na účetní platby, které report Odoo čte).

## Nasazení

`/mnt/modules/elite_common` v `addons_path`, jednou `-i elite_pos_closing_receipt` (modul se
nainstaluje i sám, je `auto_install` k pokladně), při aktualizaci `-u elite_pos_closing_receipt`,
restart a obnovení stránky pokladny. Modul přidává jen report a tlačítko, žádná obchodní data.

## Testy

`--test-tags /elite_pos_closing_receipt`: tržba, platby, hotovost v kase, DPH po vratkách, kategorie,
běžný pokladní, starší Odoo 18, uzavřená směna (spočítáno, rozdíl, vklady po uzavření) a zpětný tisk.
