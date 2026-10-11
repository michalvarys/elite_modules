"""18.0.1.2.0: přepočet názvů rezervací.

Před verzí 18.0.1.1.0 se název počítal v jazyce toho, kdo rezervaci založil
(web v němčině, správce v angličtině). Teď se počítá v jazyce kliniky;
staré rezervace přepočítáme, ať tabule i seznamy mluví česky.
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
