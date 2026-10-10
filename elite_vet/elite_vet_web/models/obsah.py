from odoo import api, fields, models


class EliteVetGalleryPhoto(models.Model):
    """Fotka kliniky v pasu na domovske strance.

    Driv to byly soubory v modulu, takze vymena fotky znamenala zasah do kodu.
    Ted je to zaznam: klinika nahraje fotku v Odoo a hned je na webu.
    """

    _name = "elite.vet.gallery.photo"
    _description = "Elite Vet - fotka galerie"
    _order = "sequence, id"

    name = fields.Char("Popis fotky", translate=True,
                       help="Ctou ho vyhledavace a ctecky pro nevidome. Kdyz zustane prazdny, doplni se nazev kliniky.")
    image = fields.Image("Fotka", required=True, max_width=1600, max_height=1600)
    sequence = fields.Integer("Pořadí", default=10)
    active = fields.Boolean("Aktivní", default=True)


class EliteVetPageSection(models.Model):
    """Obsahovy blok stranky — leták, služby, galerie, kontakt.

    Zaznam nedrzi obsah, jen poradi a to, jestli se blok ukaze. Samotny obsah je
    v sablone modulu, protoze jde o rozvrzeni a styly, ne o text k prepisovani.
    Klinika tak muze bloky prerovnat nebo vypnout, ale nemuze si rozbit layout.
    """

    _name = "elite.vet.page.section"
    _description = "Elite Vet - blok stránky"
    _order = "page, sequence, id"

    name = fields.Char("Blok", required=True, translate=True)
    page = fields.Selection([("homepage", "Domovská stránka")],
                            string="Stránka", required=True, default="homepage")
    qweb_template = fields.Char("Šablona", required=True, readonly=True,
                                help="Technicky nazev sablony v modulu. Neni na meneni.")
    sequence = fields.Integer("Pořadí", default=10)
    active = fields.Boolean("Zobrazit", default=True,
                            help="Vypnuty blok na webu zmizi, ale zustane v seznamu.")
    note = fields.Char("Co v bloku je", translate=True, readonly=True)

    @api.model
    def bloky_stranky(self, stranka):
        """Bloky pro sablonu. Kdyz zadne nejsou, stranka se vykresli prazdna —
        proto seed zaklada vsechny uz pri instalaci."""
        return self.sudo().search([("page", "=", stranka)])


class EliteVetSpecies(models.Model):
    """Druh zvirete v pasu „koho prijimame“ nad sluzbami."""

    _name = "elite.vet.species"
    _description = "Elite Vet - koho přijímáme"
    _order = "sequence, id"

    name = fields.Char("Název", required=True, translate=True,
                       help="Napriklad „Psi“, „Kocky“, „Drobni savci“.")
    icon_code = fields.Selection(
        selection=[("pes", "Pes"), ("kocka", "Kočka"), ("savec", "Drobný savec")],
        string="Kreslená ikona", default="pes")
    icon_id = fields.Many2one(
        "elite.vet.team.icon", string="Vlastní ikona", ondelete="set null",
        help="Barevný obrázek ze sady ikon. Má přednost před kreslenou ikonou.")
    icon_image = fields.Image("Náhled", related="icon_id.image", readonly=True)
    sequence = fields.Integer("Pořadí", default=10)
    active = fields.Boolean("Aktivní", default=True)


class EliteVetOpeningHours(models.Model):
    """Radek v tabulce ordinacnich hodin."""

    _name = "elite.vet.opening.hours"
    _description = "Elite Vet - ordinační hodiny"
    _order = "sequence, id"

    name = fields.Char("Dny", required=True, translate=True,
                       help="Napriklad „Pondeli – Patek“.")
    time_text = fields.Char("Čas", translate=True,
                            help="Napriklad „8:00 – 20:00“. U zavreneho dne nech prazdne.")
    # Letak nad strankou ma malo mista, proto zkracena podoba. Kdyz zustane
    # prazdna, pouzije se dlouha — radek tim nikdy nezmizi.
    name_short = fields.Char("Dny zkráceně", translate=True,
                             help="Pro leták nahoře, kde je málo místa. Napriklad „Po–Pá“.")
    time_short = fields.Char("Čas zkráceně", translate=True,
                             help="Napriklad „8–20“.")

    def dny(self):
        """Zkracene dny, nebo dlouhe, kdyz zkracene nikdo nevyplnil."""
        self.ensure_one()
        return self.name_short or self.name

    def cas(self):
        """Zkraceny cas, nebo dlouhy."""
        self.ensure_one()
        return self.time_short or self.time_text or ""
    is_closed = fields.Boolean("Zavřeno",
                               help="Misto casu se cervene vypise text z pole Čas, nebo „Zavřeno“.")
    sequence = fields.Integer("Pořadí", default=10)
    active = fields.Boolean("Aktivní", default=True)


class EliteVetContact(models.Model):
    """Kontaktni kartička v sekci Kontakt."""

    _name = "elite.vet.contact"
    _description = "Elite Vet - kontaktní karta"
    _order = "sequence, id"

    name = fields.Char("Nadpis", required=True, translate=True,
                       help="Maly nadpis nad hodnotou, napriklad „Adresa“.")
    value = fields.Char("Hodnota", required=True, translate=True,
                        help="Co se ukaze velkym pismem: adresa, cislo, e-mail.")
    value2 = fields.Char("Druhý řádek", translate=True,
                         help="Nepovinne pokracovani hodnoty, napriklad druhy radek adresy.")
    note = fields.Char("Poznámka pod hodnotou", translate=True)
    url = fields.Char("Odkaz",
                      help="Kam karta vede. Telefon jako tel:+420…, e-mail jako mailto:…")
    icon_code = fields.Selection(
        selection=[("adresa", "Adresa (špendlík)"), ("telefon", "Telefon (sluchátko)"),
                   ("email", "E-mail (obálka)")],
        string="Ikona", default="adresa", required=True)
    sequence = fields.Integer("Pořadí", default=10)
    active = fields.Boolean("Aktivní", default=True)


class EliteVetFaq(models.Model):
    """Casty dotaz. Zatim se vypisuji na strance rezervace."""

    _name = "elite.vet.faq"
    _description = "Elite Vet - častý dotaz"
    _order = "sequence, id"

    name = fields.Char("Otázka", required=True, translate=True)
    answer = fields.Html("Odpověď", required=True, translate=True, sanitize=False)
    sequence = fields.Integer("Pořadí", default=10)
    active = fields.Boolean("Aktivní", default=True)


class EliteVetPriceCategory(models.Model):
    """Jedna sekce stranky /cenik.

    Sekce je cely blok, tak jak ho clovek vidi na strance: stitek, nadpis,
    popisek, obrazek, tabulka ukonu a komentar pod ni. Zamerne je to jeden
    zaznam s jednim formularem — klinika ma jedno misto, kde meni vsechno.
    """

    _name = "elite.vet.price.category"
    _description = "Elite Vet - sekce ceníku"
    _order = "sequence, id"

    # Hlavicka stranky a bezna sekce se lisi jen podobou: hlavicka ma velky
    # nadpis na stred a stoji na strance jednou nahore, sekce mensi nadpis vlevo
    # s linkou. Zamerne je to pole, ne poradi — poradi se da prehodit omylem.
    typ = fields.Selection(
        selection=[("hlavicka", "Hlavička stránky"), ("sekce", "Sekce")],
        string="Typ", default="sekce", required=True,
        help="Hlavička stojí nahoře a má velký nadpis na střed. Sekce má menší "
             "nadpis vlevo a linku vedle něj. Hlavička se dělá jen jedna.")
    badge = fields.Char(
        "Štítek", translate=True,
        help="Malý nápis v rámečku nad nadpisem, například „CENÍK“. "
             "Nechat prázdné je v pořádku.")
    name = fields.Char(
        "Nadpis", required=True, translate=True,
        help="Velký nadpis sekce. U první sekce je to zároveň nadpis stránky.")
    description = fields.Text(
        "Popisek pod nadpisem", translate=True,
        help="Jedna dvě věty pod nadpisem. Nechat prázdné je v pořádku.")
    image = fields.Image(
        "Obrázek", max_width=1600, max_height=1200,
        help="Nepovinná fotka nad tabulkou úkonů. Bez ní se nic nevykreslí.")
    image_alt = fields.Char(
        "Popis obrázku", translate=True,
        help="Co je na fotce. Čte to Google a hlasové čtečky.")
    comment = fields.Html(
        "Komentář pod sekcí", translate=True, sanitize=False,
        help="Rámeček s doplňující informací pod tabulkou. Může mít víc odstavců.")
    sequence = fields.Integer("Pořadí", default=10)
    active = fields.Boolean("Aktivní", default=True)
    item_ids = fields.One2many("elite.vet.price.item", "category_id", string="Úkony")
    pocet_ukonu = fields.Integer("Úkonů", compute="_compute_pocet_ukonu")

    @api.depends("item_ids")
    def _compute_pocet_ukonu(self):
        for zaznam in self:
            zaznam.pocet_ukonu = len(zaznam.item_ids)

class EliteVetPriceItem(models.Model):
    """Jeden radek ceniku."""

    _name = "elite.vet.price.item"
    _description = "Elite Vet - položka ceníku"
    _order = "sequence, id"

    name = fields.Char("Úkon", required=True, translate=True)
    category_id = fields.Many2one("elite.vet.price.category", string="Skupina",
                                  ondelete="cascade")
    price = fields.Char("Cena", required=True, translate=True,
                        help="Pise se vcetne meny, napriklad „590 Kc“. Je to text, aby slo napsat i „dohodou“.")
    price_from = fields.Boolean("Cena od", default=True,
                                help="Pred cenu se pripise „od“.")
    note = fields.Char("Poznámka", translate=True)
    icon_code = fields.Selection(
        selection=[("kocka", "Kočka"), ("pes", "Pes"), ("kralik", "Králík"),
                   ("nuzky", "Nůžky"), ("kapka", "Kapka"), ("stetoskop", "Stetoskop")],
        string="Kreslená ikona", default="stetoskop")
    icon_id = fields.Many2one(
        "elite.vet.team.icon", string="Vlastní ikona", ondelete="set null",
        help="Barevný obrázek ze sady ikon. Má přednost před kreslenou ikonou.")
    icon_image = fields.Image("Náhled", related="icon_id.image", readonly=True)
    sequence = fields.Integer("Pořadí", default=10)
    active = fields.Boolean("Aktivní", default=True)


class EliteVetSetting(models.Model):
    """Udaje, ktere se opakuji na vic strankach: telefon, adresa, odkazy.

    Zamerne je to jeden zaznam, ne pole roztrousena po sablonach — kdyz klinika
    zmeni telefon, meni ho na jednom miste a projevi se vsude.
    """

    _name = "elite.vet.setting"
    _description = "Elite Vet - nastavení webu"

    name = fields.Char("Označení", default="Nastavení webu")
    # Klinika ma tri linky a kazda patri jinam. Drzi se pohromade, aby se cislo
    # menilo na jednom miste a propsalo se vsude, kde na webu je.
    phone = fields.Char("Telefon na recepci", help="Ve tvaru +420722599699, bez mezer.")
    phone_display = fields.Char("Recepce jak se zobrazí", help="Napriklad +420 722 599 699.")
    email = fields.Char("E-mail")
    hr_phone = fields.Char("Telefon pro uchazeče",
                           help="Linka pro zajemce o praci. Ukazuje se na strance tymu.")
    hr_phone_display = fields.Char("Uchazeči jak se zobrazí")
    hr_email = fields.Char("E-mail pro uchazeče")
    address_line1 = fields.Char("Adresa – první řádek")
    address_line2 = fields.Char("Adresa – druhý řádek")
    map_url = fields.Char("Odkaz na mapu")
    # Ramecek pod uvodni sekci domovske stranky. Klinika v nem vysvetluje
    # priplatky mimo ordinacni dobu, vcetne odkazu na cenik — proto Html,
    # ne prosty text. Prazdne pole znamena, ze se ramecek nevykresli.
    hero_note = fields.Html(
        "Rámeček pod úvodní sekcí", translate=True, sanitize=False,
        help="Ukáže se na domovské stránce pod úvodním blokem, nad tlačítkem "
             "Objednat se. Prázdné pole znamená, že tam nic nebude.")
    booking_url = fields.Char("Odkaz na rezervační systém",
                              help="Adresa formulare WinVet, ktera se vklada do stranky.")
    # Hlaseni lezi POD iframem, takze se na nej v prekladovem rezimu Odoo neda
    # kliknout. Jako pole zaznamu se ale preklada uplne bezne.
    booking_loading_title = fields.Char(
        "Hláška při načítání", translate=True,
        help="Ukaze se pod rámečkem, dokud se rezervační systém nenačte.")
    booking_loading_note = fields.Char("Druhý řádek hlášky", translate=True)
    # Treti hlaska lezi niz, v prazdnem miste pod prvnimi dvema, a je v nem
    # vycentrovana. Je na delsi text — proto Text, ne Char.
    booking_loading_middle = fields.Text(
        "Text uprostřed rámečku", translate=True,
        help="Delší text ve volném místě pod hláškou o načítání. "
             "Prázdné pole znamená, že tam nic nebude.")
    schedule_link_lead = fields.Char(
        "Text nad odkazem na rozpis", translate=True,
        help="Věta nad tlačítkem pod rezervačním systémem.")
    schedule_link_button = fields.Char("Tlačítko na rozpis služeb", translate=True)
    instagram_url = fields.Char("Instagram")
    facebook_url = fields.Char("Facebook")

    # Pohotovost 24/7 ma tri stavy, ne dva. Puvodni "vypnuto" totiz porad
    # slibovalo — sede tlacitko "Volat jiz brzy", blikajici kolecko vpravo dole
    # a veta, ze linku brzy spustime. Klienti to cetli tak, ze pohotovost uz
    # bezi, a volali mimo ordinacni dobu. Stav "hidden" proto linku z webu
    # odstrani uplne a je vychozi.
    emergency_mode = fields.Selection(
        [("hidden", "Vůbec neukazovat"),
         ("soon", "Ukazovat jako „již brzy“"),
         ("live", "Linka běží — ukázat číslo")],
        string="Pohotovostní linka 24/7", required=True, default="hidden",
        help="Vůbec neukazovat = na webu po lince nezůstane ani stopa. "
             "Již brzy = šedé neklikací tlačítko a věta, že ji teprve spustíme. "
             "Linka běží = zelené tlačítko s telefonním číslem.")
    emergency_phone = fields.Char(
        "Pohotovostní telefon",
        help="Ve tvaru +420722599699, bez mezer. Bez něj se pohotovost nezapne ani zaškrtnutím.")
    emergency_phone_display = fields.Char(
        "Pohotovostní telefon jak se zobrazí",
        help="Napriklad +420 722 599 699.")

    # Co se na webu pise, dokud pohotovost nebezi. Prazdne pole znamena
    # "nech puvodni vetu ze sablony" — ta je prelozena do vsech ctyr jazyku.
    # Pozor: prvni zapis naplni i zdroj en_US, takze vetu prevezmou i jazyky,
    # ktere jeste vlastni preklad nemaji. Proto se text dopisuje ve vsech
    # ctyrech jazycich, ne jen cesky.
    emergency_off_button = fields.Char(
        "Nápis na šedém tlačítku", translate=True,
        help="Co stojí na neklikacím tlačítku v bublině 24/7. Prázdné = „Volat již brzy“.")
    emergency_off_text = fields.Text(
        "Text v bublině 24/7", translate=True,
        help="Odstavec v bublině vpravo dole, dokud pohotovost neběží. "
             "Prázdné = původní věta o tom, že linku teprve spustíme.")
    emergency_off_note = fields.Text(
        "Věta pod ordinačními hodinami", translate=True,
        help="Poznámka pod tabulkou ordinačních hodin v sekci Kontakt. "
             "Prázdné = původní věta ze šablony.")

    @api.depends("emergency_mode", "emergency_phone")
    def _compute_emergency_live(self):
        for zaznam in self:
            zaznam.emergency_live = bool(
                zaznam.emergency_mode == "live" and zaznam.emergency_phone)

    emergency_live = fields.Boolean(
        "Pohotovost je na webu aktivní", compute="_compute_emergency_live",
        help="Režim „linka běží“ a k tomu vyplněné číslo. Web se tímhle polem řídí.")

    @api.depends("emergency_mode")
    def _compute_emergency_show(self):
        for zaznam in self:
            zaznam.emergency_show = zaznam.emergency_mode != "hidden"

    emergency_show = fields.Boolean(
        "Linka je na webu vidět", compute="_compute_emergency_show",
        help="Vypnuté znamená, že se o pohotovosti nikde nepíše.")

    @api.model
    def nastaveni(self):
        """Vrati jediny zaznam nastaveni; kdyz zadny neni, zalozi prazdny."""
        zaznam = self.sudo().search([], limit=1)
        if not zaznam:
            zaznam = self.sudo().create({})
        return zaznam

    @api.model
    def otevrit_rezervaci(self):
        """Nastaveni rezervace ve vlastnim formulari, at se v nem klinika neztrati."""
        return {
            "type": "ir.actions.act_window",
            "name": "Nastavení rezervace",
            "res_model": self._name,
            "res_id": self.nastaveni().id,
            "view_mode": "form",
            "views": [(self.env.ref("elite_vet_web.view_setting_rezervace_form").id, "form")],
            "target": "current",
            "context": {"create": False, "delete": False},
        }

    @api.model
    def otevrit_nastaveni(self):
        """Otevre ten jediny zaznam, ne prazdny formular.

        Bez tohohle by nabidka otevirala nove nastaveni a klinika by si omylem
        zalozila druhe, ze ktereho by web nic nebral.
        """
        return {
            "type": "ir.actions.act_window",
            "name": "Nastavení webu",
            "res_model": self._name,
            "res_id": self.nastaveni().id,
            "view_mode": "form",
            "target": "current",
            "context": {"create": False, "delete": False},
        }
