from odoo.tests import tagged

from .common import WinvetCase


@tagged("post_install", "-at_install")
class TestStatus(WinvetCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.status = cls.env["elite.vet.winvet.status"].get_status()
        cls.status.write({"winvet_version": "2603", "alert": False, "last_alert_text": False})
        cls.status.activity_ids.unlink()
        cls.manager = cls.env["res.users"].with_context(no_reset_password=True).create({
            "name": "Správce WinVet Test", "login": "winvet_manager_test",
            "groups_id": [(6, 0, [cls.env.ref("base.group_user").id,
                                  cls.env.ref("elite_vet_reservation.group_reservation_manager").id])]})

    def payload(self, **over):
        data = {"bridge_version": "1.0.0", "source": "live", "winvet_version": "2603", "ods": "13.1",
                "engine": "5.0.1", "fingerprints": {"owners": "1234567890abcdef"}, "blocked": [],
                "journal_cursor": 100, "message": None}
        data.update(over)
        return data

    def test_same_version_no_alert(self):
        self.sync.receive_status(self.payload(journal_cursor=None))
        self.assertEqual(self.status.journal_cursor, 0)
        self.sync.receive_status(self.payload())
        self.assertFalse(self.status.alert)
        self.assertFalse(self.status.activity_ids)
        self.assertIn("1234567890abcdef", self.status.fingerprints)
        self.assertTrue(self.status.last_status_at)

    def test_version_change_alert(self):
        self.sync.receive_status(self.payload(winvet_version="2610"))
        self.assertIn("aktualizován", self.status.alert)
        self.assertEqual(self.status.previous_winvet_version, "2603")
        self.assertIn(self.manager, self.status.activity_ids.user_id)
        self.assertTrue(self.status.message_ids.filtered(lambda m: "aktualizován" in (m.body or "")))

    def test_blocked_alert_once(self):
        self.sync.receive_status(self.payload(blocked=["sale_documents", "sale_lines"]))
        self.assertIn("zablokované", self.status.alert)
        self.assertEqual(self.status.blocked, "sale_documents, sale_lines")
        self.assertIn("Položky dokladů", self.status.alert)
        count = len(self.status.activity_ids)
        self.assertTrue(count)
        # the bridge reports the same state on every run: no new activities
        self.sync.receive_status(self.payload(blocked=["sale_documents", "sale_lines"]))
        self.assertEqual(len(self.status.activity_ids), count)
        self.status.action_acknowledge()
        self.assertFalse(self.status.alert)
        self.assertFalse(self.status.activity_ids)
        # still blocked on the next run: acknowledged, so no new alert
        self.sync.receive_status(self.payload(blocked=["sale_documents", "sale_lines"]))
        self.assertFalse(self.status.alert)
        self.assertFalse(self.status.activity_ids)
        # problem solved, later it comes back -> announced again
        self.sync.receive_status(self.payload())
        self.sync.receive_status(self.payload(blocked=["payments"]))
        self.assertTrue(self.status.alert)
        self.assertTrue(self.status.activity_ids)

    def test_push_counters(self):
        self.push("users", [{"id": self.ref(1), "name": "Nováková Eva", "code": "NE", "active": True}],
                  run_id="counter-run")
        line = self.status.entity_ids.filtered(lambda e: e.entity == "users")
        self.assertEqual(line.created, 1)
        self.assertEqual(line.run_id, "counter-run")
        self.assertTrue(self.status.last_push_at)


@tagged("post_install", "-at_install")
class TestSchemaChanges(WinvetCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.status = cls.env["elite.vet.winvet.status"].get_status()
        cls.status.write({"winvet_version": "2603", "alert": False, "last_alert_text": False,
                          "schema_hash": "base000000000000", "schema_baseline_hash": "base000000000000"})
        cls.status.activity_ids.unlink()
        cls.Change = cls.env["elite.vet.winvet.schema.change"]

    def payload(self, schema_hash, changes, counts):
        return {"bridge_version": "1.0.0", "source": "live", "winvet_version": "2603", "ods": "13.1",
                "engine": "5.0.1", "fingerprints": {}, "blocked": [], "journal_cursor": 1, "message": None,
                "schema_hash": schema_hash, "schema_baseline_hash": "base000000000000",
                "schema_change_counts": counts, "schema_changes": changes}

    def change(self, severity, table="PLATBA", name="X", change="added"):
        return {"object": "column", "table": table, "name": name, "change": change,
                "old": None, "new": "INTEGER", "severity": severity}

    def test_no_changes_nothing_stored(self):
        self.sync.receive_status(self.payload("base000000000000", [], {}))
        self.assertFalse(self.status.schema_change_ids)
        self.assertFalse(self.status.schema_change_summary)
        self.assertFalse(self.status.alert)

    def test_harmless_changes_logged_without_alert(self):
        self.sync.receive_status(self.payload("aaaa000000000001", [self.change("warning"), self.change("info", "LABMET")],
                                              {"warning": 1, "info": 1}))
        self.assertEqual(len(self.status.schema_change_ids), 2)
        self.assertFalse(self.status.alert)
        self.assertFalse(self.status.activity_ids)
        self.assertIn("Upozornění 1", self.status.schema_change_summary)
        self.assertTrue(self.status.message_ids.filtered(lambda m: "bez dopadu" in (m.body or "")))

    def test_breaking_change_alerts_once(self):
        changes = [self.change("breaking", name="DATUM_VRACENO", change="removed"), self.change("journal", name="TRG")]
        self.sync.receive_status(self.payload("bbbb000000000002", changes, {"breaking": 1, "journal": 1}))
        self.assertIn("PLATBA", self.status.alert)
        self.assertTrue(self.status.activity_ids)
        rows = self.status.schema_change_ids
        self.assertEqual(rows[0].severity, "breaking")
        self.assertEqual(set(rows.mapped("severity")), {"breaking", "journal"})
        # same hash reported again by the next run: no duplicates, no new activity
        count = len(self.status.activity_ids)
        self.status.action_acknowledge()
        self.sync.receive_status(self.payload("bbbb000000000002", changes, {"breaking": 1, "journal": 1}))
        self.assertEqual(self.Change.search_count([("schema_hash", "=", "bbbb000000000002")]), 2)
        self.assertFalse(self.status.alert)
        self.assertLessEqual(len(self.status.activity_ids), count)

    def test_back_to_baseline_clears_current_list(self):
        self.sync.receive_status(self.payload("cccc000000000003", [self.change("warning")], {"warning": 1}))
        self.assertTrue(self.status.schema_change_ids)
        self.sync.receive_status(self.payload("base000000000000", [], {}))
        self.assertFalse(self.status.schema_change_ids)
        self.assertEqual(self.Change.search_count([("schema_hash", "=", "cccc000000000003")]), 1)  # history kept

    def test_unknown_values_do_not_crash(self):
        weird = {"object": "something", "table": None, "name": None, "change": "renamed", "severity": "odd"}
        self.sync.receive_status(self.payload("dddd000000000004", [weird], {"odd": 1}))
        row = self.status.schema_change_ids
        self.assertEqual((row.severity, row.object_type, row.change), ("info", False, False))

    def test_old_bridge_without_schema_fields(self):
        payload = self.payload("x", [], {})
        for key in ("schema_hash", "schema_baseline_hash", "schema_change_counts", "schema_changes"):
            payload.pop(key)
        self.sync.receive_status(payload)
        self.assertEqual(self.status.schema_hash, "base000000000000")
