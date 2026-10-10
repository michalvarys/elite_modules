# Elite Vet — Web

Verejne stranky kliniky jako modul. Driv to byly archy, ktere se rucne vkladaly
do editoru webu; ted jsou v gitu a nasazuji se jako kod.

| stranka | sablona |
|---|---|
| `/` | `elite_vet_web.homepage` |
| `/rezervacni-system` | `elite_vet_web.rezervace` |
| `/cenik` | `elite_vet_web.cenik` |

## Obsah se spravuje v Odoo

Aplikace **Web kliniky** v Odoo. Co tam neni, na webu nebude:

| nabidka | co ridi |
|---|---|
| Sluzby | mrizka sluzeb na PC i rozbalovaci seznam na mobilu |
| Galerie kliniky | pas fotek v sekci O klinice |
| Ordinacni hodiny | tabulka hodin v sekci Kontakt |
| Kontaktni karty | adresa, telefon, e-mail |
| Caste dotazy | seznam na strance rezervace |
| Cenik | ukony, ceny a jejich skupiny |
| Nastaveni webu | telefon, e-mail, adresa, odkaz na mapu a na WinVet |

Specializace a ikony maji vlastni nabidku v **Nas tym** a v **Rozpis sluzeb**;
je to jeden seznam ve dvou nabidkach, ne dve kopie.

Vsechny texty jdou prekladat: v Odoo se prepne jazyk vpravo nahore a text se
prepise. Nastaveni webu se neprekalada — telefon ani adresa se nemeni s jazykem.

Vychozi obsah zaklada instalace modulu (models/seed.py z
data/vychozi-obsah.json), a to **jen pri prvni instalaci**. Od te chvile
obsah patri klinice a upgrade modulu do nej uz nesaha.

Zbytek webu maji na starost sourozene moduly: `elite_vet_team` (`/nas-tym`)
a `elite_vet_calendar` (`/rozpis-lekaru`).

## Jazyky

**Zdrojovy jazyk sablon je anglictina.** Cestina, nemcina a rustina jsou
preklady v `i18n/*.po`. Ma to jediny duvod: Odoo drzi zdroj ve slotu `en_US`
a paruje podle nej vsechny ostatni jazyky. Kdyz je v sablone anglictina,
uprava textu meni jen zdroj a preklady zustanou. Kdyby tam byla cestina,
kazda uprava by rozbila klic vsem jazykum naraz.

Po zmene textu v sablone:

```bash
# 1. nahrat sablonu i preklady do databaze
# --i18n-overwrite je nutne: bez nej Odoo nechá stary preklad, ktery uz v databazi je
odoo -c /etc/odoo/odoo.conf -d elitevet -u elite_vet_web --i18n-overwrite --stop-after-init --no-http
# 2. vyexportovat aktualni klice
odoo -c /etc/odoo/odoo.conf -d elitevet --i18n-export=/tmp/ev.pot \
     --modules=elite_vet_web --stop-after-init --no-http
# 3. do i18n/*.po doplnit preklad noveho terminu a znovu spustit krok 1
```

Hlaseni „nacitame rezervacni system" a odkaz na rozpis sluzeb se **neprekladaji
pres PO**, ale maji jazykove varianty primo v sablone. Lezi pod iframem, takze
je Odoo Translate neukaze a nikdo by se na ne neproklikal. Novy jazyk = novy
radek ve slovniku v `views/rezervace.xml`.

## Obrazky

Jsou to staticke soubory v `static/src/img`, ne prilohy v databazi. Stranka tim
prestala viset na ID priloh, ktere se na kazde instalaci lisi. Fotky galerie
jsou ve dvou velikostech (`N.jpg` sirka 500, `N-420.jpg` pro mobil), protoze
u statickych souboru nefunguje resizer Odoo.

Vymena fotky = vymena souboru v modulu a upgrade.

**Po nasazeni je nutny restart kontejneru**, ne jen upgrade — Odoo si mapu
statickych souboru stavi pri startu a do restartu by fotky hazely 404.

## Nasazeni

Cely postup na jeden zatah je v `nasazeni/README.md` — vcetne prekladu obsahu
(texty lekarek, typy smen) a kontrolniho skriptu.

## Domovska stranka

`post_init_hook` (`_nastav_homepage`) prepne stranku `website.homepage_page`
na sablonu tohohle modulu. Vlastni stranka na `/` se zamerne nezaklada: dve
stranky na stejne adrese znamenaji, ze si obsluha `/` vybere tu spatnou a misto
homepage presmeruje na prvni polozku menu.

Hook saha **jen na obecnou stranku Odoo**. Databaze muze hostit vic webu a
prepnout homepage vsem by znamenalo prepsat cizi weby. **Pokud ma web vlastni
stranku `/` (na ostrem webu Elite Vet ji ma), je potreba ji po instalaci rucne
prepnout na pohled `elite_vet_web.homepage`** — SEO pole zustanou na jejim
zaznamu.
