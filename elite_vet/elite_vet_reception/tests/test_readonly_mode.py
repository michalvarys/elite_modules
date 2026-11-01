from odoo.exceptions import UserError
from odoo.tests import tagged

from odoo.addons.elite_vet_clinic.models.readonly_mode import PARAM

from .common import ReceptionCase


@tagged("post_install", "-at_install")
class TestReadonlyMode(ReceptionCase):
    """Read-only mode in the reception screens and Pokladna: they open and show data, nothing
    is saved; Správce rezervací works as before."""

    def setUp(self):
        super().setUp()
        self.env["ir.config_parameter"].sudo().set_param(PARAM, "True")

    def test_reception_screens_save_nothing(self):
        reservation = self.reservation(9, pet=self.pet)
        reception = self.api(self.reception)
        self.assertTrue(reception.today_data())
        with self.assertRaises(UserError):
            reception.check_in(reservation.id)
        with self.assertRaises(UserError):
            reception.walk_in(self.pet.id)
        with self.assertRaises(UserError):
            reception.save_owner({"name": "Kartotéka Readonly"})
        with self.assertRaises(UserError):
            reception.save_pet(self.owner.id, {"name": "Pes Readonly", "species": "dog"})
        with self.assertRaises(UserError):
            reception.cancel_reservation(reservation.id)
        with self.assertRaises(UserError):
            reception.book(self.pet.id, self.procedure.id, "2030-01-07", 9 * 60, self.room.id)
        self.assertEqual(reservation.state, "confirmed")

    def test_room_board_is_read_only(self):
        nurse = self.api(self.nurse)
        data = nurse.room_board()
        self.assertTrue(data["perms"]["readonly"])
        self.assertFalse(data["perms"]["can_call"])
        with self.assertRaises(UserError):
            nurse.take_next_patient(self.room.id)

    def test_pos_sells_nothing(self):
        self.assertTrue(self.pos_config.with_user(self.reception).elite_vet_readonly)
        self.assertFalse(self.pos_config.with_user(self.manager).elite_vet_readonly)
        with self.assertRaises(UserError):
            self.env["pos.order"].with_user(self.reception).sync_from_ui([{"state": "paid"}])

    def test_manager_works_as_before(self):
        reservation = self.reservation(10, pet=self.pet)
        manager = self.api(self.manager)
        self.assertFalse(manager.room_board()["perms"]["readonly"])
        manager.check_in(reservation.id)
        self.assertTrue(self.env["elite.vet.clinical.record"].search([("reservation_id", "=", reservation.id)]))
