"""Reception steps of the clinic setup: employee login (pos_hr) on the Recepce till and the
reception home action pointing to that till. Runs with `elite.vet.sale.setup.ensure_setup()`,
in the post-init hook and on every module update (data/home_actions.xml)."""
import logging

from odoo import api, models

_logger = logging.getLogger(__name__)

RECEPTION_POS_ACTION = "elite_vet_reception.action_open_reception_pos"


class EliteVetSaleSetup(models.AbstractModel):
    _inherit = "elite.vet.sale.setup"

    @api.model
    def ensure_setup(self, company=None):
        super().ensure_setup(company=company)
        self.sudo()._ensure_reception()

    @api.model
    def _ensure_reception(self):
        config = self.pos_config()
        self._ensure_pos_employee_login(config)
        self._ensure_reception_home_url(config)

    def _ensure_pos_employee_login(self, config):
        if config.module_pos_hr:
            return
        if config.session_ids.filtered(lambda s: s.state != "closed"):
            # module_pos_hr is a forbidden change while the till is open (pos.config.write).
            _logger.warning("Elite Vet: till %s has an open session, employee login (pos_hr) not enabled – "
                            "close the till and update elite_vet_reception again", config.name)
            return
        config.module_pos_hr = True

    def _ensure_reception_home_url(self, config):
        action = self.env.ref(RECEPTION_POS_ACTION, raise_if_not_found=False)
        url = "/pos/ui?config_id=%d" % config.id
        if action and action.url != url:
            action.url = url
