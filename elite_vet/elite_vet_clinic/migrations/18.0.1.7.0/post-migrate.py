"""18.0.1.7.0 (task 32): one text of the visit. record_text ("Záznam z vyšetření") is filled from
the deprecated anamnesis / examination / diagnosis: only the filled parts, each under its heading
("Anamnéza:", "Vyšetření:", "Diagnóza a doporučení:") on its own line, separated by a blank line;
a record with one filled part gets that text without a heading. The old columns are kept.
Idempotent (records that already have a record text are skipped)."""
import logging

from odoo.addons.elite_vet_clinic.models.clinical_record import migrate_legacy_texts

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return
    count = migrate_legacy_texts(cr)
    _logger.info("elite_vet_clinic 18.0.1.7.0: record_text filled for %d clinical records", count)
