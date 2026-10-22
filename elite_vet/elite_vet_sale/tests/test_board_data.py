from odoo.tests import tagged

from .common import SaleCase


@tagged("post_install", "-at_install")
class TestBoardData(SaleCase):
    """Payment state of the visit record on the reservation board (spec section 4)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.room = cls.env["elite.vet.room"].create({"name": "Ordinace test platba"})
        cls.day = "2030-03-04"

    def reservation(self, start, stop):
        return self.env["elite.vet.reservation"].create({
            "kind": "reservation", "state": "confirmed", "room_id": self.room.id,
            "start": "%s %s" % (self.day, start), "stop": "%s %s" % (self.day, stop),
            "partner_id": self.owner.id, "pet_id": self.pet.id})

    def event(self, reservation):
        events = self.env["elite.vet.reservation"].board_data(self.day)["events"]
        return next(e for e in events if e["id"] == reservation.id)

    def test_payment_state_follows_the_record(self):
        res = self.reservation("09:00:00", "09:30:00")
        self.assertIs(self.event(res)["payment_state"], False, "no record, no state")
        api = self.as_user(self.nurse)
        data = api.open_today_record(self.pet.id, reservation_id=res.id)
        record = self.Record.browse(data["id"])
        self.assertEqual(record.reservation_id, res)
        self.assertEqual(self.event(res)["payment_state"], "none", "a draft has no bill yet")
        api.add_free_line(record.id, "Stříhání drápků", 100.0)
        api.mark_done(record.id)
        self.assertEqual(self.event(res)["payment_state"], "waiting")
        self.settle(record.sale_order_id)
        self.assertEqual(self.event(res)["payment_state"], "paid")

    def test_reservation_without_record_is_false(self):
        res = self.reservation("11:00:00", "11:30:00")
        self.assertIs(self.event(res)["payment_state"], False)
