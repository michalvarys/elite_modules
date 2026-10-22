from odoo import api, models

from odoo.addons.elite_vet_winvet.models.winvet_tools import to_int


class WinvetSync(models.AbstractModel):
    _inherit = "elite.vet.winvet.sync"

    def _push_items(self, records, stats, errors, batch, batches):
        super()._push_items(records, stats, errors, batch, batches)
        items = self.env["elite.vet.winvet.item"].search([("winvet_ref", "in", [to_int(r) for r in records])])
        items._sync_products(errors)
