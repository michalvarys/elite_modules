# -*- coding: utf-8 -*-
"""Ktere stranky projektu web ukazuje.

Moduly Elite Vet si pri instalaci zakladaji sest stranek. Na ostrem webu
ale muze byt cast stranek jeste ta puvodni, rucne delana, a prepsat ji
nechceme. Proto se da vybrat, ktere stranky z modulu se maji zverejnit --
treba jen domovskou a "O nas", zatimco cenik, tym, rozpis a rezervace
zustanou takove, jake na webu uz jsou.

Volba lezi v parametru `elite_vet.stranky` (Nastaveni -> Technicke ->
Parametry systemu):

    vse             vsechny stranky projektu (vychozi)
    /,/o-nas        jen domovska stranka a O nas

Aby se to na ostrem webu povedlo napoprve, zaloz parametr **jeste pred**
instalaci modulu. Instalacni hak si ho precte a rovnou zverejni jen to,
co je v nem.

Nezverejnena stranka se nemaze, jen schova, takze se da kdykoliv zapnout
zpatky -- staci parametr zmenit a modul zaktualizovat. Stranek, ktere
nepatri tomuhle projektu, se uklid nikdy nedotkne.
"""
import logging

_logger = logging.getLogger(__name__)

KLIC = "elite_vet.stranky"
VSE = "vse"

# adresa -> externi ID zaznamu stranky, ktery zaklada modul.
# Domovska stranka zaznam v XML nema, prepina se hookem v elite_vet_web,
# proto u ni stoji None a resi se podle adresy.
STRANKY = {
    "/": None,
    "/o-nas": "elite_vet_web.o_nas_page",
    "/cenik": "elite_vet_web.cenik_page",
    "/rezervacni-system": "elite_vet_web.rezervace_page",
    "/nas-tym": "elite_vet_team.nas_tym_page",
    "/rozpis-lekaru": "elite_vet_calendar.rozpis_lekaru_page",
}


def volba(env):
    """Vrati mnozinu adres, ktere se maji zverejnit."""
    hodnota = (env["ir.config_parameter"].sudo().get_param(KLIC) or VSE).strip()
    if not hodnota or hodnota.lower() == VSE:
        return set(STRANKY)

    chtene = set()
    for kus in hodnota.split(","):
        adresa = kus.strip()
        if not adresa:
            continue
        if adresa not in STRANKY:
            _logger.warning(
                "Parametr %s zminuje adresu '%s', ktera k projektu nepatri. "
                "Znam jen: %s", KLIC, adresa, ", ".join(sorted(STRANKY)))
            continue
        chtene.add(adresa)
    return chtene


def uplatni(env):
    """Zverejni stranky z volby a zbyle stranky projektu schova.

    Vola se z instalacniho haku kazdeho modulu a z migrace, takze se stav
    srovna pri instalaci i pri kazde aktualizaci.
    """
    chtene = volba(env)
    if chtene == set(STRANKY):
        # Vychozi stav, neni co resit. Zaroven se tim na devu nic nemeni.
        return

    Stranka = env["website.page"].sudo()
    zapnuto, vypnuto = [], []

    for adresa, externi_id in STRANKY.items():
        if externi_id:
            stranka = env.ref(externi_id, raise_if_not_found=False)
        else:
            # Domovska stranka: bere se ta, ktera ukazuje na nasi sablonu.
            sablona = env.ref("elite_vet_web.homepage", raise_if_not_found=False)
            stranka = Stranka.search(
                [("url", "=", "/"), ("view_id", "=", sablona.id)], limit=1
            ) if sablona else Stranka

        if not stranka:
            continue

        ma_byt = adresa in chtene
        if stranka.is_published == ma_byt:
            continue
        stranka.is_published = ma_byt
        (zapnuto if ma_byt else vypnuto).append(adresa)

    if zapnuto:
        _logger.info("Zverejneno: %s", ", ".join(zapnuto))
    if vypnuto:
        _logger.warning(
            "Schovano podle parametru %s: %s. Na techto adresach web ukazuje "
            "to, co na nich bylo predtim.", KLIC, ", ".join(vypnuto))
