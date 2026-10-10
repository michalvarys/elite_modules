from odoo.tests import TransactionCase


class ReservationCase(TransactionCase):
    """Spolecna data: tri ordinace jako na klinice a par pomocnych metod."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Room = cls.env["elite.vet.room"]
        cls.room1 = Room.create({"name": "Ordinace 1", "sequence": 10, "color": "teal"})
        cls.room2 = Room.create({"name": "Ordinace 2", "sequence": 20, "color": "blue"})
        cls.sal = Room.create({"name": "Sál", "sequence": 30, "color": "purple", "online": False})
        Proc = cls.env["elite.vet.procedure"]
        cls.vacc = Proc.create({"name": "Vaccination", "duration": 15, "symbol": "V", "color": "green"})
        cls.derm = Proc.create({"name": "Dermatological problem", "duration": 30, "symbol": "D",
                                "color": "blue", "room_ids": [(6, 0, [cls.room1.id])]})

    def hours(self, room, weekday, h_from, h_to, **extra):
        vals = {"room_id": room.id, "weekday": str(weekday), "hour_from": h_from, "hour_to": h_to}
        vals.update(extra)
        return self.env["elite.vet.room.hours"].create(vals)
