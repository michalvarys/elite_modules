import logging

_logger = logging.getLogger(__name__)

from . import models
from . import controllers
from . import wizard

# (English name, Czech translation, duration, symbol, color)
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


# German and Russian names of the default procedures (Czech is in PROCEDURES). The records
# are not in XML, so .po files do not cover them; they are translated during seeding if the
# language is installed.
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


# Procedures done only by a doctor with the given specialization (xml ids from elite_vet_team).
# Any doctor can do the other procedures.
PROCEDURE_SPECS = {
    "Dental examination": ["elite_vet_team.spec_stomatologie"],
    "Eye problem": ["elite_vet_team.spec_oftalmologie"],
    "Ultrasound / X-ray examination": ["elite_vet_team.spec_sonografie"],
    "Castration – tomcat": ["elite_vet_team.spec_chirurgie"],
    "Skin lump / tumour": ["elite_vet_team.spec_chirurgie"],
}


def _post_init(env):
    """Link doctors to team cards; seed default rooms, procedures and hours only into an empty module."""
    _link_doctors(env)
    env["elite.vet.doctor"].with_context(active_test=False).search([]).fill_calendar_colors()
    move_foreign_menus(env)
    if env["elite.vet.room"].search_count([]):
        return
    _seed_rooms_and_hours(env)
    _seed_procedures(env)
    _seed_settings(env)


# elite_vet_web menus that belong under Configuration: (xml id, sequence).
FOREIGN_MENUS_TO_CONFIG = [
    ("elite_vet_web.menu_rezervace_nastaveni", 40),
    ("elite_vet_web.menu_rezervace_faq", 50),
]


def move_foreign_menus(env):
    """Move the booking settings and FAQ menus (from elite_vet_web) under Configuration.

    The data records in views/menus.xml do the same, but a standalone
    `-u elite_vet_web` puts the menus back under the Reservations root. After upgrading
    elite_vet_web alone, `-u elite_vet_reservation` restores the move (both the data
    and this function, called from post_init_hook and migration 18.0.1.3.0).
    """
    config = env.ref("elite_vet_reservation.menu_reservation_config", raise_if_not_found=False)
    if not config:
        return
    for xmlid, sequence in FOREIGN_MENUS_TO_CONFIG:
        menu = env.ref(xmlid, raise_if_not_found=False)
        if menu and (menu.parent_id != config or menu.sequence != sequence):
            menu.write({"parent_id": config.id, "sequence": sequence})


def _link_doctors(env):
    """Doctors from the shift roster get their team card (matched by name), so their
    specializations become available, and the "accepts bookings" flag.

    At install time, anyone with the MVDr. title counts as a doctor - in the clinic's
    team exactly the veterinarians have it. The clinic adjusts it manually afterwards.
    """
    Doctor = env["elite.vet.doctor"].with_context(active_test=False)
    Member = env["elite.vet.team.member"].with_context(active_test=False)
    for doctor in Doctor.search([("member_id", "=", False)]):
        member = Member.search([("name", "=", doctor.name)], limit=1)
        if member:
            doctor.member_id = member
    if not Doctor.search_count([("accepts_bookings", "=", True)]):
        Doctor.search([("name", "=like", "MVDr.%")]).write({"accepts_bookings": True})


def _seed_rooms_and_hours(env):
    Room = env["elite.vet.room"]
    Hours = env["elite.vet.room.hours"]
    rooms = Room.create([
        {"name": "Ordinace 1", "sequence": 10, "color": "teal"},
        {"name": "Ordinace 2", "sequence": 20, "color": "blue"},
        {"name": "Sál", "sequence": 30, "color": "purple", "online": False},
    ])
    # Hours from the current WinVet widget: Mon-Fri 8:15-19:30, Sun 10:15-17:45, Sat closed.
    for room in rooms[:2]:
        for wd in range(5):
            Hours.create({"room_id": room.id, "weekday": str(wd), "hour_from": 8.25, "hour_to": 19.5})
        Hours.create({"room_id": room.id, "weekday": "6", "hour_from": 10.25, "hour_to": 17.75})


def _installed_langs(env):
    return set(env["res.lang"].search([("active", "=", True)]).mapped("code"))


def _seed_procedures(env):
    Proc = env["elite.vet.procedure"]
    langs = _installed_langs(env)
    for i, (en, cs, minutes, symbol, color) in enumerate(PROCEDURES):
        rec = Proc.create({"name": en, "duration": minutes, "symbol": symbol, "color": color,
                           "sequence": (i + 1) * 10})
        if "cs_CZ" in langs:
            rec.with_context(lang="cs_CZ").name = cs
        for lang, name in PROCEDURES_I18N.get(en, {}).items():
            if lang in langs:
                rec.with_context(lang=lang).name = name
        specs = [env.ref(x, raise_if_not_found=False) for x in PROCEDURE_SPECS.get(en, [])]
        specs = [s for s in specs if s]
        if specs:
            rec.specialization_ids = [(6, 0, [s.id for s in specs])]


def _seed_settings(env):
    env["elite.vet.setting"].nastaveni().write({
        "booking_slot_step": 15, "booking_min_hours_before": 24, "booking_max_days_ahead": 60,
        "booking_cancel_hours_before": 12, "booking_notify_email": "info@elite-vet.cz",
    })
