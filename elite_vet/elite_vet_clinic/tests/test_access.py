from odoo.exceptions import AccessError
from odoo.tests import tagged

from .common import ClinicCase


@tagged("post_install", "-at_install")
class TestAccess(ClinicCase):

    def test_group_chain(self):
        reception = self.env.ref("elite_vet_reservation.group_reservation_reception")
        nurse = self.env.ref("elite_vet_clinic.group_clinic_nurse")
        doctor = self.env.ref("elite_vet_clinic.group_clinic_doctor")
        self.assertIn(reception, self.nurse.groups_id)
        self.assertIn(nurse, self.doctor_user.groups_id)
        self.assertIn(doctor, self.manager.groups_id, "manager implies doctor")

    def test_reception_reads_only(self):
        record = self.Record.create({"pet_id": self.pet.id, "anamnesis": "Kašle"})
        data = self.as_user(self.reception).card_data(self.pet.id)
        self.assertFalse(data["permissions"]["can_write"])
        self.assertEqual(data["today_record"]["id"], record.id)
        self.assertFalse(data["today_record"]["editable"])
        with self.assertRaises(AccessError):
            self.as_user(self.reception).open_today_record(self.pet.id)
        with self.assertRaises(AccessError):
            self.as_user(self.reception).save_record(record.id, {"anamnesis": "x"})
        with self.assertRaises(AccessError):
            record.with_user(self.reception).write({"anamnesis": "x"})
        with self.assertRaises(AccessError):
            self.env["elite.vet.pet.alert"].with_user(self.reception).create({"pet_id": self.pet.id, "kind": "bites"})

    def test_nurse_writes_records_not_templates(self):
        Record = self.as_user(self.nurse)
        data = Record.open_today_record(self.pet.id)
        Record.save_record(data["id"], {"anamnesis": "Zvrací od rána."})
        Record.add_item(data["id"], self.exam.id)
        self.env["elite.vet.pet.alert"].with_user(self.nurse).create({"pet_id": self.pet.id, "kind": "bites"})
        record = self.Record.browse(data["id"])
        self.assertEqual(record.anamnesis, "Zvrací od rána.")
        with self.assertRaises(AccessError):
            record.with_user(self.nurse).unlink()
        with self.assertRaises(AccessError):
            self.env["elite.vet.text.template"].with_user(self.nurse).create({"name": "x", "body": "y"})
        with self.assertRaises(AccessError):
            self.env["elite.vet.procedure.bundle"].with_user(self.nurse).create({"name": "x"})

    def test_doctor_templates_manager_unlinks(self):
        self.env["elite.vet.text.template"].with_user(self.doctor_user).create({"name": "x", "body": "y"})
        bundle = self.env["elite.vet.procedure.bundle"].with_user(self.doctor_user).create({"name": "B"})
        with self.assertRaises(AccessError):
            bundle.unlink()
        record = self.Record.create({"pet_id": self.pet.id})
        with self.assertRaises(AccessError):
            record.with_user(self.doctor_user).unlink()
        record.with_user(self.manager).unlink()
        bundle.with_user(self.manager).unlink()

    def test_merge_menu_for_managers(self):
        menu = self.env.ref("elite_vet_clinic.menu_partner_deduplicate")
        self.assertIn(self.env.ref("elite_vet_reservation.group_reservation_manager"), menu.groups_id)
        wizard = self.env["base.partner.merge.automatic.wizard"].with_user(self.manager).create({})
        self.assertTrue(wizard)
        dup = self.env["res.partner"].create({"name": "Majitelka Klinická-Testová", "email": "jiny@example.invalid"})
        self.env["elite.vet.pet"].create({"name": "Pes duplikátu", "partner_id": dup.id})
        wizard = self.env["base.partner.merge.automatic.wizard"].with_user(self.manager).with_context(
            active_model="res.partner", active_ids=[self.owner.id, dup.id]).create({})
        wizard.dst_partner_id = self.owner
        wizard.action_merge()
        self.assertFalse(dup.exists())
        self.assertEqual(len(self.owner.pet_ids), 2)
        with self.assertRaises(AccessError):
            self.env["base.partner.merge.automatic.wizard"].with_user(self.nurse).create({})
