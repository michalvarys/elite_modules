"""České státní svátky a ostatní svátky, kdy je zákonem zavřeno.

Počítá se v kódu (žádné záznamy, žádná údržba). Pohyblivé jsou jen Velký pátek
a Velikonoční pondělí – od Velikonoční neděle podle anonymního gregoriánského
algoritmu (Meeus/Jones/Butcher).
"""
from datetime import date, timedelta
from functools import lru_cache

PEVNE = [
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


def velikonocni_nedele(rok):
    """Velikonoční neděle (gregoriánský kalendář)."""
    a = rok % 19
    b, c = divmod(rok, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    ll = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * ll) // 451
    mesic, den = divmod(h + ll - 7 * m + 114, 31)
    return date(rok, mesic, den + 1)


@lru_cache(maxsize=32)
def _svatky(rok):
    out = {date(rok, m, d): nazev for m, d, nazev in PEVNE}
    nedele = velikonocni_nedele(rok)
    out[nedele - timedelta(days=2)] = "Velký pátek"
    out[nedele + timedelta(days=1)] = "Velikonoční pondělí"
    return out


def cz_svatky(rok):
    """{date: název} všech českých státních (a ostatních) svátků v roce."""
    return dict(_svatky(rok))


def svatek(den):
    """Název svátku v daný den, jinak None."""
    return _svatky(den.year).get(den)
