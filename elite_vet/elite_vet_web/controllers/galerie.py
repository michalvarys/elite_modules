from odoo import http
from odoo.http import request


class EliteVetGalerie(http.Controller):

    @http.route("/elite_vet/galerie", type="json", auth="public", website=True, readonly=True)
    def galerie(self, lang=None):
        """Fotky pro blok Galerie.

        Jazyk posila stranka: pozadavek jde mimo jazykovou adresu (/de, /en, ...)
        a popisek fotky je prekladany alt text.
        """
        Fotka = request.env["elite.vet.gallery.photo"].sudo()
        if lang in dict(request.env["res.lang"].get_installed()):
            Fotka = Fotka.with_context(lang=lang)
        return [
            {
                "src": f"/web/image/elite.vet.gallery.photo/{fotka.id}/image/500x667",
                "alt": fotka.name or "Elite Vet",
            }
            for fotka in Fotka.search([])
        ]
