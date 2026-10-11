# Rezervace

Odoo 18 modul. Nahrazuje rezervační systém WinVet: ordinace, ordinační doba,
rozpis lékařů, úkony a rezervace jsou v Odoo, na webu `/rezervacni-system`
běží vlastní průvodce místo iframu.

## Návody (česky)

- [Návod pro recepci](doc/recepce.md) – tabule, žádosti z webu, nová rezervace,
  přesun, blokace, klienti, e-maily, časté situace.
- [Návod pro správce](doc/nastaveni.md) – práva, lékařky a specializace, ordinace
  a ordinační doba, úkony, rozpis lékařů, nastavení rezervace, kontrolní seznam
  před spuštěním.
- [Jak to funguje](doc/jak-to-funguje.md) – výpočet volných termínů, pravidlo
  lékařka × úkon, cesta žádosti z webu, ochrana proti dvojímu zabrání.

Snímky obrazovek jsou v `doc/img/`.

## Stručně

- Aplikace **Rezervace**: **Tabule**, **Nová rezervace**, **Čekající z webu**,
  **Rezervace**, **Rozpis lékařů**, **Klienti**, **Mazlíčci**, **Konfigurace**
  (Ordinace, Výjimky ordinační doby, Úkony, Nastavení rezervace, Časté dotazy).
- Skupiny: **Recepce** (denní práce) a **Správce rezervací** (konfigurace).
- Lékařka = **Lékařka – přijímá rezervace** v Rozpis služeb → Lékařky; kdo dělá
  který úkon, plyne ze specializací na kartě v Náš tým.

## Nasazení

- `proxy_mode = True` v `odoo.conf` za reverzní proxy (limit žádostí na IP adresu).
- Funkční odchozí pošta a vyplněný e-mail firmy (odesílatel e-mailů).
- Upgrade s novými překlady: `-u elite_vet_reservation --i18n-overwrite`.

## Co modul neumí (zatím)

Platební brána pro zálohy, import klientů z WinVetu (pole *ID ve WinVetu* je
připravené), SMS.
