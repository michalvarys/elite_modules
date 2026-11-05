"""18.0.1.3.0: contacts created by the ggLeap sync got the language of the superuser (English), so
Odoo sent them e-mails in English. They get Czech, like every new contact from now on. Only contacts
linked to ggLeap still in English and without an Odoo user; other languages are kept."""
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
         WHERE p.ggleap_uuid IS NOT NULL AND p.ggleap_uuid != '' AND (p.lang = 'en_US' OR p.lang IS NULL)
           AND NOT EXISTS (SELECT 1 FROM res_users u WHERE u.partner_id = p.id)
    """)
    _logger.info("elite_arena_ggleap 18.0.1.3.0: %d ggLeap contacts switched to Czech", cr.rowcount)
