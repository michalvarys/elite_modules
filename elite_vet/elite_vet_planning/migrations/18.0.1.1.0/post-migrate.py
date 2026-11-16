"""18.0.1.1.0 (requests 16. 11.)

* Months whose plan is already on /rozpis-lekaru stay published (publishing is new: a month
  without a record would disappear from the website).
* Planned shifts get the roster type by their time (they all had the slot's type, e.g. Celodenní).
"""
from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    cr.execute("""SELECT DISTINCT date_trunc('month', date)::date FROM elite_vet_shift
                  WHERE planning_slot_id IS NOT NULL""")
    Month = env["elite.vet.roster.month"]
    for (first,) in cr.fetchall():
        Month._set_published(first, True)
    Planner = env["elite.vet.planner"]
    shifts = env["elite.vet.shift"].search([("planning_slot_id", "!=", False)])
    for shift in shifts:
        shift_type = Planner._type_for_hours(shift.planning_slot_id, shift.hour_from, shift.hour_to)
        if shift_type != shift.type_id:
            shift.type_id = shift_type
