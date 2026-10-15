"""Table-level schema change detection (schema_watch) and the used-columns fingerprints."""

from __future__ import annotations

import copy
import json
import unittest

from winvet_bridge.config import DEFAULT_SCHEMA_BASELINE_FILE
from winvet_bridge.entities import SPECS, used_columns
from winvet_bridge.guard import used_column_map
from winvet_bridge.journal import JOURNAL_TABLES
from winvet_bridge.schema_watch import classify, compare, diff, snapshot_hash

from _support import db_unavailable_reason, local_firebird_config


def _snapshot():
    snap = {
        "tables": {
            "PLATBA": {
                "view": False, "format": 1, "pk": ["ID_PLATBA"], "unique": {}, "fks": {}, "indexes": {},
                "columns": {
                    "ID_PLATBA": {"type": "INTEGER", "not_null": True, "default": None, "computed": None},
                    "ZAPLACENO": {"type": "DOUBLE PRECISION", "not_null": False, "default": None, "computed": None},
                    "FORMA_UHRADY": {"type": "VARCHAR(10)", "not_null": False, "default": None, "computed": None},
                    "UNUSED": {"type": "INTEGER", "not_null": False, "default": None, "computed": None},
                },
                "triggers": {
                    "TRG_PLATBA_ZURNAL_I": {"type": 2, "inactive": False, "source": "aaa", "journal": True},
                    "TRG_PLATBA_OTHER": {"type": 2, "inactive": False, "source": "bbb", "journal": False},
                },
            },
            "LABMET": {
                "view": False, "format": 1, "pk": ["ID"], "unique": {}, "fks": {}, "indexes": {}, "triggers": {},
                "columns": {"ID": {"type": "INTEGER", "not_null": True, "default": None, "computed": None}},
            },
        },
        "procedures": {"P1": "x"},
        "views": {},
        "db_triggers": {},
    }
    snap["hash"] = snapshot_hash(snap)
    return snap


USED = {"PLATBA": {"ID_PLATBA", "ZAPLACENO", "FORMA_UHRADY"}}


def _changes(mutate):
    base = _snapshot()
    cur = copy.deepcopy(base)
    mutate(cur)
    cur["hash"] = snapshot_hash(cur)
    return compare(cur, base, USED, JOURNAL_TABLES).changes


class DiffClassifyTest(unittest.TestCase):
    def test_identical_snapshots_have_no_changes(self):
        snap = _snapshot()
        report = compare(snap, copy.deepcopy(snap), USED, JOURNAL_TABLES)
        self.assertEqual(report.changes, [])
        self.assertIsNone(report.summary())

    def test_missing_baseline(self):
        report = compare(_snapshot(), None, USED, JOURNAL_TABLES)
        self.assertIsNone(report.baseline_hash)
        self.assertIn("approve", report.summary())

    def test_used_column_removed_is_breaking(self):
        (c,) = _changes(lambda s: s["tables"]["PLATBA"]["columns"].pop("ZAPLACENO"))
        self.assertEqual((c.object, c.table, c.name, c.change, c.severity),
                         ("column", "PLATBA", "ZAPLACENO", "removed", "breaking"))

    def test_used_column_type_change_is_breaking_length_change_warning(self):
        def mutate(s):
            s["tables"]["PLATBA"]["columns"]["ZAPLACENO"]["type"] = "NUMERIC(15,2)"
            s["tables"]["PLATBA"]["columns"]["FORMA_UHRADY"]["type"] = "VARCHAR(20)"
        sev = {c.name: c.severity for c in _changes(mutate)}
        self.assertEqual(sev, {"ZAPLACENO": "breaking", "FORMA_UHRADY": "warning"})

    def test_new_column_in_read_table_is_warning(self):
        (c,) = _changes(lambda s: s["tables"]["PLATBA"]["columns"].__setitem__(
            "NEW", {"type": "INTEGER", "not_null": False, "default": None, "computed": None}))
        self.assertEqual((c.change, c.severity), ("added", "warning"))

    def test_unused_column_change_in_read_table_is_warning(self):
        (c,) = _changes(lambda s: s["tables"]["PLATBA"]["columns"].pop("UNUSED"))
        self.assertEqual(c.severity, "warning")

    def test_journal_trigger_change_is_journal(self):
        (c,) = _changes(lambda s: s["tables"]["PLATBA"]["triggers"]["TRG_PLATBA_ZURNAL_I"].__setitem__("inactive", True))
        self.assertEqual((c.object, c.severity), ("trigger", "journal"))

    def test_other_trigger_change_is_warning(self):
        (c,) = _changes(lambda s: s["tables"]["PLATBA"]["triggers"]["TRG_PLATBA_OTHER"].__setitem__("source", "ccc"))
        self.assertEqual(c.severity, "warning")

    def test_unread_table_changes_and_new_objects_are_info(self):
        def mutate(s):
            s["tables"]["LABMET"]["columns"].pop("ID")
            s["tables"]["NEW_TABLE"] = copy.deepcopy(s["tables"]["LABMET"])
            s["procedures"]["P1"] = "y"
        changes = _changes(mutate)
        self.assertTrue(changes)
        self.assertEqual({c.severity for c in changes}, {"info"})

    def test_read_table_removed_is_breaking(self):
        (c,) = _changes(lambda s: s["tables"].pop("PLATBA"))
        self.assertEqual((c.object, c.change, c.severity), ("table", "removed", "breaking"))

    def test_report_payload_orders_by_severity(self):
        def mutate(s):
            s["procedures"]["P1"] = "y"
            s["tables"]["PLATBA"]["columns"].pop("ZAPLACENO")
        base = _snapshot()
        cur = copy.deepcopy(base)
        mutate(cur)
        cur["hash"] = snapshot_hash(cur)
        report = compare(cur, base, USED, JOURNAL_TABLES)
        payload = report.payload()
        self.assertEqual(payload[0]["severity"], "breaking")
        self.assertEqual(report.counts, {"breaking": 1, "info": 1})
        json.dumps(payload)  # JSON-serialisable for the status call


class UsedColumnsTest(unittest.TestCase):
    def test_every_entity_table_has_used_columns(self):
        used = used_columns()
        for spec in SPECS.values():
            for table in spec.tables:
                self.assertTrue(used.get(table), f"{spec.name}: no columns derived for {table}")

    def test_ids_are_included(self):
        used = used_columns()
        self.assertIn("ID_PARTNER", used["PARTNER"])
        self.assertIn("ID_DOKLAD_POLOZKA", used["DOKLAD_POLOZKA_UM"])

    def test_sensitive_columns_are_never_used(self):
        flat = {c for cols in used_column_map().values() for c in cols}
        for forbidden in ("REGISTRACE", "RODNE_CISLO", "HASH", "KOD_CVK"):
            self.assertNotIn(forbidden, flat)
        self.assertIn("DEKURS", used_column_map()["DENNI_ZAZNAM"])  # allowed since contract v2

    def test_journal_and_version_columns_are_guarded(self):
        used = used_column_map()
        self.assertEqual(used["VERZE"], {"VERZE"})
        self.assertIn("ID_ZAZNAM", used["ZURNAL"])
        self.assertIn("IDKEY", used["ZURNAL"])
        self.assertTrue({"ID_VARIANTA", "ID_CENIK", "CENA", "CENA_S_DPH"} <= used["VARIANTA_CENIK"])


class SchemaWatchIntegrationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        reason = db_unavailable_reason()
        if reason:
            raise unittest.SkipTest(reason)

    def test_local_copy_matches_shipped_baseline(self):
        from winvet_bridge.db import ReadOnlyDatabase
        from winvet_bridge.schema_watch import load_baseline, read_snapshot

        baseline = load_baseline(DEFAULT_SCHEMA_BASELINE_FILE)
        self.assertIsNotNone(baseline, "schema_baseline.json must be shipped with the package")
        with ReadOnlyDatabase(local_firebird_config()) as db:
            snapshot = read_snapshot(db)
        report = compare(snapshot, baseline, used_column_map(), JOURNAL_TABLES)
        self.assertEqual([c.describe() for c in report.changes], [])
        self.assertGreater(len(snapshot["tables"]), 200)
        self.assertTrue(any(t["triggers"] for t in snapshot["tables"].values()))


if __name__ == "__main__":
    unittest.main()
