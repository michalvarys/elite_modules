from . import jazyky
from . import parametry
from . import stranky
from . import web


def _pri_instalaci(env):
    """Bezi po instalaci zakladniho modulu projektu.

    Poradi neni nahodne:

    1. Osirele systemove parametry se spravi jako prvni. Kdyz se nechaji
       byt, shodi pozdeji instalaci nebo tlacitko "Aktualizovat tema"
       hlaskou o duplicitnim klici -- i kdyz jde o modul cizi projektu.
    2. Teprve pak jazyky. Tenhle modul se z celeho projektu instaluje
       jako prvni, takze ostatni uz zapisuji preklady do zapnutych jazyku;
       do nezapnuteho jazyka zapsat nejde a preklad by se tise ztratil.
    """
    parametry.sprav(env)
    jazyky.nastav(env)
