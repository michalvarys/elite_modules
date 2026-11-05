from werkzeug.exceptions import NotFound
from werkzeug.urls import url_encode

from odoo import http
from odoo.http import request

AGE_COOKIE = "elite_trafika_18"
AGE_COOKIE_DAYS = 30


class TrafikaCatalogController(http.Controller):
    """Public catalog of one website; it is behind the age question and sells nothing."""

    def _check_website(self):
        """The database can serve other websites too, the catalog must not appear on them."""
        name = request.env["ir.config_parameter"].sudo().get_param("elite_trafika_catalog.website")
        if name and request.website.name != name:
            raise NotFound()

    def _is_adult(self):
        return request.httprequest.cookies.get(AGE_COOKIE) == "1"

    def _source(self, source):
        return request.env["elite.trafika.catalog.like"].sudo().clean_source(source)

    @http.route("/katalog", type="http", auth="public", website=True, sitemap=False)
    def catalog(self, zdroj=None, **kw):
        self._check_website()
        source = self._source(zdroj)
        if not self._is_adult():
            return request.render("elite_trafika_catalog.age_gate", {"source": source})
        Item = request.env["elite.trafika.catalog.item"].sudo()
        return request.render("elite_trafika_catalog.catalog_page", {
            "items": Item.search([]), "kinds": dict(Item._fields["kind"].selection), "source": source,
        })

    @http.route("/katalog/18", type="http", auth="public", website=True, sitemap=False, methods=["POST"])
    def confirm_age(self, zdroj=None, **kw):
        self._check_website()
        response = request.redirect("/katalog?%s" % url_encode({"zdroj": self._source(zdroj)}))
        response.set_cookie(AGE_COOKIE, "1", max_age=AGE_COOKIE_DAYS * 24 * 3600, httponly=True, samesite="Lax")
        return response

    @http.route("/katalog/zajem", type="json", auth="public", website=True, sitemap=False, methods=["POST"])
    def interest(self, item_id, liked, source=None):
        self._check_website()
        item = request.env["elite.trafika.catalog.item"].sudo().browse(int(item_id)).exists()
        if not self._is_adult() or not item.active:
            return {"ok": False}
        item.set_liked(bool(liked), source)
        return {"ok": True}
