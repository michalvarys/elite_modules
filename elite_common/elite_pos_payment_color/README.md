# Elite – barvy a rozložení plateb v pokladně

Platební metodě pokladny jde nastavit barvu. Na obrazovce platby má pak její tlačítko pozadí
v této barvě, takže obsluha rozliší Hotově, Kartou, Stravenky a další platby na první pohled.

**Nastavení:** Pokladna → Konfigurace → Platební metody → pole **Barva tlačítka v pokladně**
(výběr barvy, jde i do seznamu metod). Prázdné pole = běžné šedé tlačítko. Změna se v pokladně
projeví po jejím znovunačtení.

- Písmo na tlačítku je bílé nebo tmavé, podle toho, co je na vybrané barvě lépe čitelné.
- Při najetí a stisku tlačítko lehce ztmavne.
- Barva se ukazuje jen na tlačítkách pro výběr platby, řádky zadaných plateb zůstávají beze změny.
- Barvu jde změnit i při otevřené směně (ostatní údaje platební metody Odoo při otevřené směně
  měnit nedovolí).

**Rozložení tlačítek:** Pokladna → Nastavení → Platba → **Rozložit tlačítka plateb**.

- Vypnuto (výchozí, jako v Odoo): tlačítka plateb jsou seřazená za sebou od shora.
- Zapnuto: tlačítka se rozloží s mezerami po celé výšce panelu (první nahoře, poslední dole).
- Platí pro tablet a počítač; na mobilu jsou tlačítka vždy ve dvou sloupcích jako v Odoo.

Modul se neinstaluje sám: `-i elite_pos_payment_color`.
