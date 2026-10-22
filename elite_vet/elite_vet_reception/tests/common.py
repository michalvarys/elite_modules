from odoo.addons.elite_vet_sale.tests.common import SaleCase


class ReceptionCase(SaleCase):
    """SaleCase plus a room, reservations of today and the reception API as each role."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Reception = cls.env["elite.vet.reception"]
        cls.room = cls.env["elite.vet.room"].create({"name": "Ordinace test recepce"})
        cls.procedure = cls.env["elite.vet.procedure"].search([], limit=1)

    def api(self, user):
        return self.Reception.with_user(user)

    def new_pet(self, name, owner=None):
        return self.env["elite.vet.pet"].create({
            "name": name, "partner_id": (owner or self.owner).id, "species": "dog"})

    def reservation(self, hour, minute=0, pet=None, doctor=None, **vals):
        values = {
            "kind": "reservation", "state": "confirmed", "room_id": self.room.id,
            "start": self.today_utc(hour, minute), "stop": self.today_utc(hour, minute + 20),
            "doctor_id": (doctor or self.doctor).id,
        }
        if pet:
            values.update({"pet_id": pet.id, "partner_id": pet.partner_id.id})
        if self.procedure:
            values["procedure_id"] = self.procedure.id
        values.update(vals)
        return self.env["elite.vet.reservation"].create(values)
