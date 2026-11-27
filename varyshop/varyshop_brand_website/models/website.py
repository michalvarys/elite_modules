import base64

from odoo import fields, models, tools

ODOO_FAVICON = "web/static/img/favicon.ico"
VARYSHOP_FAVICON = "varyshop_brand/static/img/favicon.ico"


def read_favicon(path):
    with tools.file_open(path, "rb") as f:
        return base64.b64encode(f.read())


def favicon_variants(path):
    """The favicon file as stored by default, and as converted by the website when saved."""
    raw = read_favicon(path)
    converted = base64.b64encode(tools.image_process(
        base64.b64decode(raw), size=(256, 256), crop="center", output_format="ICO"))
    return {raw, converted}


class Website(models.Model):
    _inherit = "website"

    # the field of `website` is bound to its own default function, an override of it is not used
    favicon = fields.Binary(default=lambda self: read_favicon(VARYSHOP_FAVICON))

    def _varyshop_swap_favicon(self, old_path, new_path):
        """Websites still showing the default favicon of `old_path` get the one of `new_path`; a
        favicon someone uploaded is kept."""
        old = favicon_variants(old_path)
        new = read_favicon(new_path)
        for website in self.sudo().with_context(active_test=False, bin_size=False).search([]):
            if website.favicon in old:
                website.favicon = new
