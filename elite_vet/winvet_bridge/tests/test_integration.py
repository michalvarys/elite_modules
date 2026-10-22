"""Integration tests against the local WinVet analysis copy (skipped when it is not reachable).

The tests assert structure (key sets, types, counts) only - record contents are never printed.
"""

import re
import tempfile
import unittest
from pathlib import Path

from winvet_bridge import ENTITY_ORDER
from winvet_bridge.config import DEFAULT_VERIFIED_FILE
from winvet_bridge.db import ReadOnlyDatabase
from winvet_bridge.entities import ENTITY_TABLES, SPECS, all_readers
from winvet_bridge.guard import GROUP_TABLES, evaluate, load_verified, read_schema_info
from winvet_bridge.journal import BridgeState, StateStore, read_changes, read_max_cursor
from winvet_bridge.odoo_client import OdooClient, OdooError
from winvet_bridge.sync import SyncRunner, WinVetSource

from _support import FakeOdoo, db_unavailable_reason, local_firebird_config
from test_normalize_mapping import CONTRACT_KEYS


class IntegrationBase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        reason = db_unavailable_reason()
        if reason:
            raise unittest.SkipTest(reason)
        cls.db = ReadOnlyDatabase(local_firebird_config()).connect()

    @classmethod
    def tearDownClass(cls):
        cls.db.close()


class SchemaIntegrationTest(IntegrationBase):
    def test_version_and_fingerprints_match_verified_json(self):
        schema = read_schema_info(self.db)
        self.assertEqual(schema.winvet_version, "2603")
        self.assertRegex(schema.ods or "", r"^\d+\.\d+$")
        self.assertTrue(schema.engine)
        verified = load_verified(DEFAULT_VERIFIED_FILE)
        self.assertEqual(schema.fingerprints, verified["versions"]["2603"]["fingerprints"])
        guard = evaluate(schema, verified, ENTITY_TABLES)
        self.assertEqual(guard.blocked_entities, [])
        self.assertFalse(guard.journal_blocked)

    def test_all_guarded_tables_are_base_tables(self):
        tables = {t for ts in GROUP_TABLES.values() for t in ts}
        rows = self.db.query_all(
            "select trim(rdb$relation_name), rdb$view_blr is null from rdb$relations "
            "where rdb$system_flag = 0"
        )
        base = {name for name, is_table in rows if is_table}
        self.assertEqual(tables - base, set(), "fingerprinted relations must exist and be base tables")


class ReadOnlyIntegrationTest(IntegrationBase):
    def test_update_in_bridge_transaction_fails(self):
        with self.db.transaction() as tx:
            cursor = tx.manager.cursor()
            try:
                with self.assertRaises(Exception) as ctx:
                    cursor.execute("update VERZE set TEMP = TEMP")
                self.assertRegex(str(ctx.exception).lower(), r"read-only|read only")
            finally:
                cursor.close()
            # the transaction is rolled back by the context manager - never committed

    def test_insert_in_bridge_transaction_fails(self):
        with self.db.transaction() as tx:
            cursor = tx.manager.cursor()
            try:
                with self.assertRaises(Exception) as ctx:
                    cursor.execute("insert into VERZE (TEMP) values ('x')")
                self.assertRegex(str(ctx.exception).lower(), r"read-only|read only")
            finally:
                cursor.close()

    def test_query_api_refuses_writes(self):
        with self.db.transaction() as tx:
            with self.assertRaises(ValueError):
                list(tx.query("update VERZE set TEMP = TEMP"))


class EntityIntegrationTest(IntegrationBase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.readers = all_readers(cls.db, 500)
        cls.records = {name: reader.read_all() for name, reader in cls.readers.items()}

    def test_every_entity_reads_with_contract_keys_only(self):
        for name in ENTITY_ORDER:
            records = self.records[name]
            self.assertGreater(len(records), 0, name)
            for record in records:
                self.assertEqual(set(record), CONTRACT_KEYS[name], name)
                self.assertIsInstance(record["id"], int, name)
            ids = [r["id"] for r in records]
            self.assertEqual(len(ids), len(set(ids)), f"{name}: duplicate ids")

    def test_stock_layers_sum_to_totals(self):
        sums = {}
        for lot in self.records["stock_lots"]:
            sums[lot["item_id"]] = sums.get(lot["item_id"], 0.0) + lot["quantity"]
        totals = self.records["stock_totals"]
        matching = sum(1 for t in totals if abs(sums.get(t["item_id"], 0.0) - t["total"]) < 0.0005)
        self.assertGreaterEqual(matching, 490, f"{matching} of {len(totals)} items match")

    def test_v2_values(self):
        visits = self.records["visits"]
        notes = [r for r in visits if r["notes"]]
        self.assertGreater(len(notes), len(visits) * 0.8)
        bad = re.compile("[\\x00-\\x09\\x0b-\\x1f\\x7f-\\x9f\\ufffd]|TPF0|TRV[A-Z][a-z]|TableTrias|unremovable=")
        texts = [("visits", r["id"], r["notes"]) for r in notes]
        texts += [("phrases", r["id"], r["text"]) for r in self.records["phrases"] if r["text"]]
        for entity, record_id, text in texts:  # never print the text itself
            self.assertFalse(bad.search(text), f"{entity} {record_id}: control characters / RVF leftovers")
        items = self.records["items"]
        priced = [r for r in items if r["price"] is not None]
        self.assertGreater(len(priced), len(items) // 2)
        self.assertTrue(all(r["price_untaxed"] is not None for r in priced))
        visit_ids = {r["id"] for r in visits}
        linked = [r for r in self.records["vitals"] if r["visit_id"] in visit_ids]
        self.assertGreater(len(linked), len(self.records["vitals"]) * 0.9)
        bundle_ids = {r["id"] for r in self.records["bundles"]}
        self.assertTrue(all(r["bundle_id"] in bundle_ids for r in self.records["bundle_lines"]))

    def test_value_types(self):
        allowed = (str, int, float, bool, type(None))
        date_re = re.compile(r"^\d{4}-\d{2}-\d{2}$")
        datetime_re = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$")
        for name, records in self.records.items():
            for record in records:
                for key, value in record.items():
                    self.assertIsInstance(value, allowed, f"{name}.{key}")
                    if isinstance(value, str):
                        self.assertEqual(value, value.strip(), f"{name}.{key} not trimmed")
                        self.assertNotEqual(value, "", f"{name}.{key} empty string")
                    if value is not None and (key in ("date", "birth_date", "created", "registered") or
                                              key.endswith("_date")):
                        self.assertRegex(value, date_re, f"{name}.{key}")
                    if value is not None and key == "modified":
                        self.assertRegex(value, datetime_re, f"{name}.{key}")

    def test_sale_documents_types(self):
        types = {r["type"] for r in self.records["sale_documents"]}
        self.assertTrue(types <= {"UM", "PODP", "FAV", "VRAT"}, types)

    def test_read_ids(self):
        for name, reader in self.readers.items():
            sample = [r["id"] for r in self.records[name][:3]]
            got = reader.read_ids(sample + [-987654])
            self.assertEqual(sorted(r["id"] for r in got), sorted(sample), name)
            self.assertEqual(reader.read_ids([]), [])
            for record in got:
                self.assertEqual(set(record), CONTRACT_KEYS[name])

    def test_read_ids_large_list_is_chunked(self):
        reader = self.readers["sale_lines"]
        ids = [r["id"] for r in self.records["sale_lines"]][:1200]
        self.assertEqual(len(reader.read_ids(ids)), len(ids))

    def test_executed_sql_is_safe(self):
        # run every reader + guard + journal at least once (done in setUpClass and other tests)
        read_schema_info(self.db)
        read_max_cursor(self.db)
        statements = ReadOnlyDatabase.executed_sql
        self.assertTrue(statements)
        for sql in statements:
            self.assertNotRegex(sql.upper(), r"\bREGISTRACE\b")
            self.assertNotRegex(sql.upper(), r"\b(RODNE_CISLO|HASH|KOD_CVK)\b")
            self.assertNotRegex(sql.upper(), r"SELECT\s+\*|EXECUTE|PROCEDURE")
        # reader tables are real tables (not views / selectable procedures)
        rows = self.db.query_all(
            "select trim(rdb$relation_name) from rdb$relations where rdb$view_blr is null"
        )
        base = {r[0] for r in rows}
        for spec in SPECS.values():
            for table in spec.tables:
                self.assertIn(table, base)
            used = set(re.findall(r"\b(?:from|join)\s+([A-Z_0-9$]+)", spec.sql, re.IGNORECASE))
            self.assertEqual({u.upper() for u in used}, set(spec.tables), spec.name)


class JournalSyncIntegrationTest(IntegrationBase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = StateStore(Path(self.tmp.name) / "state.json")

    def tearDown(self):
        self.tmp.cleanup()

    def runner(self, client=None):
        return SyncRunner(WinVetSource(self.db, 500), self.store, load_verified(DEFAULT_VERIFIED_FILE),
                          batch_size=500, source_kind="backup", client=client)

    def test_journal_changes(self):
        top = read_max_cursor(self.db)
        self.assertGreater(top, 0)
        changes = read_changes(self.db, top - 2000, top)
        self.assertGreater(changes.entries, 0)
        for entity, ids in list(changes.changed.items()) + list(changes.deleted.items()):
            self.assertIn(entity, ENTITY_ORDER)
            self.assertTrue(all(isinstance(i, int) for i in ids))
            self.assertTrue(changes.changed.get(entity, set()).isdisjoint(changes.deleted.get(entity, set())))
        self.assertEqual(read_changes(self.db, top, top).entries, 0)

    def test_dry_run_full_counts(self):
        report = self.runner().run(full=True, dry_run=True)
        counts = report.counts()
        for entity in ("owners", "patients", "sale_lines"):
            self.assertGreater(counts[entity], 0, entity)
        self.assertEqual(set(counts), set(ENTITY_ORDER))
        self.assertFalse(self.store.path.exists(), "dry run must not write state")

    def test_full_then_incremental_with_fake_odoo(self):
        top = read_max_cursor(self.db)
        with FakeOdoo() as odoo:
            client = OdooClient(odoo.url, odoo.api_key, timeout=30, retries=0)
            report = self.runner(client).run()
            self.assertEqual(report.mode, "full")
            self.assertEqual(odoo.calls[0]["path"], "/winvet/api/v1/status")
            self.assertTrue(all(len(p["records"]) <= 500 for p in odoo.pushes()))
        self.assertEqual(self.store.load().journal_cursor, top)

        # rewind the cursor -> incremental run replays the last journal entries
        self.store.save(BridgeState(journal_cursor=top - 300, last_full_date="2026-01-01"))
        with FakeOdoo() as odoo:
            client = OdooClient(odoo.url, odoo.api_key, timeout=30, retries=0)
            report = self.runner(client).run()
            pushes = odoo.pushes()
        self.assertEqual(report.mode, "incremental")
        self.assertGreater(report.journal_entries, 0)
        self.assertTrue(any(p["mode"] == "incremental" for p in pushes))
        self.assertEqual(self.store.load().journal_cursor, top)

    def test_cursor_kept_when_push_fails(self):
        top = read_max_cursor(self.db)
        self.store.save(BridgeState(journal_cursor=top - 300))
        with FakeOdoo() as odoo:
            odoo.fail_push_at = 1
            client = OdooClient(odoo.url, odoo.api_key, timeout=30, retries=0)
            with self.assertRaises(OdooError):
                self.runner(client).run()
        self.assertEqual(self.store.load().journal_cursor, top - 300)


if __name__ == "__main__":
    unittest.main()
