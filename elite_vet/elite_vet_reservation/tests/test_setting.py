from odoo.tests import tagged

from .common import ReservationCase


@tagged("post_install", "-at_install")
class TestSetting(ReservationCase):

    def test_defaults(self):
        s = self.env["elite.vet.setting"].nastaveni()
        self.assertEqual(s.booking_slot_step, 15)
        self.assertEqual(s.booking_min_hours_before, 24)
        self.assertEqual(s.booking_max_days_ahead, 60)
        self.assertEqual(s.booking_cancel_hours_before, 12)
        self.assertFalse(s.booking_require_doctor)
        self.assertFalse(s.booking_deposits_enabled)

    def test_seed_is_idempotent_and_skips_when_rooms_exist(self):
        from odoo.addons.elite_vet_reservation import _post_init
        before = self.env["elite.vet.procedure"].search_count([])
        _post_init(self.env)          # rooms from common.py already exist -> nothing is created
        self.assertEqual(self.env["elite.vet.procedure"].search_count([]), before)

    def test_seed_on_empty_db(self):
        from odoo.addons.elite_vet_reservation import _post_init, PROCEDURES
        self.env["elite.vet.reservation"].search([]).unlink()
        self.env["elite.vet.doctor.assignment"].search([]).unlink()
        # Including archived ones (common.py archives the default data), otherwise the guard would skip the seed.
        self.env["elite.vet.procedure"].with_context(active_test=False).search([]).unlink()
        self.env["elite.vet.room"].with_context(active_test=False).search([]).unlink()
        _post_init(self.env)
        rooms = self.env["elite.vet.room"].search([], order="sequence")
        self.assertEqual(rooms.mapped("name"), ["Ordinace 1", "Ordinace 2", "Sál"])
        self.assertFalse(rooms[2].online)
        self.assertEqual(self.env["elite.vet.procedure"].search_count([]), len(PROCEDURES))
        # Mon-Fri 8:15-19:30 + Sun 10:15-17:45 = 6 lines per room, theatre without hours
        self.assertEqual(len(rooms[0].hours_ids), 6)
        self.assertEqual(len(rooms[2].hours_ids), 0)
        vacc = self.env["elite.vet.procedure"].search([("symbol", "=", "V")])
        self.assertEqual(vacc.name, "Vaccination")
        if "cs_CZ" in self.env["res.lang"].search([]).mapped("code"):
            self.assertEqual(vacc.with_context(lang="cs_CZ").name, "Vakcinace")

    def test_slot_step_must_be_positive(self):
        from odoo.exceptions import ValidationError
        s = self.env["elite.vet.setting"].nastaveni()
        for bad in ({"booking_slot_step": 0}, {"booking_slot_step": 7}, {"booking_min_hours_before": -1}):
            with self.assertRaises(ValidationError), self.cr.savepoint():
                s.write(bad)
