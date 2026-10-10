# -*- coding: utf-8 -*-
"""Oprava osirelych systemovych parametru.

Kdyz parametr vznikne za behu pres `set_param`, nema zaznam `ir.model.data`.
Jakmile ho potom nejaky modul ma i ve svych datech, Odoo ho pri instalaci
nebo aktualizaci nepozna jako svuj a zkusi ho zalozit znovu:

    psycopg2.errors.UniqueViolation: duplicate key value violates unique
    constraint "ir_config_parameter_key_uniq"
    DETAIL:  Key (key)=(theme_elite_arena.mobile_intro_enabled) already exists

Spadne tim cela instalace nebo tlacitko "Aktualizovat tema", a to
komukoliv v te databazi -- i kdyz s nasim projektem ten modul nesouvisi.
Prave tohle potkalo dev i ostry web.

Oprava je jen doplneni chybejiciho zaznamu. Hleda se poctive: projdou se
datove soubory nainstalovanych modulu, najde se `<record model="ir.config_parameter">`
se stejnym klicem a pouzije se JEHO id -- vymyslet si jine by nepomohlo,
Odoo by parametr stejne nenaslo a zkusilo zalozit znovu.

Zaznam dostane `noupdate`, takze aktualizace modulu nepreplacne hodnotu,
kterou uz nekdo nastavil. Zadny parametr se nemaze ani nepresouva.
"""
import logging
import os

from lxml import etree

_logger = logging.getLogger(__name__)


def _datove_soubory(cesta_modulu, manifest):
    """Vrati XML soubory, ktere modul nacita jako data."""
    for klic in ("data", "demo", "init_xml", "update_xml"):
        for nazev in manifest.get(klic) or []:
            if nazev.endswith(".xml"):
                yield os.path.join(cesta_modulu, nazev)


def _parametry_v_modulu(cesta_modulu, manifest):
    """Dvojice (id zaznamu, klic parametru) deklarovane v datech modulu."""
    for soubor in _datove_soubory(cesta_modulu, manifest):
        if not os.path.exists(soubor):
            continue
        try:
            strom = etree.parse(soubor)
        except etree.XMLSyntaxError:
            continue
        for zaznam in strom.iter("record"):
            if zaznam.get("model") != "ir.config_parameter":
                continue
            id_zaznamu = zaznam.get("id")
            if not id_zaznamu:
                continue
            for pole in zaznam.iter("field"):
                if pole.get("name") == "key" and (pole.text or "").strip():
                    yield id_zaznamu.split(".")[-1], pole.text.strip()


def sprav(env):
    """Doplni chybejici zaznamy ir.model.data u systemovych parametru."""
    from odoo.modules.module import get_module_path

    Parametr = env["ir.config_parameter"].sudo()
    Data = env["ir.model.data"].sudo()

    # parametry, ktere v databazi jsou, ale nikdo se k nim nehlasi
    maji_zaznam = set(Data.search([("model", "=", "ir.config_parameter")]).mapped("res_id"))
    osirele = {p.key: p.id for p in Parametr.search([]) if p.id not in maji_zaznam}
    if not osirele:
        _logger.info("Systemove parametry: zadny osirely, neni co spravovat.")
        return

    moduly = env["ir.module.module"].sudo().search([("state", "=", "installed")])

    opraveno = []
    for modul in moduly:
        try:
            cesta = get_module_path(modul.name)
        except Exception:  # noqa: BLE001 - modul muze byt smazany z disku
            continue
        if not cesta:
            continue

        # manifest se cte pres Odoo, at sedi s tim, co se opravdu nacita
        try:
            from odoo.modules.module import get_manifest
            manifest = get_manifest(modul.name)
        except Exception:  # noqa: BLE001
            continue
        if not manifest:
            continue

        for id_zaznamu, klic in _parametry_v_modulu(cesta, manifest):
            if klic not in osirele:
                continue
            if Data.search_count([("module", "=", modul.name),
                                  ("name", "=", id_zaznamu)]):
                continue
            Data.create({
                "module": modul.name,
                "name": id_zaznamu,
                "model": "ir.config_parameter",
                "res_id": osirele.pop(klic),
                "noupdate": True,
            })
            opraveno.append("%s.%s (%s)" % (modul.name, id_zaznamu, klic))

    if opraveno:
        _logger.warning(
            "Systemove parametry bez zaznamu doplneny, aby na nich nespadla "
            "instalace ani aktualizace tematu: %s. Hodnoty zustaly beze zmeny.",
            ", ".join(opraveno))
    else:
        _logger.info(
            "Systemove parametry: %s osirelych, ale zadny modul je ve svych "
            "datech nema, takze nic nehrozi.", len(osirele))
