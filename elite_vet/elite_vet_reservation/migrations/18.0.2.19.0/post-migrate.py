"""18.0.2.19.0 (request 3. 11.): the pet name and species of a reservation follow its selected pet.
The fields became computed; existing reservations with a pet take the values from its card once."""
from odoo import api, SUPERUSER_ID


def migrate(cr, version):
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    Res = env["elite.vet.reservation"].with_context(active_test=False)
    records = Res.search([("pet_id", "!=", False)])
    env.add_to_compute(Res._fields["pet_name"], records)
    env.add_to_compute(Res._fields["pet_species"], records)
    records.flush_recordset(["pet_name", "pet_species"])
