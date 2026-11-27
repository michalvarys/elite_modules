from odoo import models

from ..brand import url


class IrHttp(models.AbstractModel):
    _inherit = "ir.http"

    def session_info(self):
        info = super().session_info()
        if "support_url" in info:
            info["support_url"] = url("support")
        return info
