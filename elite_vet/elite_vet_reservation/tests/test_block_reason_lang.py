"""Request 25. 10.: a block reason typed in any UI language is saved and shown to everyone."""
from datetime import date

from odoo.tests import Form, tagged

from .common import ReservationCase

THU = date(2026, 10, 15)


@tagged("post_install", "-at_install")
class TestBlockReasonLanguage(ReservationCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        for code in ("de_DE", "cs_CZ"):
            cls.env["res.lang"]._activate_lang(code)
        Users = cls.env["res.users"].with_context(no_reset_password=True)
        groups = [cls.env.ref("base.group_user").id,
                  cls.env.ref("elite_vet_reservation.group_reservation_manager").id]
        cls.manager_de = Users.create({"name": "T22 Manager DE", "login": "t22_manager_de", "lang": "de_DE",
                                       "groups_id": [(6, 0, groups)]})
        cls.manager_en = Users.create({"name": "T22 Manager EN", "login": "t22_manager_en", "lang": "en_US",
                                       "groups_id": [(6, 0, groups)]})

    def test_field_is_not_translatable(self):
        self.assertFalse(self.env["elite.vet.reservation"]._fields["block_reason"].translate)

    def test_block_created_in_german_form(self):
        Model = self.env["elite.vet.reservation"].with_user(self.manager_de).with_context(
            lang="de_DE", default_kind="block", default_state="confirmed")
        with Form(Model) as form:
            form.block_reason = "Mittagspause T22"
            form.block_room_ids.clear()
            form.block_room_ids.add(self.room1)
            form.start = self.dt(THU, 12)
            form.stop = self.dt(THU, 13)
        block = form.record
        self.assertEqual(block.room_id, self.room1)
        for lang in ("cs_CZ", "en_US", "de_DE"):
            self.assertEqual(block.with_context(lang=lang).block_reason, "Mittagspause T22", lang)
        self.assertEqual(block.name, "Mittagspause T22")
        # the board (clinic language) shows it
        events = self.env["elite.vet.reservation"].board_data(THU.isoformat())["events"]
        self.assertIn("Mittagspause T22", [e["name"] for e in events if e["id"] == block.id])

    def test_edit_in_english_reaches_czech(self):
        block = self.env["elite.vet.reservation"].with_context(lang="cs_CZ").create({
            "kind": "block", "state": "confirmed", "block_reason": "Porada T22", "block_scope": "full",
            "room_id": self.room1.id, "start": self.dt(THU, 15), "stop": self.dt(THU, 16)})
        block.with_user(self.manager_en).with_context(lang="en_US").write({"block_reason": "Meeting T22"})
        self.assertEqual(block.with_context(lang="cs_CZ").block_reason, "Meeting T22")
        self.assertEqual(block.name, "Meeting T22")
        block.flush_recordset()
        self.env.cr.execute("SELECT block_reason FROM elite_vet_reservation WHERE id = %s", [block.id])
        self.assertEqual(self.env.cr.fetchone()[0], "Meeting T22")   # plain text, not jsonb
