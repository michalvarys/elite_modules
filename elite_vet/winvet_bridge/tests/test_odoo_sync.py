"""Unit tests with a fake Odoo HTTP server and a fake WinVet source."""

import datetime as dt
import tempfile
import unittest
from pathlib import Path

from winvet_bridge import ENTITY_ORDER
from winvet_bridge.cli import should_run_full
from winvet_bridge.guard import GROUPS, SchemaInfo
from winvet_bridge.journal import BridgeState, StateStore, collect_changes
from winvet_bridge.odoo_client import OdooClient, OdooError, OdooTransportError
from winvet_bridge.sync import SyncRunner

from _support import FakeOdoo

FPS = {g: f"{i:016x}" for i, g in enumerate(GROUPS)}
VERIFIED = {"versions": {"2603": {"fingerprints": dict(FPS)}}}


class FakeSource:
    """In-memory WinVet: ``data[entity] = {id: record}``, journal rows (ID_ZURNAL, TABLE, ID, ACTION)."""

    def __init__(self, sizes=None, journal=(), fingerprints=None, version="2603"):
        sizes = sizes or {e: 3 for e in ENTITY_ORDER}
        self.data = {e: {i: {"id": i} for i in range(1, sizes.get(e, 0) + 1)} for e in ENTITY_ORDER}
        self.journal = list(journal)
        self.fingerprints = dict(fingerprints or FPS)
        self.version = version
        self.read_log = []

    def schema_info(self):
        return SchemaInfo(self.version, "13.1", "5.0.1", dict(self.fingerprints))

    def journal_max(self):
        return max((r[0] for r in self.journal), default=0)

    def journal_changes(self, after, upto):
        return collect_changes([r for r in self.journal if after < r[0] <= upto], after, upto)

    def read_all(self, entity):
        self.read_log.append((entity, "all"))
        return list(self.data[entity].values())

    def read_ids(self, entity, ids):
        self.read_log.append((entity, tuple(ids)))
        return [self.data[entity][i] for i in ids if i in self.data[entity]]


class OdooClientTest(unittest.TestCase):
    def test_auth_header_and_jsonrpc_body(self):
        with FakeOdoo("k1") as odoo:
            client = OdooClient(odoo.url, "k1", timeout=5, retries=0)
            self.assertEqual(client.status({"a": 1}), {"ok": True})
            call = odoo.calls[0]
            self.assertEqual(call["path"], "/winvet/api/v1/status")
            self.assertEqual(call["auth"], "Bearer k1")
            self.assertEqual(call["body"]["jsonrpc"], "2.0")
            self.assertEqual(call["body"]["params"], {"a": 1})
            self.assertNotIn("k1", repr(client))

    def test_ok_false_raises(self):
        with FakeOdoo("right") as odoo:
            client = OdooClient(odoo.url, "wrong", timeout=5, retries=0)
            with self.assertRaisesRegex(OdooError, "unauthorized"):
                client.push({"entity": "owners"})

    def test_retries_on_http_503(self):
        sleeps = []
        with FakeOdoo() as odoo:
            odoo.http_errors = [503, 502]
            client = OdooClient(odoo.url, odoo.api_key, timeout=5, retries=3, backoff=0.5, sleep=sleeps.append)
            self.assertTrue(client.status({})["ok"])
            self.assertEqual(len(odoo.calls), 3)
        self.assertEqual(sleeps, [0.5, 1.0])

    def test_no_retry_on_http_4xx(self):
        with FakeOdoo() as odoo:
            odoo.http_errors = [404]
            client = OdooClient(odoo.url, odoo.api_key, timeout=5, retries=3, sleep=lambda s: None)
            with self.assertRaises(OdooError):
                client.status({})
            self.assertEqual(len(odoo.calls), 1)

    def test_network_error_retries_then_fails(self):
        with FakeOdoo() as odoo:
            url = odoo.url
        sleeps = []
        client = OdooClient(url, "k", timeout=2, retries=2, backoff=1, sleep=sleeps.append)
        with self.assertRaises(OdooTransportError):
            client.status({})
        self.assertEqual(sleeps, [1, 2])


class SyncRunnerTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = StateStore(Path(self.tmp.name) / "state.json")

    def tearDown(self):
        self.tmp.cleanup()

    def runner(self, source, odoo=None, batch_size=2):
        client = OdooClient(odoo.url, odoo.api_key, timeout=5, retries=0) if odoo else None
        return SyncRunner(source, self.store, VERIFIED, batch_size=batch_size, source_kind="backup", client=client)

    def test_first_run_is_full_status_first_and_contract_order(self):
        source = FakeSource(journal=[(100, "PARTNER", 1, "U"), (120, "PACIENT", 2, "U")])
        with FakeOdoo() as odoo:
            report = self.runner(source, odoo).run()
            paths = [c["path"].rsplit("/", 1)[1] for c in odoo.calls]
            pushes = odoo.pushes()
            status = odoo.calls[0]["body"]["params"]
        self.assertEqual(report.mode, "full")
        self.assertEqual(paths[0], "status")
        self.assertNotIn("status", paths[1:])
        self.assertEqual(status["source"], "backup")
        self.assertEqual(status["winvet_version"], "2603")
        self.assertEqual(status["blocked"], [])
        self.assertIsNone(status["journal_cursor"])
        self.assertEqual(set(status["fingerprints"]), set(GROUPS))
        entities = [p["entity"] for p in pushes]
        self.assertEqual(sorted(set(entities), key=entities.index), list(ENTITY_ORDER))
        self.assertEqual(entities, sorted(entities, key=ENTITY_ORDER.index))
        owners = [p for p in pushes if p["entity"] == "owners"]
        self.assertEqual([(p["batch"], p["batches"], len(p["records"])) for p in owners], [(1, 2, 2), (2, 2, 1)])
        self.assertTrue(all(p["mode"] == "full" and p["run_id"] == report.run_id for p in pushes))
        self.assertEqual(self.store.load().journal_cursor, 120)
        self.assertEqual(self.store.load().last_full_date, dt.date.today().isoformat())

    def test_incremental_run(self):
        source = FakeSource(journal=[(100, "PARTNER", 1, "U")])
        self.store.save(BridgeState(journal_cursor=100))
        source.journal += [(101, "PARTNER", 2, "U"), (102, "PARTNER", 3, "D"), (103, "DOKLAD_POLOZKA", 99, "U"),
                           (104, "DOKLAD_POLOZKA", 1, "U")]
        with FakeOdoo() as odoo:
            report = self.runner(source, odoo).run()
            pushes = odoo.pushes()
        self.assertEqual(report.mode, "incremental")
        by_entity = {}
        for p in pushes:
            by_entity.setdefault(p["entity"], []).append(p)
        # users and contacts always full, others only when changed
        self.assertEqual(set(by_entity), {"users", "contacts", "owners", "sale_lines"})
        self.assertTrue(all(p["mode"] == "full" for p in by_entity["users"] + by_entity["contacts"]))
        owners = by_entity["owners"][0]
        self.assertEqual((owners["mode"], owners["records"], owners["deleted"]), ("incremental", [{"id": 2}], [3]))
        # id 99 is not in DOKLAD_POLOZKA_UM -> ignored
        self.assertEqual(by_entity["sale_lines"][0]["records"], [{"id": 1}])
        self.assertEqual(self.store.load().journal_cursor, 104)

    def test_cursor_not_advanced_on_failure(self):
        source = FakeSource(journal=[(100, "PARTNER", 1, "U")])
        self.store.save(BridgeState(journal_cursor=50, last_full_date="2000-01-01"))
        with FakeOdoo() as odoo:
            odoo.fail_push_at = 2
            with self.assertRaises(OdooError):
                self.runner(source, odoo).run(full=True)
        state = self.store.load()
        self.assertEqual(state.journal_cursor, 50)
        self.assertEqual(state.last_full_date, "2000-01-01")

    def test_dry_run_makes_no_http_and_keeps_state(self):
        source = FakeSource(journal=[(7, "PARTNER", 1, "U")])
        report = self.runner(source, None).run(dry_run=True)
        self.assertEqual(report.counts()["owners"], 3)
        self.assertFalse(self.store.path.exists())

    def test_blocked_entities_not_read_and_full_after_unblock(self):
        fps = dict(FPS, sales="ffffffffffffffff")
        source = FakeSource(journal=[(10, "PLATBA", 1, "U")], fingerprints=fps)
        self.store.save(BridgeState(journal_cursor=5))
        with FakeOdoo() as odoo:
            report = self.runner(source, odoo).run()
            status = odoo.calls[0]["body"]["params"]
            pushed = {p["entity"] for p in odoo.pushes()}
        self.assertEqual(status["blocked"], ["sale_documents", "sale_lines", "payments"])
        self.assertIn("sales", status["message"])
        self.assertTrue(pushed.isdisjoint({"sale_documents", "sale_lines", "payments"}))
        self.assertFalse(any(e in ("sale_documents", "sale_lines", "payments") for e, _ in source.read_log))
        self.assertEqual([e.entity for e in report.entities if e.blocked], status["blocked"])
        state = self.store.load()
        self.assertEqual(state.journal_cursor, 10)
        self.assertEqual(state.pending_full, ["sale_documents", "sale_lines", "payments"])
        # schema approved again -> those entities are pushed in full once
        source.fingerprints = dict(FPS)
        source.journal.append((11, "PARTNER", 1, "U"))
        with FakeOdoo() as odoo:
            self.runner(source, odoo).run()
            modes = {(p["entity"], p["mode"]) for p in odoo.pushes()}
        self.assertIn(("payments", "full"), modes)
        self.assertIn(("owners", "incremental"), modes)
        self.assertEqual(self.store.load().pending_full, [])

    def test_unverified_version_blocks_all_and_keeps_cursor(self):
        source = FakeSource(journal=[(10, "PARTNER", 1, "U")], version="2700")
        self.store.save(BridgeState(journal_cursor=5))
        with FakeOdoo() as odoo:
            self.runner(source, odoo).run()
            self.assertEqual(len(odoo.calls), 1)
            self.assertEqual(odoo.calls[0]["body"]["params"]["blocked"], list(ENTITY_ORDER))
        self.assertEqual(source.read_log, [])
        self.assertEqual(self.store.load().journal_cursor, 5)

    def test_journal_restart_forces_full(self):
        source = FakeSource(journal=[(10, "PARTNER", 1, "U")])
        self.store.save(BridgeState(journal_cursor=500))
        report = self.runner(source).run(dry_run=True)
        self.assertEqual(report.mode, "full")
        self.assertIn("restarted", report.message)

    def test_should_run_full(self):
        t3 = dt.time(3, 0)
        self.assertFalse(should_run_full(dt.datetime(2026, 1, 2, 2, 59), "2026-01-01", t3))
        self.assertTrue(should_run_full(dt.datetime(2026, 1, 2, 3, 0), "2026-01-01", t3))
        self.assertFalse(should_run_full(dt.datetime(2026, 1, 2, 9, 0), "2026-01-02", t3))
        self.assertTrue(should_run_full(dt.datetime(2026, 1, 2, 9, 0), None, t3))


if __name__ == "__main__":
    unittest.main()
