from datetime import datetime

import pytz

from odoo.tests import TransactionCase


class ReservationCase(TransactionCase):
    """Spolecna data: tri ordinace jako na klinice a par pomocnych metod."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Vychozi data z post_init_hook (ordinace, hodiny, ukony) i cokoliv, co v DB
        # uz je, by testum podsouvalo cizi ordinace a sloty. Archivujeme to;
        # search([]) pak vraci jen fixtures z teto tridy.
        for model in ("elite.vet.room", "elite.vet.procedure"):
            cls.env[model].search([]).write({"active": False})
        cls.env["elite.vet.doctor.assignment"].search([]).unlink()
        # Rezervace a e-maily z rucniho zkouseni v teze databazi by testum
        # obsazovaly sloty a pricitaly zpravy; vse se na konci tridy vrati zpet.
        cls.env["elite.vet.reservation"].search([]).unlink()
        cls.env["mail.mail"].search([]).unlink()
        Room = cls.env["elite.vet.room"]
        cls.room1 = Room.create({"name": "Ordinace 1", "sequence": 10, "color": "teal"})
        cls.room2 = Room.create({"name": "Ordinace 2", "sequence": 20, "color": "blue"})
        cls.sal = Room.create({"name": "Sál", "sequence": 30, "color": "purple", "online": False})
        Proc = cls.env["elite.vet.procedure"]
        cls.vacc = Proc.create({"name": "Vaccination", "duration": 15, "symbol": "V", "color": "green"})
        cls.derm = Proc.create({"name": "Dermatological problem", "duration": 30, "symbol": "D",
                                "color": "blue", "room_ids": [(6, 0, [cls.room1.id])]})
        Doctor = cls.env["elite.vet.doctor"]
        cls.dr_a = Doctor.create({"name": "MVDr. Alena Testová", "prijima_rezervace": True})
        cls.dr_b = Doctor.create({"name": "MVDr. Bára Testová", "prijima_rezervace": True})

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
        """Prazsky cas -> naivni UTC, jak ho Odoo uklada."""
        local = self.TZ.localize(datetime(day.year, day.month, day.day, h, m))
        return local.astimezone(pytz.utc).replace(tzinfo=None)

    def reservation(self, **vals):
        base = {"kind": "reservation", "state": "confirmed", "source": "internal",
                "procedure_id": self.vacc.id, "room_id": self.room1.id,
                "contact_name": "Test Klient", "contact_email": "klient@example.cz",
                "contact_phone": "+420777000111", "pet_name": "Rex"}
        base.update(vals)
        return self.env["elite.vet.reservation"].create(base)
