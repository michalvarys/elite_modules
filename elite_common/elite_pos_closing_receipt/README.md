# Elite – tisk uzávěrky pokladny

Sdílený modul pro všechny pokladny (Aréna, Trafika). V okně **Zavřít pokladnu** místo tlačítka
„Daily Sale“ (stažení PDF reportu) je tlačítko **Vytisknout uzávěrku**. Zmizí i tisk denního prodeje
přes IoT tiskárnu, uzávěrka ho nahrazuje. Tlačítko Cash In/Out zůstává.

Uzávěrka jde na účtenkovou tiskárnu pokladny; bez tiskárny se otevře tisk prohlížeče. Dá se
vytisknout kolikrát chcete, i před uzavřením a bez něj.

## Co je na uzávěrce

- pokladna, směna, kdy se otevřela, kdo uzavírá
- tržba celkem
- platby podle způsobu platby
- hotovost v kase: počáteční stav, přijato v hotovosti, vklady a výběry, kolik má být v kase
- DPH podle sazeb (základ, daň), už po odečtení vratek
- slevy, vratky, zaokrouhlení (jen když nějaké jsou)
- prodej podle kategorií pokladny; zaškrtnutím „Na uzávěrce vypsat i jednotlivé zboží“ i po kusech

Všechny částky jsou s DPH. Čísla se berou ze stejného výpočtu jako report denního prodeje Odoo
(`report.point_of_sale.report_saledetails`) a hotovost ze stejného výpočtu jako okno zavírání
(`get_closing_control_data`), takže sedí s oběma. Data vrací `pos.session.get_elite_closing_receipt()`.

## Nasazení

`/mnt/modules/elite_common` v `addons_path`, jednou `-i elite_pos_closing_receipt` (modul se
nainstaluje i sám, je `auto_install` k pokladně), restart a obnovení stránky pokladny. Modul
nevytváří žádná data.

## Testy

`--test-tags /elite_pos_closing_receipt`: tržba, platby, hotovost v kase, DPH po vratkách, kategorie.
