"""18.0.2.4.0: the block reason is no longer translatable (request 25. 10.).

A block reason is an internal note: typed in an English or German UI it was stored only in that
language and a Czech user did not see the change. The jsonb column becomes plain text before
Odoo updates the field (Odoo itself would keep the en_US value): the Czech value wins, then
English, then any other filled language.
"""
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    cr.execute("""
        SELECT data_type FROM information_schema.columns
         WHERE table_name = 'elite_vet_reservation' AND column_name = 'block_reason'
    """)
    row = cr.fetchone()
    if not row or row[0] != "jsonb":
        return
    cr.execute("ALTER TABLE elite_vet_reservation ADD COLUMN block_reason_text varchar")
    cr.execute("""
        UPDATE elite_vet_reservation
           SET block_reason_text = COALESCE(
                   NULLIF(block_reason->>'cs_CZ', ''),
                   NULLIF(block_reason->>'en_US', ''),
                   (SELECT t.value FROM jsonb_each_text(block_reason) AS t(lang, value)
                     WHERE t.value <> '' ORDER BY t.lang LIMIT 1))
         WHERE block_reason IS NOT NULL
    """)
    _logger.info("block_reason: %s values kept as plain text", cr.rowcount)
    cr.execute("ALTER TABLE elite_vet_reservation DROP COLUMN block_reason")
    cr.execute("ALTER TABLE elite_vet_reservation RENAME COLUMN block_reason_text TO block_reason")
