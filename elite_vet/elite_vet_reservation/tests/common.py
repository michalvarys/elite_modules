from datetime import datetime

import pytz

from odoo.tests import TransactionCase


class ReservationCase(TransactionCase):
    """Shared data: three rooms as at the clinic, plus a few helper methods."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Default data from post_init_hook (rooms, hours, procedures) and anything
        # already in the DB would feed foreign rooms and slots into the tests. Archive it;
        # search([]) then returns only this class's fixtures.
        for model in ("elite.vet.room", "elite.vet.procedure"):
            cls.env[model].search([]).write({"active": False})
        cls.env["elite.vet.doctor.assignment"].search([]).unlink()
        # Reservations and e-mails from manual testing in the same database would
        # occupy slots and add messages; everything is rolled back at the end of the class.
        cls.env["elite.vet.reservation"].search([]).unlink()
        cls.env["mail.mail"].search([]).unlink()
        Room = cls.env["elite.vet.room"]
        cls.room1 = Room.create({"name": "Ordinace 1", "sequence": 10, "color": "teal"})
        cls.room2 = Room.create({"name": "Ordinace 2", "sequence": 20, "color": "blue"})
        cls.surgery = Room.create({"name": "Sál", "sequence": 30, "color": "purple", "online": False})
        Proc = cls.env["elite.vet.procedure"]
        cls.vacc = Proc.create({"name": "Vaccination", "duration": 15, "symbol": "V", "color": "green"})
        cls.derm = Proc.create({"name": "Dermatological problem", "duration": 30, "symbol": "D",
                                "color": "blue", "room_ids": [(6, 0, [cls.room1.id])]})
        Doctor = cls.env["elite.vet.doctor"]
        # Real doctors from the demo data would leak into the tests' "who performs the procedure".
        Doctor.search([]).write({"accepts_bookings": False})
        cls.dr_a = Doctor.create({"name": "MVDr. Alena Testová", "accepts_bookings": True})
        cls.dr_b = Doctor.create({"name": "MVDr. Bára Testová", "accepts_bookings": True})
        # Weekends and holidays reception-only (default on) would make older tests with
        # fixed dates (Oct 28) and "today + N days" depend on the calendar. Disabled;
        # the weekend and holiday tests (test_blocks) enable them themselves.
        cls.env["elite.vet.setting"].nastaveni().write({
            "booking_block_weekends": False, "booking_block_holidays": False})

    def hours(self, room, weekday, h_from, h_to, **extra):
        vals = {"room_id": room.id, "weekday": str(weekday), "hour_from": h_from, "hour_to": h_to}
        vals.update(extra)
        return self.env["elite.vet.room.hours"].create(vals)

    def assign(self, doctor, room, day, h_from, h_to, procedures=None):
        vals = {"doctor_id": doctor.id, "room_id": room.id, "date": day,
                "hour_from": h_from, "hour_to": h_to}
        if procedures:
            vals["procedure_ids"] = [(6, 0, procedures.ids)]
        return self.env["elite.vet.doctor.assignment"].create(vals)

    TZ = pytz.timezone("Europe/Prague")

    def dt(self, day, h, m=0):
        """Prague time -> naive UTC, as Odoo stores it."""
        local = self.TZ.localize(datetime(day.year, day.month, day.day, h, m))
        return local.astimezone(pytz.utc).replace(tzinfo=None)

    def reservation(self, **vals):
        base = {"kind": "reservation", "state": "confirmed", "source": "internal",
                "procedure_id": self.vacc.id, "room_id": self.room1.id,
                "contact_name": "Test Klient", "contact_email": "klient@example.cz",
                "contact_phone": "+420777000111", "pet_name": "Rex"}
        base.update(vals)
        return self.env["elite.vet.reservation"].create(base)
