from psycopg2 import IntegrityError

from odoo.exceptions import ValidationError
from odoo.tests import tagged
from odoo.tools import mute_logger

from .common import ClinicCase


@tagged("post_install", "-at_install")
class TestModels(ClinicCase):

    def test_lines_prices_and_total(self):
        record = self.Record.create({"pet_id": self.pet.id})
        self.assertEqual(record.partner_id, self.owner)
        self.assertEqual(record.user_id, self.env.user)
        self.assertEqual(record.state, "draft")
        self.assertEqual(record.currency_id, self.env.ref("base.CZK"))
        Line = self.env["elite.vet.clinical.record.line"]
        exam = Line.create({"record_id": record.id, "item_id": self.exam.id})
        vac = Line.create({"record_id": record.id, "item_id": self.vaccine.id, "quantity": 2})
        free = Line.create({"record_id": record.id, "name": "Konzultace po telefonu", "price_unit": 100})
        self.assertEqual((exam.name, exam.kind, exam.price_unit, exam.amount),
                         ("Klinické vyšetření testovací", "service", 450.0, 450.0))
        self.assertEqual((vac.kind, vac.unit, vac.amount), ("product", "dávka", 1241.0))
        self.assertEqual((free.kind, free.amount), ("other", 100.0))
        self.assertEqual(record.amount_total, 1791.0)
        vac.price_unit = 600
        self.assertEqual(record.amount_total, 1750.0)
        with self.assertRaises(ValidationError):
            free.quantity = -1

    def test_weight_goes_to_pet_when_done(self):
        record = self.Record.create({"pet_id": self.pet.id, "weight": 16.2})
        self.assertEqual(self.pet.weight, 15.0, "a draft does not change the pet")
        record.action_done()
        self.assertEqual(self.pet.weight, 16.2)
        record.weight = 16.4
        self.assertEqual(self.pet.weight, 16.4)

    def test_date_is_clinic_local(self):
        record = self.Record.create({"pet_id": self.pet.id, "start": "2026-10-14 22:30:00"})  # 00:30 in Prague
        self.assertEqual(str(record.date), "2026-10-15")

    def test_one_record_per_reservation(self):
        room = self.env["elite.vet.room"].create({"name": "Ordinace test klinika"})
        res = self.env["elite.vet.reservation"].create({
            "kind": "reservation", "state": "confirmed", "room_id": room.id, "start": "2030-01-07 09:00:00",
            "stop": "2030-01-07 09:30:00", "partner_id": self.owner.id, "pet_id": self.pet.id})
        self.Record.create({"pet_id": self.pet.id, "reservation_id": res.id})
        with self.assertRaises(IntegrityError), mute_logger("odoo.sql_db"), self.env.cr.savepoint():
            self.Record.create({"pet_id": self.pet.id, "reservation_id": res.id})
        # several records without a reservation are fine
        self.Record.create([{"pet_id": self.pet.id}, {"pet_id": self.pet.id}])

    def test_alert_summary(self):
        Alert = self.env["elite.vet.pet.alert"]
        Alert.create([{"pet_id": self.pet.id, "kind": "bites"},
                      {"pet_id": self.pet.id, "kind": "allergy", "note": "penicilin"},
                      {"pet_id": self.pet.id, "kind": "other", "note": "staré", "active": False}])
        self.assertEqual(self.pet.alert_summary, "Kouše; Alergie: penicilin")

    def test_template_edited_flag(self):
        Template = self.env["elite.vet.text.template"]
        synced = Template.create({"name": "Z WinVetu", "body": "text", "winvet_ref": 9_500_900})
        own = Template.create({"name": "Vlastní", "body": "text"})
        synced.sequence = 3
        self.assertFalse(synced.edited_in_odoo, "only name/body count as an edit")
        synced.body = "jiný text"
        self.assertTrue(synced.edited_in_odoo)
        own.body = "x"
        self.assertFalse(own.edited_in_odoo, "Odoo templates have nothing to protect")
        other = Template.create({"name": "Z WinVetu 2", "body": "text", "winvet_ref": 9_500_901})
        other.with_context(winvet_sync=True).body = "ze synchronizace"
        self.assertFalse(other.edited_in_odoo)

    def test_bundle_edited_by_line_change(self):
        Bundle = self.env["elite.vet.procedure.bundle"]
        bundle = Bundle.with_context(winvet_sync=True).create({"name": "Vakcinace pes", "winvet_ref": 9_500_910, "line_ids": [
            (0, 0, {"item_id": self.exam.id, "name": "Vyšetření", "quantity": 1}),
            (0, 0, {"item_id": self.vaccine.id, "name": "Vakcína", "quantity": 1})]})
        self.assertFalse(bundle.edited_in_odoo, "created by the sync – nothing edited yet")
        bundle.flush_recordset()
        self.assertEqual((bundle.line_count, bundle.amount), (2, 1070.5))
        bundle = bundle.with_context(winvet_sync=False)
        bundle.line_ids[0].quantity = 2
        self.assertTrue(bundle.edited_in_odoo)
