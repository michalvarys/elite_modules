"""18.0.2.18.0 (request 3. 11.): a reservation without a procedure gets Jiné. The clinic entered
its procedures by hand, so its Jiné has no XML ID: bind elite_vet_reservation.procedure_other to
it before the data file loads, else the data file would create a second Jiné. Without one, the
data file creates it. Idempotent."""
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return
    cr.execute("""SELECT 1 FROM ir_model_data
                   WHERE module = 'elite_vet_reservation' AND name = 'procedure_other'""")
    if cr.fetchone():
        return
    cr.execute("""SELECT id FROM elite_vet_procedure
                   WHERE name->>'cs_CZ' = 'Jiné' OR name->>'en_US' IN ('Jiné', 'Other')
                   ORDER BY active DESC, id LIMIT 1""")
    row = cr.fetchone()
    if not row:
        return
    cr.execute("""INSERT INTO ir_model_data (module, name, model, res_id, noupdate)
                  VALUES ('elite_vet_reservation', 'procedure_other', 'elite.vet.procedure', %s, true)""", row)
    _logger.info("Úkon Jiné (id %s) navázán na elite_vet_reservation.procedure_other", row[0])
