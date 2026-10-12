"""Czech public holidays and other days when businesses are closed by law.

Computed in code (no records, no maintenance). Only Good Friday and Easter
Monday move; they are derived from Easter Sunday using the anonymous Gregorian
algorithm (Meeus/Jones/Butcher).
"""
from datetime import date, timedelta
from functools import lru_cache

FIXED_HOLIDAYS = [
    (1, 1, "Den obnovy samostatného českého státu, Nový rok"),
    (5, 1, "Svátek práce"),
    (5, 8, "Den vítězství"),
    (7, 5, "Den slovanských věrozvěstů Cyrila a Metoděje"),
    (7, 6, "Den upálení mistra Jana Husa"),
    (9, 28, "Den české státnosti"),
    (10, 28, "Den vzniku samostatného československého státu"),
    (11, 17, "Den boje za svobodu a demokracii"),
    (12, 24, "Štědrý den"),
    (12, 25, "1. svátek vánoční"),
    (12, 26, "2. svátek vánoční"),
]


def easter_sunday(year):
    """Easter Sunday (Gregorian calendar)."""
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    ll = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * ll) // 451
    month, day = divmod(h + ll - 7 * m + 114, 31)
    return date(year, month, day + 1)


@lru_cache(maxsize=32)
def _holidays(year):
    out = {date(year, m, d): name for m, d, name in FIXED_HOLIDAYS}
    sunday = easter_sunday(year)
    out[sunday - timedelta(days=2)] = "Velký pátek"
    out[sunday + timedelta(days=1)] = "Velikonoční pondělí"
    return out


def czech_holidays(year):
    """{date: name} of all Czech public (and other) holidays in the year."""
    return dict(_holidays(year))


def holiday_name(day):
    """Name of the holiday on the given day, otherwise None."""
    return _holidays(day.year).get(day)
