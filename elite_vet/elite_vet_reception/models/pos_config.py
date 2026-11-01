from odoo import api, fields, models

from odoo.addons.elite_vet_clinic.models.readonly_mode import check_clinic_writable, clinic_readonly


class PosConfig(models.Model):
    _inherit = "pos.config"

    is_elite_vet_reception = fields.Boolean(
        string="Pokladna recepce", compute="_compute_is_elite_vet_reception",
        help="Pokladna „Recepce“: v pokladně jsou záložky Dnes, Objednat, Kartotéka a Tabule "
             "a po přihlášení se otevře záložka Dnes.")

    elite_vet_readonly = fields.Boolean(
        string="Jen pro čtení", compute="_compute_elite_vet_readonly",
        help="Režim jen pro čtení (Nastavení → Elite Vet) a uživatel není správce rezervací: "
             "pokladna se otevře, ale nic neuloží.")

    @api.depends_context("uid")
    def _compute_elite_vet_readonly(self):
        self.elite_vet_readonly = clinic_readonly(self.env)

    def _compute_is_elite_vet_reception(self):
        reception = self.env.ref("elite_vet_sale.pos_config_reception", raise_if_not_found=False)
        for config in self:
            config.is_elite_vet_reception = bool(reception) and config == reception


class PosOrder(models.Model):
    _inherit = "pos.order"

    @api.model
    def sync_from_ui(self, orders):
        """The screen stops payment in read-only mode already; this is the server-side backstop.
        Drafts pass: the till syncs an open order in the background (printing, reload)."""
        if any(order.get("state", "draft") != "draft" for order in orders):
            check_clinic_writable(self.env)
        return super().sync_from_ui(orders)
