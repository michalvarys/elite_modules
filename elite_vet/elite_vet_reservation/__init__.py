import logging

_logger = logging.getLogger(__name__)

from . import models
from . import controllers

# (název EN, český překlad, délka, zkratka, barva)
PROCEDURES = [
    ("Vaccination", "Vakcinace", 15, "V", "green"),
    ("Clinical examination – check-up", "Klinické vyšetření – kontrola", 30, "k", "teal"),
    ("Clinical examination – healthy pet", "Klinické vyšetření – zdravé zvíře", 30, "Z", "teal"),
    ("Clinical examination – health problem", "Klinické vyšetření – zdravotní problém", 45, "P", "blue"),
    ("Dental examination", "Stomatologické vyšetření", 30, "S", "purple"),
    ("Blood sampling (fasting 8–12 h)", "Odběr krve – nalačno 8–12 hodin", 30, "O", "orange"),
    ("Diarrhoea / vomiting", "Průjem / zvracení", 45, "G", "blue"),
    ("Cough / breathing problem", "Kašel / problém s dýcháním", 45, "R", "blue"),
    ("Claws / glands", "Drápky / žlázky", 15, "D", "green"),
    ("Pre-operative examination", "Předoperační vyšetření", 30, "PO", "orange"),
    ("Castration – tomcat", "Kastrace kocour", 45, "KA", "pink"),
    ("Injury", "Úraz", 45, "U", "red"),
    ("Urination problem", "Problém s močením", 45, "M", "blue"),
    ("Food intake problem", "Problém s příjmem potravy", 45, "J", "blue"),
    ("Dermatological problem", "Dermatologický problém", 30, "DE", "blue"),
    ("Ultrasound / X-ray examination", "USG / RTG vyšetření", 45, "X", "purple"),
    ("Mobility problem", "Problém s pohyblivostí", 45, "H", "blue"),
    ("Ear problem", "Problém s ušima", 45, "E", "blue"),
    ("Eye problem", "Problém s očima", 45, "Q", "blue"),
    ("Skin lump / tumour", "Bulka / nádor", 45, "N", "red"),
    ("Other", "Jiné", 30, "?", "grey"),
]


# Německé a ruské názvy výchozích úkonů (čeština je ve PROCEDURES). Záznamy nejsou
# v XML, proto je .po soubory nepokryjí; překládají se při seedu, pokud je jazyk nainstalovaný.
PROCEDURES_I18N = {
    "Vaccination": {"de_DE": "Impfung", "ru_RU": "Вакцинация"},
    "Clinical examination – check-up": {"de_DE": "Klinische Untersuchung – Kontrolle", "ru_RU": "Клинический осмотр – контроль"},
    "Clinical examination – healthy pet": {"de_DE": "Klinische Untersuchung – gesundes Tier", "ru_RU": "Клинический осмотр – здоровое животное"},
    "Clinical examination – health problem": {"de_DE": "Klinische Untersuchung – Gesundheitsproblem", "ru_RU": "Клинический осмотр – проблема со здоровьем"},
    "Dental examination": {"de_DE": "Zahnuntersuchung", "ru_RU": "Стоматологический осмотр"},
    "Blood sampling (fasting 8–12 h)": {"de_DE": "Blutentnahme (nüchtern, 8–12 Stunden)", "ru_RU": "Забор крови (натощак, 8–12 часов)"},
    "Diarrhoea / vomiting": {"de_DE": "Durchfall / Erbrechen", "ru_RU": "Диарея / рвота"},
    "Cough / breathing problem": {"de_DE": "Husten / Atemprobleme", "ru_RU": "Кашель / проблемы с дыханием"},
    "Claws / glands": {"de_DE": "Krallen / Drüsen", "ru_RU": "Когти / железы"},
    "Pre-operative examination": {"de_DE": "Voruntersuchung vor der Operation", "ru_RU": "Предоперационный осмотр"},
    "Castration – tomcat": {"de_DE": "Kastration – Kater", "ru_RU": "Кастрация – кот"},
    "Injury": {"de_DE": "Verletzung", "ru_RU": "Травма"},
    "Urination problem": {"de_DE": "Probleme beim Wasserlassen", "ru_RU": "Проблемы с мочеиспусканием"},
    "Food intake problem": {"de_DE": "Probleme bei der Futteraufnahme", "ru_RU": "Проблемы с приёмом пищи"},
    "Dermatological problem": {"de_DE": "Hautproblem", "ru_RU": "Дерматологическая проблема"},
    "Ultrasound / X-ray examination": {"de_DE": "Ultraschall- / Röntgenuntersuchung", "ru_RU": "УЗИ / рентген"},
    "Mobility problem": {"de_DE": "Bewegungsproblem", "ru_RU": "Проблемы с подвижностью"},
    "Ear problem": {"de_DE": "Ohrenproblem", "ru_RU": "Проблема с ушами"},
    "Eye problem": {"de_DE": "Augenproblem", "ru_RU": "Проблема с глазами"},
    "Skin lump / tumour": {"de_DE": "Knoten / Tumor", "ru_RU": "Шишка / опухоль"},
    "Other": {"de_DE": "Sonstiges", "ru_RU": "Другое"},
}


def _pri_instalaci(env):
    """Výchozí ordinace, úkony a hodiny. Jen při prázdném modulu, pak patří klinice."""
    if env["elite.vet.room"].search_count([]):
        return
    _seed_rooms_and_hours(env)
    _seed_procedures(env)
    _seed_settings(env)


def _seed_rooms_and_hours(env):
    Room = env["elite.vet.room"]
    Hours = env["elite.vet.room.hours"]
    rooms = Room.create([
        {"name": "Ordinace 1", "sequence": 10, "color": "teal"},
        {"name": "Ordinace 2", "sequence": 20, "color": "blue"},
        {"name": "Sál", "sequence": 30, "color": "purple", "online": False},
    ])
    # Okna z dnešního widgetu WinVetu: Po-Pá 8:15-19:30, Ne 10:15-17:45, So zavřeno.
    for room in rooms[:2]:
        for wd in range(5):
            Hours.create({"room_id": room.id, "weekday": str(wd), "hour_from": 8.25, "hour_to": 19.5})
        Hours.create({"room_id": room.id, "weekday": "6", "hour_from": 10.25, "hour_to": 17.75})


def _nainstalovane_jazyky(env):
    return set(env["res.lang"].search([("active", "=", True)]).mapped("code"))


def _seed_procedures(env):
    Proc = env["elite.vet.procedure"]
    jazyky = _nainstalovane_jazyky(env)
    for i, (en, cs, minutes, symbol, color) in enumerate(PROCEDURES):
        rec = Proc.create({"name": en, "duration": minutes, "symbol": symbol, "color": color,
                           "sequence": (i + 1) * 10})
        if "cs_CZ" in jazyky:
            rec.with_context(lang="cs_CZ").name = cs
        for lang, name in PROCEDURES_I18N[en].items():
            if lang in jazyky:
                rec.with_context(lang=lang).name = name


def _seed_settings(env):
    env["elite.vet.setting"].nastaveni().write({
        "booking_slot_step": 15, "booking_min_hours_before": 24, "booking_max_days_ahead": 60,
        "booking_cancel_hours_before": 12, "booking_notify_email": "info@elite-vet.cz",
    })
