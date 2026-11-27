from odoo import http
from odoo.addons.web.controllers.webmanifest import WebManifest

from ..brand import COLOR, ICON_IOS, NAME


class VaryshopWebManifest(WebManifest):
    """Installable web app (PWA): Varyshop name, colours and icons."""

    def _get_webmanifest(self):
        manifest = super()._get_webmanifest()
        if manifest.get("name") == "Odoo":
            manifest["name"] = NAME
        manifest["background_color"] = manifest["theme_color"] = COLOR
        manifest["icons"] = [{
            "src": "/varyshop_brand/static/img/icon-%s.png" % size,
            "sizes": size,
            "type": "image/png",
        } for size in ("192x192", "512x512")]
        return manifest

    def _icon_path(self):
        return "varyshop_brand/static/img/icon-192x192.png"

    @http.route()
    def scoped_app(self, app_id, path="", app_name=""):
        response = super().scoped_app(app_id, path=path, app_name=app_name)
        if getattr(response, "qcontext", None) is not None:
            response.qcontext["apple_touch_icon"] = ICON_IOS
        return response
