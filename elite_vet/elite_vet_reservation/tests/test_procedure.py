from odoo.exceptions import ValidationError
from odoo.tests import tagged

from .common import ReservationCase


@tagged("post_install", "-at_install")
class TestProcedure(ReservationCase):

    def test_rooms_for_booking_defaults_to_all_online_rooms(self):
        self.assertEqual(self.vacc.rooms_for_booking(), self.room1 | self.room2)  # the theatre is not online

    def test_rooms_for_booking_respects_room_ids_and_online(self):
        self.derm.room_ids = [(6, 0, [self.room1.id, self.surgery.id])]
        self.assertEqual(self.derm.rooms_for_booking(), self.room1)

    def test_duration_must_be_positive_multiple_of_five(self):
        with self.assertRaises(ValidationError):
            self.vacc.duration = 0
        with self.assertRaises(ValidationError):
            self.vacc.duration = 17

    def test_deposit_amount_required_when_deposit_required(self):
        with self.assertRaises(ValidationError):
            self.vacc.write({"deposit_required": True, "deposit_amount": 0})
