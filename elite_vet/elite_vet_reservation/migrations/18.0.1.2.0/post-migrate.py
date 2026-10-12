"""18.0.1.2.0: recompute reservation names.

Before 18.0.1.2.0 the name was computed in the language of whoever created the
reservation (website in German, admin in English). Now it is computed in the
clinic's language; old reservations are recomputed so the board and lists are in Czech.
"""
import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    reservations = env["elite.vet.reservation"].with_context(active_test=False).search([])
    env.add_to_compute(reservations._fields["name"], reservations)
    env.flush_all()
    _logger.info("elite_vet_reservation: přepočítán název u %s rezervací", len(reservations))
