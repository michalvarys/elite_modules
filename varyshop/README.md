# varyshop — značka Varyshop v Odoo

Moduly, které v **oficiálním Odoo 18** (image `odoo:18`) nahradí logo a značku Odoo značkou
Varyshop. Odoo samotné se nemění, takže jde používat aktuální Odoo s jeho opravami.

**Instalace.** Stačí mít složku `varyshop` v `addons_path`:

- **Nová databáze:** `varyshop_brand` se nainstaluje sám s první aplikací (Odoo s ní instaluje
  `mail`). Doplňky pro pokladnu, web a portál se nainstalují samy s danou aplikací, i když se
  přidá později.
- **Existující databáze** (už má aplikace nainstalované): Odoo samo doinstaluje modul jen
  spolu s některou jeho závislostí, proto se jednou nainstaluje ručně. Doplňky se přidají
  k aplikacím, které databáze má:

```bash
odoo -d <databáze> -i varyshop_brand --stop-after-init
```

| Modul | Kdy se instaluje | Co změní |
|---|---|---|
| `varyshop_brand` | sám s první aplikací (v existující databázi jednou ručně) | titulek okna a favicona, přihlášení („Powered by Varyshop“), ikona a název aplikace na mobilu (PWA), stránka offline, Nastavení → O aplikaci, menu uživatele (Dokumentace a Podpora na varyshop.eu, bez „Můj účet Odoo.com“), titulky dialogů („Varyshop varování“), patička e-mailů, **modrá Varyshop místo fialové Odoo** (horní lišta, tlačítka, odkazy, výběry, pokladna, tlačítka v e-mailech) |
| `varyshop_brand_pos` | sám s Pokladnou | logo v horní liště pokladny, šetřič obrazovky, „Běží na Varyshop“ na účtence a na zákaznickém displeji, titulek a favicona pokladny |
| `varyshop_brand_website` | sám s Webem | patička webu „Běží na Varyshop – Řízení firmy a automatizace procesů“ s odkazem na varyshop.eu, favicona webu, logo v editoru webu |
| `varyshop_brand_portal` | sám s Portálem | „Běží na Varyshop“ u dokumentů na zákaznickém portálu |

**E-maily.** Odkaz „Powered by Odoo“ je kromě rozvržení e-mailů i v šablonách jednotlivých
aplikací (pozvánka, reset hesla, přehledy…). Ty se nepřepisují; odkaz na odoo.com se nahradí
až při odeslání e-mailu (`models/mail_mail.py`), takže platí i pro šablony upravené v Odoo.

**Barvy.** Podle www.varyshop.eu: logo `#6EA8FE`, tmavší modrá `#3D7BD9`. Bílé písmo a ikony
(horní lišta, hlavní tlačítka) na světlé `#6EA8FE` nejsou čitelné, proto je v Odoo `#3D7BD9`
(`static/src/scss/primary_variables.scss`, platí pro backend i pokladnu). V e-mailech se fialová
Odoo (`#875A7B`, `#714B67`, `#71639e`) nahradí při odeslání. Weby si barvy nechávají: výchozí
paleta webu zůstává jako v Odoo, vlastní palety se nemění.

**Co zůstane.** Nastavení → O aplikaci dál uvádí, že jde o Odoo Community Edition, s copyrightem
Odoo S.A. a licencí LGPL (to licence vyžaduje). Zůstanou i QR kódy na mobilní aplikaci Odoo,
protože ta se k serveru opravdu připojuje. Názvy aplikací v seznamu modulů se nemění; fialová
natvrdo v několika stránkách webu (průzkumy, kurzy, akce) zůstává. Texty s „Odoo“ uvnitř stránek (nápovědy, popisky nastavení) modul nepřepisuje.

**Co nepřepíše.** Faviconu webu změní jen tam, kde je výchozí favicona Odoo; vlastní favicona
zůstane. Název aplikace pro mobil (`web.web_app_name`) nastaví jen tam, kde je výchozí „Odoo“.
Odinstalace vrátí obojí zpět.

**Varyshop fork.** Image `varyshop/website` má značku Varyshop přímo v kódu Odoo a je starší
verze řady 18.0 (např. pokladna v něm nemá šetřič obrazovky). Moduly jsou pro oficiální
`odoo:18` a do forku se neinstalují.

Logo a ikony jsou ze zdrojů forku (`varyshop.eu/website`, commit „logos“);
`static/img/favicon.ico` a `icon-ios.png` jsou z ikony VS dopočítané.

## Testy

```bash
odoo -d <testovací databáze> -i point_of_sale,website,varyshop_brand --test-tags /varyshop_brand,/varyshop_brand_website --stop-after-init
```
