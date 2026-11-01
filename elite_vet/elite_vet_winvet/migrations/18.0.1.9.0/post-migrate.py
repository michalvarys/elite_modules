"""18.0.1.9.0: owners created by the WinVet push got the language of the superuser (English), so
Odoo sent them e-mails in English. They get Czech, like every new owner from now on. Only owners
from WinVet still in English and without an Odoo user; a language picked on purpose is kept.
Reservations booked at the desk (Objednat) took the owner's language, so their reminders would
go out in English too: the internal ones of these owners get Czech; web bookings keep the
language of the visitor."""
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return
    cr.execute("SELECT 1 FROM res_lang WHERE code = 'cs_CZ' AND active")
    if not cr.fetchone():
        return
    cr.execute("""
        UPDATE res_partner p SET lang = 'cs_CZ'
         WHERE p.winvet_ref IS NOT NULL AND (p.lang = 'en_US' OR p.lang IS NULL)
           AND NOT EXISTS (SELECT 1 FROM res_users u WHERE u.partner_id = p.id)
    """)
    _logger.info("elite_vet_winvet 18.0.1.9.0: %d WinVet owners switched to Czech", cr.rowcount)
    cr.execute("""
        UPDATE elite_vet_reservation r SET lang = 'cs_CZ'
          FROM res_partner p
         WHERE p.id = r.partner_id AND p.winvet_ref IS NOT NULL AND p.lang = 'cs_CZ'
           AND r.source = 'internal' AND r.lang = 'en_US'
    """)
    _logger.info("elite_vet_winvet 18.0.1.9.0: %d desk reservations switched to Czech", cr.rowcount)
