import json
from datetime import timedelta

from odoo.exceptions import UserError
from odoo.tests import tagged

from odoo.addons.elite_vet_clinic.models.patient_card import age_text, clinic_today

from .common import BASE, ClinicCase


@tagged("post_install", "-at_install")
class TestCardApi(ClinicCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Card = cls.env["elite.vet.clinical.record"].with_user(cls.doctor_user)

    def test_age_text(self):
        today = clinic_today()
        self.assertEqual(age_text(today - timedelta(days=7 * 366), None, today), "7 let")
        self.assertEqual(age_text(today.replace(year=today.year - 1), None, today), "1 rok")
        self.assertEqual(age_text(today.replace(year=today.year - 3), None, today), "3 roky")
        self.assertEqual(age_text(today - timedelta(days=5 * 31), None, today), "5 měsíců")
        self.assertEqual(age_text(today - timedelta(days=15), None, today), "2 týdny")
        self.assertEqual(age_text(None, today.year - 4, today), "cca 4 roky")
        self.assertIsNone(age_text(None, None, today))

    def test_open_today_record_reuses_draft(self):
        first = self.Card.open_today_record(self.pet.id)
        self.assertEqual(first["state"], "draft")
        self.assertEqual(first["doctor_id"], self.doctor.id, "doctor matched from the user's name")
        self.assertEqual(self.Card.open_today_record(self.pet.id)["id"], first["id"])
        self.assertNotEqual(self.Card.open_today_record(self.pet.id, force_new=True)["id"], first["id"])
        # a record from yesterday is not reused
        old = self.Record.create({"pet_id": self.pet.id, "start": self.today_utc(10) - timedelta(days=1)})
        self.assertNotEqual(self.Card.open_today_record(self.pet.id)["id"], old.id)

    def test_open_today_record_with_reservation(self):
        room = self.env["elite.vet.room"].create({"name": "Ordinace test karta"})
        other_doc = self.env["elite.vet.doctor"].create({"name": "MVDr. Jiná Karta-Testová"})
        res = self.env["elite.vet.reservation"].create({
            "kind": "reservation", "state": "confirmed", "room_id": room.id, "start": self.today_utc(23, 0),
            "stop": self.today_utc(23, 30), "partner_id": self.owner.id, "pet_id": self.pet.id,
            "doctor_id": other_doc.id})
        draft = self.Card.open_today_record(self.pet.id)
        data = self.Card.open_today_record(self.pet.id, res.id)
        self.assertEqual(data["id"], draft["id"], "today's draft without a reservation gets linked")
        self.assertEqual(data["reservation_id"], res.id)
        self.assertEqual(self.Card.open_today_record(self.pet.id, res.id)["id"], draft["id"])
        other_pet = self.env["elite.vet.pet"].create({"name": "Cizí", "partner_id": self.owner.id})
        with self.assertRaises(UserError):
            self.Card.open_today_record(other_pet.id, res.id)

    def test_save_record_whitelist_and_numbers(self):
        rec = self.Card.open_today_record(self.pet.id)
        data = self.Card.save_record(rec["id"], {"temperature": "38,7", "weight": 15.4, "heart_rate": "96",
                                                 "respiratory_rate": None, "record_text": "Kulhá.",
                                                 "anamnesis": "deprecated, ignored",
                                                 "state": "done", "pet_id": 1, "amount_total": 5})
        self.assertEqual((data["temperature"], data["weight"], data["heart_rate"], data["respiratory_rate"]),
                         (38.7, 15.4, 96, None))
        self.assertEqual((data["record_text"], data["state"], data["pet_id"]), ("Kulhá.", "draft", self.pet.id))
        self.assertNotIn("anamnesis", data)
        self.assertFalse(self.Record.browse(rec["id"]).anamnesis, "the deprecated fields are never written")
        with self.assertRaises(UserError):
            self.Card.save_record(rec["id"], {"temperature": "horko"})

    def test_add_item_and_bundle_merging(self):
        bundle = self.env["elite.vet.procedure.bundle"].create({"name": "Vakcinace", "line_ids": [
            (0, 0, {"item_id": self.exam.id, "name": "Vyšetření", "quantity": 1}),
            (0, 0, {"item_id": self.vaccine.id, "name": "Vakcína", "quantity": 1}),
            (0, 0, {"item_id": self.dewormer.id, "name": "Tableta", "quantity": 2, "unit": "tbl"})]})
        rec = self.Card.open_today_record(self.pet.id)
        self.Card.add_item(rec["id"], self.exam.id)
        data = self.Card.add_bundle(rec["id"], bundle.id)
        by_item = {line["item_id"]: line for line in data["lines"]}
        self.assertEqual(len(data["lines"]), 3, "the same item is merged, not duplicated")
        self.assertEqual(by_item[self.exam.id]["quantity"], 2)
        self.assertIsNone(by_item[self.exam.id]["bundle_id"], "line existed before the bundle")
        self.assertEqual(by_item[self.vaccine.id]["bundle_id"], bundle.id)
        self.assertEqual(by_item[self.dewormer.id]["quantity"], 2)
        self.assertEqual(data["amount_total"], 2 * 450 + 620.5 + 2 * 85)
        data = self.Card.add_bundle(rec["id"], bundle.id)
        self.assertEqual({line["item_id"]: line["quantity"] for line in data["lines"]},
                         {self.exam.id: 3, self.vaccine.id: 2, self.dewormer.id: 4})
        line_id = by_item[self.dewormer.id]["id"]
        data = self.Card.update_line(line_id, {"quantity": "1,5", "price_unit": 80, "item_id": self.exam.id})
        line = next(line for line in data["lines"] if line["id"] == line_id)
        self.assertEqual((line["quantity"], line["price_unit"], line["amount"], line["item_id"]),
                         (1.5, 80.0, 120.0, self.dewormer.id))
        data = self.Card.remove_line(line_id)
        self.assertEqual(len(data["lines"]), 2)
        data = self.Card.add_free_line(rec["id"], "Telefonická konzultace", 150)
        self.assertEqual(data["lines"][-1]["kind"], "other")

    def test_apply_template(self):
        """Task 32: into the one record text – at the cursor, or appended without one; never replaces."""
        tpl = self.env["elite.vet.text.template"].create({"name": "Bez nálezu", "section": "examination",
                                                          "body": "Celkový stav dobrý.\n"})
        rec = self.Card.open_today_record(self.pet.id)
        res = self.Card.apply_template(rec["id"], tpl.id)
        self.assertEqual(res, {"text": "Celkový stav dobrý.", "caret": 19})
        self.Card.save_record(rec["id"], {"record_text": "Kulhá.\nSliznice růžové.\n\n"})
        res = self.Card.apply_template(rec["id"], tpl.id)
        self.assertEqual(res["text"], "Kulhá.\nSliznice růžové.\n\nCelkový stav dobrý.")
        self.assertEqual(self.Record.browse(rec["id"]).record_text, res["text"])
        # at the cursor: after "Kulhá." (end of the first line) – on its own line, nothing lost
        res = self.Card.apply_template(rec["id"], tpl.id, 6)
        self.assertEqual(res["text"], "Kulhá.\nCelkový stav dobrý.\nSliznice růžové.\n\nCelkový stav dobrý.")
        self.assertEqual(res["text"][:res["caret"]], "Kulhá.\nCelkový stav dobrý.")
        # a position that is not a number (the old section argument) = no cursor
        res = self.Card.apply_template(rec["id"], tpl.id, "examination")
        self.assertTrue(res["text"].endswith("růžové.\n\nCelkový stav dobrý.\n\nCelkový stav dobrý."))
        self.assertFalse(self.Record.browse(rec["id"]).examination)
        with self.assertRaises(UserError):
            self.Card.apply_template(rec["id"], 999999999)

    def test_mark_done_locks_and_reopen(self):
        rec = self.Card.open_today_record(self.pet.id)
        self.Card.save_record(rec["id"], {"weight": 16.0})
        data = self.Card.mark_done(rec["id"])
        self.assertEqual((data["state"], data["editable"]), ("done", False))
        self.assertEqual(self.pet.weight, 16.0)
        with self.assertRaises(UserError):
            self.Card.add_item(rec["id"], self.exam.id)
        with self.assertRaises(UserError):
            self.Card.save_record(rec["id"], {"record_text": "pozdě"})
        # the finished record is today's record (no second draft opened automatically)
        self.assertEqual(self.Card.open_today_record(self.pet.id)["id"], rec["id"])
        with self.assertRaises(Exception):
            self.Record.with_user(self.nurse).reopen_record(rec["id"])
        self.assertEqual(self.Card.reopen_record(rec["id"])["state"], "draft")

    def test_card_data_shape(self):
        self.env["elite.vet.pet.alert"].create({"pet_id": self.pet.id, "kind": "allergy", "note": "penicilin"})
        self.env["elite.vet.text.template"].create([
            {"name": "A", "section": "anamnesis", "body": "a"}, {"name": "K", "section": "any", "body": "k"}])
        winvet_pet = self.env["elite.vet.pet"].browse(self.pet.id)
        winvet_pet.winvet_ref = BASE + 50
        self.push_ok("visits", [{"id": BASE + 60, "patient_id": BASE + 50, "date": "2026-09-01", "time": "09:30:00",
                                 "case_name": "Kulhání", "diagnosis_code": None, "diagnosis_name": "Distorze",
                                 "entered_by": None, "document_id": None, "notes": "Klid 14 dní."}])
        self.push_ok("vitals", [{"id": BASE + 70, "visit_id": BASE + 60, "time": "09:35:00", "temperature": 38.4,
                                 "heart_rate": 100, "respiratory_rate": 24, "weight": 14.2, "bp_systolic": None,
                                 "bp_diastolic": None}])
        self.push_ok("vaccinations", [{"id": BASE + 80, "patient_id": BASE + 50, "date": "2026-03-01",
                                       "next_date": "2027-03-01", "item_id": None, "item_name": "Nobivac",
                                       "quantity": 1, "unit": "dávka", "kind": 1}])
        old = self.Record.create({"pet_id": self.pet.id, "start": "2026-05-01 08:00:00", "weight": 14.0,
                                  "record_text": "Diagnóza a doporučení:\nOtitis externa\nKontrola za týden",
                                  "state": "done"})
        self.pet.weight = 15.0
        rec = self.Card.open_today_record(self.pet.id)
        self.Card.save_record(rec["id"], {"weight": 15.0})
        data = self.Card.card_data(self.pet.id)
        json.dumps(data)  # JSON-serialisable
        self.assertEqual(set(data), {"header", "timeline", "today_record", "templates", "bundles", "doctors",
                                     "permissions", "today"})
        pet = data["header"]["pet"]
        self.assertEqual((pet["name"], pet["species_label"], pet["breed"], pet["age_text"]),
                         ("Azor Klinický", "Pes", "bígl", "7 let"))
        self.assertEqual((pet["weight"], pet["weight_delta"], pet["weight_date"]),
                         (15.0, 0.8, str(clinic_today())), "today 15.0 vs 14.2 measured in WinVet")
        self.assertEqual(data["header"]["owner"]["partner_id"], self.owner.id)
        self.assertEqual(data["header"]["owner"]["phone"], "+420 602 111 987")
        self.assertEqual([a["label"] for a in data["header"]["alerts"]], ["Alergie: penicilin"])
        self.assertEqual(data["today_record"]["id"], rec["id"])
        types = [(i["type"], i["date"]) for i in data["timeline"]]
        self.assertEqual(types, [("record", str(clinic_today())), ("visit", "2026-09-01"),
                                 ("record", "2026-05-01"), ("vaccination", "2026-03-01")])
        visit = data["timeline"][1]
        self.assertEqual((visit["time"], visit["diagnosis"], visit["notes"]), ("09:30", "Distorze", "Klid 14 dní."))
        self.assertEqual(visit["vitals_summary"], "T 38,4 °C · P 100/min · D 24/min · 14,2 kg")
        self.assertEqual(data["timeline"][2]["title"], "Otitis externa", "the heading is skipped")
        self.assertEqual(data["timeline"][2]["record_text"], old.record_text)
        self.assertEqual(data["timeline"][2]["summary"], "Diagnóza a doporučení: Otitis externa Kontrola za týden")
        self.assertEqual(data["timeline"][2]["id"], old.id)
        self.assertEqual(data["timeline"][3]["next_date"], "2027-03-01")
        # task 32: one list with every template, whatever its (deprecated) section
        names = [t["name"] for t in data["templates"]]
        self.assertIn("A", names)
        self.assertIn("K", names)
        self.assertNotIn("section", data["templates"][0])
        self.assertTrue(data["permissions"]["can_write"])
        self.assertTrue(data["permissions"]["can_edit_templates"])

    def test_search_items(self):
        found = self.Card.search_items("testovací")
        names = [i["name"] for i in found]
        self.assertIn("Vakcína testovací DHPPi", names)
        self.assertNotIn("Skupina testovací", names, "groups are not billable")
        self.assertEqual([i["name"] for i in self.Card.search_items("testovací", kind="service")],
                         ["Klinické vyšetření testovací"])
        by_code = self.Card.search_items("KT2")
        self.assertEqual((by_code[0]["id"], by_code[0]["price"]), (self.vaccine.id, 620.5))

    def test_search_patients(self):
        def ids(term):
            return [p["id"] for p in self.Card.search_patients(term)]
        self.assertIn(self.pet.id, ids("Azor Klin"))
        self.assertIn(self.pet.id, ids("Klinická-Testová"))
        self.assertIn(self.pet.id, ids("602111987"), "phone, digits only")
        self.assertIn(self.pet.id, ids("777 654 321"), "mobile with spaces")
        self.assertIn(self.pet.id, ids("100555777"), "chip stored with spaces")
        self.assertEqual(ids("x"), [])
        self.Record.create({"pet_id": self.pet.id, "start": "2026-05-01 08:00:00"})
        hit = next(p for p in self.Card.search_patients("Azor Klin") if p["id"] == self.pet.id)
        self.assertEqual((hit["owner"], hit["phone"], hit["last_visit"]),
                         ("Majitelka Klinická-Testová", "777 654 321", "2026-05-01"))

    def test_my_patients_today(self):
        room = self.env["elite.vet.room"].create({"name": "Ordinace test dnes"})
        other_doc = self.env["elite.vet.doctor"].create({"name": "MVDr. Jiná Dnešní-Testová"})
        Res = self.env["elite.vet.reservation"]
        mine = Res.create({"kind": "reservation", "state": "confirmed", "room_id": room.id,
                           "start": self.today_utc(23, 0), "stop": self.today_utc(23, 20),
                           "partner_id": self.owner.id, "pet_id": self.pet.id, "doctor_id": self.doctor.id})
        theirs = Res.create({"kind": "reservation", "state": "confirmed", "room_id": room.id,
                             "start": self.today_utc(23, 30), "stop": self.today_utc(23, 50),
                             "contact_name": "Jiný Klient", "pet_name": "Micka", "doctor_id": other_doc.id})
        rec = self.Card.open_today_record(self.pet.id, mine.id)
        data = self.Card.my_patients_today()
        self.assertEqual(data["doctor"], {"id": self.doctor.id, "name": self.doctor.name})
        self.assertTrue(data["filtered_by_doctor"])
        self.assertEqual([i["reservation_id"] for i in data["items"]], [mine.id])
        item = data["items"][0]
        self.assertEqual((item["pet_id"], item["owner"], item["room"], item["record_id"], item["record_state"]),
                         (self.pet.id, self.owner.name, room.name, rec["id"], "draft"))
        self.assertEqual(item["time"], "23:00")
        # a user without a matching doctor sees all of today's reservations
        data = self.Record.with_user(self.nurse).my_patients_today()
        self.assertFalse(data["filtered_by_doctor"])
        ids = [i["reservation_id"] for i in data["items"]]
        self.assertIn(mine.id, ids)
        self.assertIn(theirs.id, ids)
        other = next(i for i in data["items"] if i["reservation_id"] == theirs.id)
        self.assertEqual((other["pet_id"], other["pet_name"]), (None, "Micka"))

    def test_open_card_buttons(self):
        action = self.pet.with_user(self.reception).action_open_patient_card()
        self.assertEqual((action["type"], action["tag"]), ("ir.actions.client", "elite_vet_clinic.patient_card"))
        self.assertEqual(action["params"], {"pet_id": self.pet.id, "reservation_id": False})
        self.assertEqual(self.owner.action_open_patient_card()["params"]["pet_id"], self.pet.id)
        self.env["elite.vet.pet"].create({"name": "Druhý", "partner_id": self.owner.id})
        multi = self.owner.action_open_patient_card()
        self.assertEqual((multi["res_model"], multi["domain"]), ("elite.vet.pet", [("partner_id", "=", self.owner.id)]))
        lonely = self.env["res.partner"].create({"name": "Bez zvířete"})
        with self.assertRaises(UserError):
            lonely.action_open_patient_card()
        room = self.env["elite.vet.room"].create({"name": "Ordinace test tlačítko"})
        res = self.env["elite.vet.reservation"].create({
            "kind": "reservation", "state": "confirmed", "room_id": room.id, "start": "2030-01-08 09:00:00",
            "stop": "2030-01-08 09:30:00", "partner_id": self.owner.id, "pet_id": self.pet.id})
        self.assertEqual(res.action_open_patient_card()["params"], {"pet_id": self.pet.id, "reservation_id": res.id})
        web = self.env["elite.vet.reservation"].create({
            "kind": "reservation", "state": "confirmed", "room_id": room.id, "start": "2030-01-08 10:00:00",
            "stop": "2030-01-08 10:30:00", "contact_name": "Webový Klient-Kartový",
            "contact_email": "web.kartovy@example.invalid", "contact_phone": "+420 700 100 200",
            "pet_name": "Bobík"})
        params = web.action_open_patient_card()["params"]
        self.assertEqual(self.env["elite.vet.pet"].browse(params["pet_id"]).name, "Bobík")
