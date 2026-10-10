"""Zalozeni vychoziho obsahu pri prvni instalaci.

Obsah je v ``data/vychozi-obsah.json`` a pochazi z toho, co na webu opravdu
bylo — vcetne prekladu do vsech ctyr jazyku. Zaklada se jen jednou; od te chvile
patri obsah klinice a upgrade modulu do nej uz nesaha.

Zdrojovy jazyk je anglictina (slot ``en_US``), cestina, nemcina a rustina se
dopisuji jako preklad. Poradi je dulezite: kdyby se zapsala nejdriv cestina,
anglicky text by prepsal zdroj a cestina by ho zdedila.
"""

import base64
import json
import logging
import os

_logger = logging.getLogger(__name__)

SLOZKA = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JAZYKY = ("cs_CZ", "de_DE", "ru_RU")


def _nacti_obsah():
    cesta = os.path.join(SLOZKA, "data", "vychozi-obsah.json")
    with open(cesta, encoding="utf-8") as soubor:
        return json.load(soubor)


def _nainstalovane_jazyky(env):
    """Kody jazyku, ktere databaze opravdu zna.

    Zapis prekladu do jazyka, ktery nainstalovany neni, Odoo odmitne
    hlaskou "Invalid language code" a shodi celou instalaci modulu.
    """
    return set(env["res.lang"].search([("active", "=", True)]).mapped("code"))


def _zapis_preklady(zaznam, pole, hodnoty):
    """Zapise anglicky zdroj a pak preklady do jazyku, ktere databaze zna."""
    if not hodnoty:
        return
    anglicky = hodnoty.get("en_US")
    if anglicky:
        zaznam.with_context(lang="en_US")[pole] = anglicky
    jazyky = _nainstalovane_jazyky(zaznam.env)
    for jazyk in JAZYKY:
        text = hodnoty.get(jazyk)
        if text and jazyk in jazyky:
            zaznam.with_context(lang=jazyk)[pole] = text


def seed_galerie(env):
    """Nahraje fotky ze statickych souboru modulu do galerie."""
    Foto = env["elite.vet.gallery.photo"]
    if Foto.search_count([]):
        return
    slozka = os.path.join(SLOZKA, "static", "src", "img", "galerie")
    if not os.path.isdir(slozka):
        return
    # soubory se jmenuji cislem, radime tedy cisly a ne abecedne (10 pred 2)
    soubory = sorted(
        (s for s in os.listdir(slozka) if s.endswith(".jpg") and "-420" not in s),
        key=lambda s: int(s.split(".")[0]),
    )
    for poradi, soubor in enumerate(soubory, start=1):
        with open(os.path.join(slozka, soubor), "rb") as obrazek:
            Foto.create({
                "name": "Elite Vet Karlovy Vary",
                "image": base64.b64encode(obrazek.read()),
                "sequence": poradi * 10,
            })
    _logger.info("Elite Vet: zalozeno %s fotek galerie", len(soubory))


def seed_obsah(env):
    """Hodiny, kontakty, caste dotazy, cenik a nastaveni."""
    obsah = _nacti_obsah()

    Hodiny = env["elite.vet.opening.hours"]
    if not Hodiny.search_count([]):
        for radek in obsah["hodiny"]:
            zaznam = Hodiny.create({
                "name": radek["dny"].get("en_US", ""),
                "time_text": radek["cas"].get("en_US", ""),
                "sequence": radek["poradi"],
            })
            _zapis_preklady(zaznam, "name", radek["dny"])
            _zapis_preklady(zaznam, "time_text", radek["cas"])

    Kontakt = env["elite.vet.contact"]
    if not Kontakt.search_count([]):
        for radek in obsah["kontakty"]:
            zaznam = Kontakt.create({
                "name": radek["nadpis"].get("en_US", ""),
                "value": radek["hodnota"].get("en_US", ""),
                "value2": radek["hodnota2"].get("en_US", ""),
                "note": radek["poznamka"].get("en_US", ""),
                "url": radek["odkaz"],
                "icon_code": radek["ikona"],
                "sequence": radek["poradi"],
            })
            for pole, klic in (("name", "nadpis"), ("value", "hodnota"),
                               ("value2", "hodnota2"), ("note", "poznamka")):
                _zapis_preklady(zaznam, pole, radek[klic])

    Dotaz = env["elite.vet.faq"]
    if not Dotaz.search_count([]):
        for radek in obsah["dotazy"]:
            zaznam = Dotaz.create({
                "name": radek["otazka"].get("en_US", ""),
                "answer": radek["odpoved"].get("en_US", ""),
                "sequence": radek["poradi"],
            })
            _zapis_preklady(zaznam, "name", radek["otazka"])
            _zapis_preklady(zaznam, "answer", radek["odpoved"])

    # Ukony ceniku zaklada _nastav_cenik z data/cenik.json — i se sekcemi,
    # do kterych patri. Tady uz by vznikly podruhe, a jeste bez sekce.
    Nastaveni = env["elite.vet.setting"]
    if not Nastaveni.search_count([]):
        hodnoty = dict(obsah["nastaveni"])
        # Ramecek pod uvodni sekci je Html s translate=True. Takove pole se
        # preklada po terminech, takze zdroj musi byt uz v create() — jinak
        # ho prvni zapis v cizim jazyce prepise.
        ramecek = obsah.get("hero_note") or {}
        if ramecek.get("en_US"):
            hodnoty["hero_note"] = ramecek["en_US"]
        zaznam = Nastaveni.create(hodnoty)
        if ramecek:
            _zapis_preklady(zaznam, "hero_note", ramecek)

    seed_druhy(env)
    seed_bloky(env)
    seed_texty_rezervace(env)


# Texty kolem rezervacniho systemu. Lezi pod iframem, takze je prekladovy rezim
# Odoo neukaze — jako pole zaznamu se ale prekladaji bezne.
TEXTY_REZERVACE = {
    "booking_loading_title": {
        "en_US": "Loading the booking system…", "cs_CZ": "Načítáme rezervační systém…",
        "de_DE": "Reservierungssystem wird geladen…", "ru_RU": "Загружаем систему бронирования…"},
    "booking_loading_note": {
        "en_US": "It takes a moment, thank you for your patience.",
        "cs_CZ": "Chvilku to trvá, děkujeme za trpělivost.",
        "de_DE": "Es dauert einen Moment, danke für Ihre Geduld.",
        "ru_RU": "Это займёт минуту, спасибо за терпение."},
    "schedule_link_lead": {
        "en_US": "Not sure which vet to book with?",
        "cs_CZ": "Nevíte, ke kterému lékaři se objednat?",
        "de_DE": "Sie wissen nicht, bei welchem Arzt Sie buchen sollen?",
        "ru_RU": "Не знаете, к какому врачу записаться?"},
    "schedule_link_button": {
        "en_US": "View the duty schedule", "cs_CZ": "Zobrazit rozpis služeb",
        "de_DE": "Dienstplan ansehen", "ru_RU": "Посмотреть график работы"},
}


def seed_texty_rezervace(env):
    zaznam = env["elite.vet.setting"].nastaveni()
    nainstalovane = _nainstalovane_jazyky(env)
    if zaznam.with_context(lang="en_US").booking_loading_title:
        return
    for pole, jazyky in TEXTY_REZERVACE.items():
        zaznam.with_context(lang="en_US")[pole] = jazyky["en_US"]
        for jazyk in JAZYKY:
            if jazyk in nainstalovane:
                zaznam.with_context(lang=jazyk)[pole] = jazyky[jazyk]


# Koho klinika prijima. Zdroj anglicky, preklady hned u toho.
DRUHY = [
    ("pes", 10, "Dogs", "Psi", "Hunde", "Собаки"),
    ("kocka", 20, "Cats", "Kočky", "Katzen", "Кошки"),
    ("savec", 30, "Small mammals", "Drobní savci", "Kleinsäuger", "Мелкие млекопитающие"),
]


def seed_druhy(env):
    Druh = env["elite.vet.species"]
    if Druh.search_count([]):
        return
    nainstalovane = _nainstalovane_jazyky(env)
    for kod, poradi, en, cs, de, ru in DRUHY:
        zaznam = Druh.create({"name": en, "icon_code": kod, "sequence": poradi})
        for jazyk, text in (("cs_CZ", cs), ("de_DE", de), ("ru_RU", ru)):
            if jazyk in nainstalovane:
                zaznam.with_context(lang=jazyk).name = text


# Obsahove bloky domovske stranky v zakladnim poradi. Kdyz tu nejaky chybi,
# na strance se vubec nevykresli — proto se zakladaji vsechny.
BLOKY = [
    ("letak", 10, "elite_vet_web.sekce_letak",
     ("Leták s otevírací dobou", "Flyer with opening hours", "Flyer mit Öffnungszeiten", "Листовка с часами работы"),
     ("Úvodní leták s logem a otevírací dobou", "Opening flyer with logo and hours",
      "Eröffnungsflyer mit Logo und Zeiten", "Вступительная листовка с логотипом и часами")),
    ("objednat", 20, "elite_vet_web.sekce_objednat",
     ("Tlačítko Objednat se", "Book an appointment button", "Schaltfläche Termin buchen", "Кнопка записи"),
     ("Zelené tlačítko pod letákem", "Green button under the flyer",
      "Grüne Schaltfläche unter dem Flyer", "Зелёная кнопка под листовкой")),
    ("o_klinice", 30, "elite_vet_web.sekce_o_klinice",
     ("O klinice a galerie", "About the clinic and gallery", "Über die Klinik und Galerie", "О клинике и галерея"),
     ("Text o klinice, karta s fotkou recepce a pás fotek", "Text about the clinic, reception photo and photo strip",
      "Text über die Klinik, Rezeptionsfoto und Fotoleiste", "Текст о клинике, фото ресепшна и лента фотографий")),
    ("sluzby", 40, "elite_vet_web.sekce_sluzby",
     ("Služby", "Services", "Leistungen", "Услуги"),
     ("Koho přijímáme a seznam služeb", "Who we treat and the list of services",
      "Wen wir behandeln und die Leistungsliste", "Кого принимаем и список услуг")),
    ("tym", 50, "elite_vet_web.sekce_tym",
     ("Pozvánka na náš tým", "Invitation to our team", "Einladung zu unserem Team", "Приглашение к команде"),
     ("Tmavá karta s odkazem na stránku týmu", "Dark card linking to the team page",
      "Dunkle Karte mit Link zur Teamseite", "Тёмная карточка со ссылкой на команду")),
    ("kontakt", 60, "elite_vet_web.sekce_kontakt",
     ("Kontakt, hodiny a mapa", "Contact, hours and map", "Kontakt, Zeiten und Karte", "Контакты, часы и карта"),
     ("Kontaktní karty, ordinační hodiny a mapa", "Contact cards, opening hours and map",
      "Kontaktkarten, Öffnungszeiten und Karte", "Контактные карточки, часы работы и карта")),
]


def seed_bloky(env):
    nainstalovane = _nainstalovane_jazyky(env)
    Blok = env["elite.vet.page.section"]
    if Blok.with_context(active_test=False).search_count([]):
        return
    for kod, poradi, sablona, nazvy, popisy in BLOKY:
        cs, en, de, ru = nazvy
        pcs, pen, pde, pru = popisy
        zaznam = Blok.create({
            "name": en, "note": pen, "page": "homepage",
            "qweb_template": sablona, "sequence": poradi,
        })
        for jazyk, nazev, popis in (("cs_CZ", cs, pcs), ("de_DE", de, pde), ("ru_RU", ru, pru)):
            if jazyk not in nainstalovane:
                continue
            zaznam.with_context(lang=jazyk).name = nazev
            zaznam.with_context(lang=jazyk).note = popis
