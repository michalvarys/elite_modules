"""Request 25. 10.: internal notes of a visit – the reception's note for the room."""
from odoo.exceptions import AccessError, UserError
from odoo.tests import tagged

from .common import ReceptionCase


@tagged("post_install", "-at_install")
class TestReceptionNote(ReceptionCase):

    def test_check_in_with_a_note(self):
        reception = self.api(self.reception)
        pet = self.new_pet("Poznámkový")
        res = self.reservation(9, 0, pet=pet)
        data = reception.check_in(res.id, "Jana", "  Klient spěchá, platí kartou  ")
        record = self.Record.browse(data["record_id"])
        self.assertEqual(record.reception_note, "Klient spěchá, platí kartou")
        self.assertEqual(data["reception_note"], "Klient spěchá, platí kartou")
        # Dnes, the room screen, Moji pacienti dnes and the patient card show it
        waiting = [w for w in reception.today_data()["waiting"] if w["record_id"] == record.id]
        self.assertEqual(waiting[0]["reception_note"], "Klient spěchá, platí kartou")
        items = [i for col in reception.room_board()["columns"] for items in col["sections"].values()
                 for i in items if i["record_id"] == record.id]
        self.assertEqual(items[0]["reception_note"], "Klient spěchá, platí kartou")
        mine = [i for i in self.as_user(self.nurse).my_patients_today()["items"] if i["record_id"] == record.id]
        self.assertEqual(mine[0]["reception_note"], "Klient spěchá, platí kartou")
        self.assertEqual(self.as_user(self.nurse).get_record(record.id)["reception_note"],
                         "Klient spěchá, platí kartou")
        # a second check-in without a note keeps it
        reception.check_in(res.id, "Jana")
        self.assertEqual(record.reception_note, "Klient spěchá, platí kartou")
        # tracked in the chatter (tests run with tracking disabled: the field flag)
        self.assertTrue(self.Record._fields["reception_note"].tracking)

    def test_check_in_without_a_note(self):
        res = self.reservation(9, 30, pet=self.new_pet("Bezpoznámkový"))
        data = self.api(self.reception).check_in(res.id, "Jana", "   ")
        self.assertFalse(self.Record.browse(data["record_id"]).reception_note)
        self.assertIsNone(data["reception_note"])

    def test_walk_in_with_a_note(self):
        pet = self.new_pet("Neobjednaný")
        data = self.api(self.reception).walk_in(pet.id, False, "Jana", False, "Kouše, opatrně")
        self.assertEqual(self.Record.browse(data["record_id"]).reception_note, "Kouše, opatrně")
        walk_ins = [i for i in self.as_user(self.nurse).my_patients_today()["items"]
                    if i.get("record_id") == data["record_id"]]
        self.assertEqual(walk_ins[0]["reception_note"], "Kouše, opatrně")

    def test_edit_and_clear_the_note(self):
        reception = self.api(self.reception)
        pet = self.new_pet("Upravovaný")
        data = reception.walk_in(pet.id, False, "Jana")
        record = self.Record.browse(data["record_id"])
        self.assertEqual(reception.set_reception_note(record.id, "Přinesl vzorek moči")["reception_note"],
                         "Přinesl vzorek moči")
        reception.set_reception_note(record.id, "")
        self.assertFalse(record.reception_note)
        # a finished visit keeps its note as it was
        reception.set_reception_note(record.id, "Pozdě")
        nurse = self.as_user(self.nurse)
        nurse.mark_done(record.id)
        with self.assertRaises(UserError):
            reception.set_reception_note(record.id, "Jiná")
        self.assertEqual(record.reception_note, "Pozdě")
        with self.assertRaises(UserError):
            reception.set_reception_note(0, "x")

    def test_rights(self):
        record = self.Record.browse(self.api(self.reception).walk_in(self.new_pet("Právní").id)["record_id"])
        outsider = self.env["res.users"].create({
            "name": "Bez recepce T22", "login": "t22_no_reception",
            "groups_id": [(6, 0, [self.env.ref("base.group_user").id])]})
        with self.assertRaises(AccessError):
            self.api(outsider).set_reception_note(record.id, "x")

    def test_not_on_the_quotation(self):
        """The note is internal: nothing of it reaches the quotation (receipt / invoice)."""
        pet = self.new_pet("Účtenkový")
        data = self.api(self.reception).walk_in(pet.id, False, "Jana", False, "TAJNA-POZNAMKA-T22")
        nurse = self.as_user(self.nurse)
        nurse.add_item(data["record_id"], self.exam.id)
        nurse.mark_done(data["record_id"])
        order = self.Record.browse(data["record_id"]).sale_order_id
        self.assertTrue(order)
        texts = " ".join(filter(None, [order.note and str(order.note), order.client_order_ref,
                                       *order.order_line.mapped("name")]))
        self.assertNotIn("TAJNA-POZNAMKA-T22", texts)


@tagged("post_install", "-at_install")
class TestRoomNote(ReceptionCase):
    """Request 25. 10.: the room's internal note for the reception (Poznámka pro recepci)."""

    def finished_visit(self, name, note=None):
        reception = self.api(self.reception)
        record_id = reception.walk_in(self.new_pet(name).id, False, "Jana")["record_id"]
        nurse = self.as_user(self.nurse)
        nurse.add_item(record_id, self.exam.id)
        if note is not None:
            self.assertEqual(nurse.save_room_note(record_id, note)["room_note"], note.strip())
        nurse.mark_done(record_id)
        return self.Record.browse(record_id)

    def test_note_reaches_the_till(self):
        record = self.finished_visit("Platící", "  Platí převodem, fakturu na firmu  ")
        self.assertEqual(record.room_note, "Platí převodem, fakturu na firmu")
        reception = self.api(self.reception)
        bills = [b for b in reception.today_data()["to_pay"] if b["record_id"] == record.id]
        self.assertEqual(bills[0]["room_note"], "Platí převodem, fakturu na firmu")
        owner_bills = [b for b in reception.owner_data(record.partner_id.id)["open_bills"]
                       if b["record_id"] == record.id]
        self.assertEqual(owner_bills[0]["room_note"], "Platí převodem, fakturu na firmu")
        # not on the quotation (receipt / invoice)
        order = record.sale_order_id
        texts = " ".join(filter(None, [order.note and str(order.note), order.client_order_ref,
                                       *order.order_line.mapped("name")]))
        self.assertNotIn("převodem", texts)

    def test_editable_after_done_not_after_cancel(self):
        record = self.finished_visit("Doplňovaný")
        self.assertEqual(record.state, "done")
        nurse = self.as_user(self.nurse)
        data = nurse.save_room_note(record.id, "Doplatí zítra")
        self.assertEqual(data["room_note"], "Doplatí zítra")
        self.assertTrue(data["room_note_editable"])
        nurse.save_room_note(record.id, "  ")
        self.assertFalse(record.room_note)
        cancelled = self.Record.create({"pet_id": self.new_pet("Zrušený").id, "state": "cancelled"})
        with self.assertRaises(UserError):
            nurse.save_room_note(cancelled.id, "x")
        self.assertFalse(nurse.get_record(cancelled.id)["room_note_editable"])

    def test_reception_cannot_write_it(self):
        record = self.finished_visit("Čtený", "Jen pro recepci")
        with self.assertRaises(AccessError):
            self.as_user(self.reception).save_room_note(record.id, "jiná")
        data = self.as_user(self.reception).get_record(record.id)
        self.assertEqual(data["room_note"], "Jen pro recepci")
        self.assertFalse(data["room_note_editable"])
        self.assertTrue(self.Record._fields["room_note"].tracking)
