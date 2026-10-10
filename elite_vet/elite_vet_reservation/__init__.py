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


def _seed_settings(env):
    env["elite.vet.setting"].nastaveni().write({
        "booking_slot_step": 15, "booking_min_hours_before": 24, "booking_max_days_ahead": 60,
        "booking_cancel_hours_before": 12, "booking_notify_email": "info@elite-vet.cz",
    })
