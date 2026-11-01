from odoo.exceptions import UserError
from odoo.tests import tagged

from odoo.addons.elite_vet_clinic.models.readonly_mode import PARAM, clinic_readonly

from .common import ClinicCase


@tagged("post_install", "-at_install")
class TestReadonlyMode(ClinicCase):
    """Production while the clinic still works in WinVet: Ordinace and the cards are read-only
    for everyone but Správce rezervací; the sync and new reservations keep working."""

    def switch(self, on=True):
        self.env["ir.config_parameter"].sudo().set_param(PARAM, "True" if on else "False")

    def test_off_by_default(self):
        self.assertFalse(clinic_readonly(self.as_user(self.nurse).env))
        data = self.as_user(self.nurse).open_today_record(self.pet.id)
        self.assertTrue(data["id"])

    def test_settings_switch_stores_the_parameter(self):
        self.env["res.config.settings"].create({"elite_vet_readonly_mode": True}).execute()
        self.assertTrue(clinic_readonly(self.as_user(self.nurse).env))
        self.env["res.config.settings"].create({"elite_vet_readonly_mode": False}).execute()
        self.assertFalse(clinic_readonly(self.as_user(self.nurse).env))

    def test_patient_card_is_read_only(self):
        self.switch()
        card = self.as_user(self.doctor_user).card_data(self.pet.id)
        self.assertFalse(card["permissions"]["can_write"])
        self.assertTrue(card["permissions"]["readonly"])
        with self.assertRaises(UserError):
            self.as_user(self.doctor_user).open_today_record(self.pet.id)

    def test_records_alerts_pets_and_clients_cannot_be_changed(self):
        record = self.Record.create({"pet_id": self.pet.id})
        self.switch()
        with self.assertRaises(UserError):
            self.as_user(self.nurse).create({"pet_id": self.pet.id})
        with self.assertRaises(UserError):
            record.with_user(self.nurse).write({"record_text": "Změna"})
        with self.assertRaises(UserError):
            self.env["elite.vet.clinical.record.line"].with_user(self.nurse).create(
                {"record_id": record.id, "name": "Položka", "price_unit": 10})
        with self.assertRaises(UserError):
            self.env["elite.vet.pet.alert"].with_user(self.nurse).create({"pet_id": self.pet.id, "kind": "bites"})
        with self.assertRaises(UserError):
            self.pet.with_user(self.reception).write({"note": "Změna"})
        with self.assertRaises(UserError):
            self.owner.with_user(self.reception).write({"phone": "+420 600 000 000"})

    def test_manager_and_sync_keep_writing(self):
        self.switch()
        self.assertFalse(clinic_readonly(self.as_user(self.manager).env))
        self.pet.with_user(self.manager).write({"note": "Správce smí"})
        self.as_user(self.manager).open_today_record(self.pet.id)
        # the WinVet push runs as superuser
        self.push_ok("items", [self.item_payload(1, "service", name="Vyšetření přejmenované", price=460.0)])
        self.assertEqual(self.exam.name, "Vyšetření přejmenované")

    def test_reservations_still_create_clients_and_pets(self):
        self.switch()
        partner = self.env["res.partner"].with_user(self.reception).find_or_create_client(
            "Nová Klientka-Readonly", "nova.readonly@example.invalid", "+420 603 444 555")
        self.assertTrue(partner.is_vet_client)
        pet = self.env["elite.vet.pet"].with_user(self.reception).find_or_create(partner, "Rex Readonly", "dog")
        self.assertEqual(pet.partner_id, partner)
