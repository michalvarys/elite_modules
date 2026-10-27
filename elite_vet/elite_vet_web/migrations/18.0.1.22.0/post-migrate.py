# -*- coding: utf-8 -*-
"""Zamrzla galerie v ulozenych strankach -> blok Galerie.

Editor pri ulozeni stranky zapsal vykreslenou galerii natvrdo: ID fotek
a pocet stranek v inline <style>. Fotka pridana nebo smazana v adminu se
pak na webu neprojevila. Stranky ulozene z editoru upgrade modulu
neprepise, proto se tu galerie nahradi blokem s_vet_galerie hned za
sekci, ve ktere byla.

Kazdy jazyk se prestavi zvlast a texty (napoveda, popisky sipek) se
berou z puvodni galerie v tom jazyce, takze preklady zustanou.
"""
import json
import logging

from lxml import etree

from odoo import api, SUPERUSER_ID

_logger = logging.getLogger(__name__)

SIPKA = ('<svg width="21" height="21" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
         'stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><polyline points="%s"/></svg>')
BLOK = (
    '<section class="s_vet_galerie ev-gal-sekce" data-snippet="s_vet_galerie" data-name="Galerie kliniky">'
    '<div class="ev-container"><div class="ev-gal-box">'
    '<div class="ev-gal-view"><div class="ev-gal-track o_not_editable"></div></div>'
    '<div class="ev-gal-nav">'
    '<button type="button" class="ev-gal-arr ev-gal-arr--prev">' + SIPKA % "15 18 9 12 15 6" + '</button>'
    '<button type="button" class="ev-gal-arr ev-gal-arr--next">' + SIPKA % "9 18 15 12 9 6" + '</button>'
    '</div></div><p class="ev-gal-hint"></p></div></section>'
)
TRIDA = "contains(concat(' ', normalize-space(@class), ' '), ' %s ')"


def _text(gal, xpath, vychozi):
    nalez = gal.xpath(xpath)
    if not nalez:
        return vychozi
    hodnota = nalez[0] if isinstance(nalez[0], str) else nalez[0].text
    return (hodnota or "").strip() or vychozi


def prestavit(arch):
    """Vrati arch s galerii nahrazenou blokem, nebo None, kdyz v nem neni."""
    koren = etree.fromstring(arch)
    galerie = koren.xpath("//div[%s]" % (TRIDA % "ev-gal-inline"))
    if not galerie:
        return None
    for gal in galerie:
        blok = etree.fromstring(BLOK)
        blok.xpath("//p")[0].text = _text(gal, ".//p[%s]" % (TRIDA % "ev-gal-hint"),
                                          "Swipe sideways to browse the photos")
        for smer, vychozi in (("prev", "Previous photos"), ("next", "Next photos")):
            popisek = _text(gal, ".//*[%s]/@aria-label" % (TRIDA % ("ev-gal-arr--" + smer)), vychozi)
            blok.xpath("//button[%s]" % (TRIDA % ("ev-gal-arr--" + smer)))[0].set("aria-label", popisek)

        sekce = next(gal.iterancestors("section"), None)
        rodic = gal.getparent()
        # remove() by zahodil i text za galerii (tail), ten musi zustat
        if gal.tail:
            pred = gal.getprevious()
            if pred is not None:
                pred.tail = (pred.tail or "") + gal.tail
            else:
                rodic.text = (rodic.text or "") + gal.tail
        if sekce is not None:
            rodic.remove(gal)
            blok.tail = sekce.tail
            sekce.addnext(blok)
        else:
            rodic.replace(gal, blok)
    return etree.tostring(koren, encoding="unicode")


def migrate(cr, version):
    cr.execute("SELECT id, key, arch_db FROM ir_ui_view WHERE arch_db::text LIKE %s", ("%ev-gal-inline%",))
    zmeneno = []
    for view_id, key, arch_db in cr.fetchall():
        novy = {}
        for jazyk, arch in arch_db.items():
            prestaveno = prestavit(arch) if arch else None
            novy[jazyk] = prestaveno if prestaveno is not None else arch
        if novy != arch_db:
            cr.execute("UPDATE ir_ui_view SET arch_db = %s WHERE id = %s", (json.dumps(novy), view_id))
            zmeneno.append("%s (%s)" % (key, view_id))
    if zmeneno:
        env = api.Environment(cr, SUPERUSER_ID, {})
        env["ir.ui.view"].invalidate_model(["arch_db"])
        env.registry.clear_cache("templates")
        _logger.info("Zamrzla galerie nahrazena blokem Galerie v: %s", ", ".join(zmeneno))
