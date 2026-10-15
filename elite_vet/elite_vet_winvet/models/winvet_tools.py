"""Pure helpers shared by the sync engine (no ORM access)."""
import re
import unicodedata
from datetime import date, datetime

import pytz

ENTITIES = [
    "users", "items", "owners", "contacts", "patients",
    "vaccinations", "visits", "sale_documents", "sale_lines", "payments",
]

PRAGUE = pytz.timezone("Europe/Prague")

# Academic and professional titles ignored when matching WinVet users to doctors.
TITLES = {
    "mvdr", "mudr", "mgr", "bc", "ing", "phd", "dr", "doc", "prof", "dipl", "dvm",
    "rndr", "phdr", "judr", "paeddr", "csc", "mba", "bsc", "msc", "dis", "ph", "d",
}


def strip_accents(text):
    return "".join(c for c in unicodedata.normalize("NFKD", text or "") if not unicodedata.combining(c))


def name_words(text):
    """'MVDr. Jana Nováková, Ph.D.' -> {'jana', 'novakova'} (titles, case and accents ignored)."""
    words = re.split(r"[\s.,;/()]+", strip_accents(text).lower())
    return {w for w in words if w and w not in TITLES}


# Raw WinVet species text (DRUH) -> elite.vet.pet SPECIES key. Keys are matched
# against the accent-free, lower-cased words of the raw text; the first hit wins.
SPECIES_WORDS = [
    ("dog", ["pes", "psi", "fena", "pejsek", "stene", "dog"]),
    ("cat", ["kocka", "kocky", "kocour", "kote", "cat"]),
    ("rabbit", ["kralik", "kralici", "rabbit"]),
    ("rodent", ["morce", "morcata", "potkan", "krysa", "krecek", "mys", "osmak", "degu",
                "cincila", "piskomil", "veverka", "hlodavec", "hlodavci"]),
    ("bird", ["papousek", "andulka", "korela", "ptak", "ptaci", "kanar", "zebricka",
              "agapornis", "holub", "slepice", "kachna"]),
    ("reptile", ["had", "agama", "zelva", "gekon", "jesterka", "leguan", "chameleon",
                 "krajta", "uzovka", "hroznys", "plaz", "plazi", "varan"]),
]


def map_species(raw):
    """Return (species_key, species_other). Unknown text -> ('other', raw text)."""
    text = (raw or "").strip()
    if not text:
        return "other", False
    words = set(re.split(r"[^a-z]+", strip_accents(text).lower()))
    for key, keys in SPECIES_WORDS:
        if words.intersection(keys):
            return key, False
    return "other", text


def normalize_phone(text):
    return re.sub(r"\D", "", text or "")


# ---------------------------------------------------------------- value converters

def to_str(value):
    if value is None:
        return False
    text = str(value).strip()
    return text or False


def to_int(value):
    if value is None or value == "":
        return False
    try:
        return int(value)
    except (TypeError, ValueError):
        return False


def to_float(value):
    if value is None or value == "":
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def to_bool(value):
    if isinstance(value, str):
        return value.strip().upper() in ("A", "Y", "1", "TRUE", "ANO")
    return bool(value)


MIN_YEAR, MAX_YEAR = 1900, 2100


def to_date(value):
    """'YYYY-MM-DD' -> date. Invalid dates and typo years (WinVet has e.g. '0218-10-25')
    outside 1900..2100 -> False."""
    if not value:
        return False
    if isinstance(value, datetime):
        value = value.date()
    if not isinstance(value, date):
        try:
            value = datetime.strptime(str(value)[:10], "%Y-%m-%d").date()
        except ValueError:
            return False
    return value if MIN_YEAR <= value.year <= MAX_YEAR else False


def bad_date(value):
    """True for a non-empty value that to_date rejects (reported in the push status)."""
    return bool(value) and not to_date(value)


def to_utc_datetime(value):
    """WinVet local (Europe/Prague) 'YYYY-MM-DD HH:MM:SS' -> naive UTC as Odoo stores it."""
    if not value:
        return False
    try:
        local = datetime.strptime(str(value)[:19], "%Y-%m-%d %H:%M:%S")
    except ValueError:
        day = to_date(value)
        if not day:
            return False
        local = datetime(day.year, day.month, day.day)
    if not MIN_YEAR <= local.year <= MAX_YEAR:
        return False
    return PRAGUE.localize(local).astimezone(pytz.utc).replace(tzinfo=None)
