# -*- coding: utf-8 -*-
"""Vyber webu, kteremu projekt patri.

Lezi v zakladnim modulu, protoze ho potrebuje uz nastaveni jazyku, ktere
bezi jako prvni. Ostatni moduly si ho berou odsud.
"""
import logging

_logger = logging.getLogger(__name__)


def zvol_web(env):
    """Vybere web, kteremu stranky projektu patri.

    V databazi muze bezet vic webu vedle sebe (Elite Vet, Elite Arena,
    trafika, Jack, IMI). Stranka bez prirazeneho webu se v Odoo zobrazi
    na VSECH domenach, coz je presne to, co nechceme.

    Poradi hledani: domena obsahujici elite-vet, pak cokoli s "vet"
    v nazvu nebo domene, jinak jediny existujici web. Kdyz nic nesedi,
    vrati prvni a zapise to do logu -- administrator to pak prepise
    v Web -> Konfigurace -> Stranky.
    """
    weby = env["website"].search([])
    if not weby:
        return False
    if len(weby) == 1:
        return weby

    for web in weby:
        if "elite-vet" in (web.domain or "").lower():
            return web
    for web in weby:
        popis = ((web.name or "") + " " + (web.domain or "")).lower()
        if "vet" in popis and "arena" not in popis:
            return web

    _logger.warning(
        "Nepodarilo se poznat, ktery web je Elite Vet. Pouzil se web '%s'. "
        "Zmenit to jde v Web -> Konfigurace -> Stranky.",
        weby[0].name,
    )
    return weby[0]
