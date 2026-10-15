"""Unit tests: guard rules, journal folding, state file, batching, config, SQL safety."""

import ast
import datetime as dt
import json
import os
import re
import tempfile
import unittest
from pathlib import Path

from winvet_bridge import ENTITY_ORDER
from winvet_bridge.config import ConfigError, load_config
from winvet_bridge.db import FORBIDDEN_COLUMNS, UnsafeSqlError, check_select_sql
from winvet_bridge.entities import ENTITY_TABLES, SPECS
from winvet_bridge.guard import GROUP_TABLES, GROUPS, SchemaInfo, approve, entity_groups, evaluate, load_verified
from winvet_bridge.journal import CHANGES_SQL, JOURNAL_TABLES, BridgeState, StateStore, collect_changes
from winvet_bridge.sync import ALWAYS_FULL
from winvet_bridge.sync import build_batches

PACKAGE_DIR = Path(__file__).resolve().parents[1] / "winvet_bridge"
FPS = {g: f"{i:016x}" for i, g in enumerate(GROUPS)}


def schema(version="2603", **changes):
    fps = dict(FPS)
    fps.update(changes)
    return SchemaInfo(version, "13.1", "5.0.1", fps)


VERIFIED = {"versions": {"2603": {"fingerprints": dict(FPS)}}}


class GuardTest(unittest.TestCase):
    def test_all_ok(self):
        result = evaluate(schema(), VERIFIED, ENTITY_TABLES)
        self.assertTrue(result.version_verified)
        self.assertEqual(result.blocked_entities, [])
        self.assertFalse(result.journal_blocked)
        self.assertIsNone(result.message)

    def test_unknown_version_blocks_everything(self):
        result = evaluate(schema("2604"), VERIFIED, ENTITY_TABLES)
        self.assertFalse(result.version_verified)
        self.assertEqual(result.blocked_entities, list(ENTITY_ORDER))
        self.assertTrue(result.journal_blocked)
        self.assertIn("2604", result.message)

    def test_missing_version_blocks_everything(self):
        result = evaluate(schema(None), VERIFIED, ENTITY_TABLES)
        self.assertEqual(result.blocked_entities, list(ENTITY_ORDER))

    def test_sales_change_blocks_only_sales_entities(self):
        result = evaluate(schema(sales="ffffffffffffffff"), VERIFIED, ENTITY_TABLES)
        self.assertEqual(result.mismatched_groups, ["sales"])
        self.assertEqual(result.blocked_entities, ["sale_documents", "sale_lines", "payments"])
        self.assertFalse(result.journal_blocked)

    def test_clinical_change_blocks_dependent_sale_lines(self):
        result = evaluate(schema(clinical="ffffffffffffffff"), VERIFIED, ENTITY_TABLES)
        self.assertEqual(result.blocked_entities, ["visits", "vitals", "sale_lines"])

    def test_templates_change_blocks_only_template_entities(self):
        result = evaluate(schema(templates="ffffffffffffffff"), VERIFIED, ENTITY_TABLES)
        self.assertEqual(result.mismatched_groups, ["templates"])
        self.assertEqual(result.blocked_entities, ["bundles", "bundle_lines", "phrases"])

    def test_catalog_change_blocks_users_and_items(self):
        result = evaluate(schema(catalog="ffffffffffffffff"), VERIFIED, ENTITY_TABLES)
        self.assertEqual(result.blocked_entities, ["users", "items"])

    def test_journal_change_blocks_only_journal(self):
        result = evaluate(schema(journal="ffffffffffffffff"), VERIFIED, ENTITY_TABLES)
        self.assertEqual(result.blocked_entities, [])
        self.assertTrue(result.journal_blocked)
        self.assertIn("journal", result.message)

    def test_every_reader_table_is_fingerprinted(self):
        groups = entity_groups(ENTITY_TABLES)
        self.assertEqual(groups["sale_lines"], ["sales", "clinical"])
        self.assertEqual(groups["users"], ["catalog"])
        self.assertEqual(groups["items"], ["catalog"])
        self.assertEqual(groups["vitals"], ["clinical"])
        for name in ("bundles", "bundle_lines", "phrases"):
            self.assertEqual(groups[name], ["templates"], name)
        self.assertEqual(set(groups), set(ENTITY_ORDER))
        grouped = {t for tables in GROUP_TABLES.values() for t in tables}
        for name, tables in ENTITY_TABLES.items():
            self.assertTrue(set(tables) <= grouped, name)
        with self.assertRaises(ValueError):
            entity_groups({"x": ["UNKNOWN_TABLE"]})

    def test_approve_writes_and_reloads(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "verified.json"
            approve(path, schema("2700"), now=dt.datetime(2026, 1, 1, 12, 0, 0))
            approve(path, schema("2603"))
            data = load_verified(path)
            self.assertEqual(set(data["versions"]), {"2603", "2700"})
            self.assertEqual(data["versions"]["2700"]["fingerprints"], FPS)
            self.assertEqual(data["versions"]["2700"]["approved"], "2026-01-01 12:00:00")
            self.assertEqual(evaluate(schema("2700"), data, ENTITY_TABLES).blocked_entities, [])

    def test_missing_verified_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(load_verified(Path(tmp) / "nope.json"), {"versions": {}})

    def test_shipped_verified_json(self):
        data = load_verified(PACKAGE_DIR.parent / "verified.json")
        self.assertIn("2603", data["versions"])
        self.assertEqual(set(data["versions"]["2603"]["fingerprints"]), set(GROUPS))


class JournalTest(unittest.TestCase):
    def test_collect_changes(self):
        rows = [
            (10, "PARTNER", 1, "U"),
            (11, "PARTNER ", 2, "I"),
            (12, "PARTNER", 2, "D"),
            (13, "DOKLAD_POLOZKA", 50, "I"),
            (14, "FRONTA", 7, "U"),          # unknown table -> ignored
            (15, "PACIENT", 3, "D"),
            (16, "PACIENT", 3, "I"),          # re-inserted after delete -> changed
            (17, "DOKLAD_POLOZKA", 51, "D"),
            (18, "VARIANTA", None, "U"),      # no id -> ignored
        ]
        ch = collect_changes(list(reversed(rows)), 9, 18)
        self.assertEqual(ch.entries, 9)
        self.assertEqual(ch.changed_ids("owners"), [1])
        self.assertEqual(ch.deleted_ids("owners"), [2])
        self.assertEqual(ch.changed_ids("patients"), [3])
        self.assertEqual(ch.deleted_ids("patients"), [])
        self.assertEqual(ch.changed_ids("sale_lines"), [50])
        self.assertEqual(ch.deleted_ids("sale_lines"), [51])
        self.assertEqual(ch.changed_ids("items"), [])

    def test_collect_changes_price_rows_reread_the_item(self):
        rows = [
            (1, "VARIANTA_CENIK", 900, "I", 10),   # 5-tuple: IDKEY = ID_VARIANTA
            (2, "VARIANTA_CENIK", 901, "D", 11),   # deleted price row -> item re-read, not deleted
            (3, "VARIANTA", 12, "D"),
            (4, "VARIANTA_CENIK", 902, "D", 12),   # item itself deleted -> stays deleted
            (5, "VARIANTA_CENIK", 903, "U", 13),
            (6, "VARIANTA", 13, "U"),
            (7, "DENNI_ZAZNAM_HODNOTA", 70, "I"),
            (8, "DENNI_ZAZNAM_HODNOTA", 71, "D"),
            (9, "FRAZE", 5, "U"),
        ]
        ch = collect_changes(rows, 0, 9)
        self.assertEqual(ch.changed_ids("items"), [10, 11, 13])
        self.assertEqual(ch.deleted_ids("items"), [12])
        self.assertEqual(ch.full, set())
        self.assertEqual(ch.changed_ids("vitals"), [70])
        self.assertEqual(ch.deleted_ids("vitals"), [71])
        self.assertEqual(ch.changed_ids("phrases"), [5])
        # a price row without IDKEY (or an old 4-tuple row) cannot be resolved -> items in full
        self.assertEqual(collect_changes([(1, "VARIANTA_CENIK", 900, "U", None)], 0, 1).full, {"items"})
        self.assertEqual(collect_changes([(1, "VARIANTA_CENIK", 900, "U")], 0, 1).full, {"items"})

    def test_journal_mapping_v2(self):
        self.assertEqual(JOURNAL_TABLES["DENNI_ZAZNAM_HODNOTA"], "vitals")
        self.assertEqual(JOURNAL_TABLES["FRAZE"], "phrases")
        self.assertEqual(JOURNAL_TABLES["VARIANTA_CENIK"], "items")
        for name in ("bundles", "bundle_lines", "users", "contacts"):
            self.assertNotIn(name, JOURNAL_TABLES.values())
            self.assertIn(name, ALWAYS_FULL)
        self.assertIn("IDKEY", CHANGES_SQL)

    def test_journal_tables_match_contract(self):
        self.assertEqual(set(JOURNAL_TABLES.values()) - set(ENTITY_ORDER), set())
        self.assertNotIn("users", JOURNAL_TABLES.values())
        self.assertNotIn("contacts", JOURNAL_TABLES.values())

    def test_state_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = StateStore(Path(tmp) / "sub" / "state.json")
            self.assertIsNone(store.load().journal_cursor)
            store.save(BridgeState(journal_cursor=42, pending_full=["visits"], last_full_date="2026-10-15"))
            state = store.load()
            self.assertEqual(state.journal_cursor, 42)
            self.assertEqual(state.pending_full, ["visits"])
            self.assertEqual(state.last_full_date, "2026-10-15")


class BatchTest(unittest.TestCase):
    def test_batches(self):
        recs = [{"id": i} for i in range(1201)]
        batches = build_batches("owners", "full", recs, [], 500, "r1")
        self.assertEqual([len(b["records"]) for b in batches], [500, 500, 201])
        self.assertEqual([(b["batch"], b["batches"]) for b in batches], [(1, 3), (2, 3), (3, 3)])
        self.assertTrue(all(b["run_id"] == "r1" and b["entity"] == "owners" for b in batches))
        self.assertEqual(sum((b["records"] for b in batches), []), recs)

    def test_empty_full_has_one_batch_incremental_none(self):
        self.assertEqual(len(build_batches("users", "full", [], [], 500, "r")), 1)
        self.assertEqual(build_batches("owners", "incremental", [], [], 500, "r"), [])

    def test_deleted_are_batched(self):
        batches = build_batches("owners", "incremental", [{"id": 1}], list(range(7)), 3, "r")
        self.assertEqual([b["deleted"] for b in batches], [[0, 1, 2], [3, 4, 5], [6]])
        self.assertEqual([len(b["records"]) for b in batches], [1, 0, 0])


class SqlSafetyTest(unittest.TestCase):
    def test_check_select_sql(self):
        check_select_sql("select a.X from T a where a.Y = 'update'")
        for bad in ("update VERZE set TEMP = TEMP", "insert into X values (1)", "delete from X",
                    "select 1 from rdb$database; delete from X", "execute procedure P",
                    "select REGISTRACE from VERZE", "select v.registrace from VERZE v",
                    "select HASH from UZIVATEL_NEW", "select u.KOD_CVK from UZIVATEL_NEW u",
                    "select gen_id(G, 1) from rdb$database", "/* x */ merge into X using Y on 1=1"):
            with self.assertRaises(UnsafeSqlError, msg=bad):
                check_select_sql(bad)
        # contract v2: clinical notes are allowed (visits.notes), the rest stays forbidden
        check_select_sql("select z.DEKURS from DENNI_ZAZNAM z")
        self.assertEqual(set(FORBIDDEN_COLUMNS), {"REGISTRACE", "RODNE_CISLO", "HASH", "KOD_CVK"})

    def test_source_never_mentions_forbidden_columns_in_sql(self):
        """Grep every SQL string literal in the package for forbidden columns / select * / procedures."""
        offenders = []
        for path in PACKAGE_DIR.glob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            docstrings = {id(n.value) for n in ast.walk(tree) if isinstance(n, ast.Expr)}
            literals = [n.value for n in ast.walk(tree)
                        if isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in docstrings]
            for literal in literals:
                low = literal.lower()
                if not re.search(r"\b(select|from|join)\b", low):
                    continue
                for col in FORBIDDEN_COLUMNS:
                    if re.search(rf"\b{col.lower()}\b", low):
                        offenders.append((path.name, col))
                if re.search(r"select\s+\*|\w+\.\*", low) or re.search(r"\b(execute|procedure)\b", low):
                    offenders.append((path.name, literal[:40]))
        self.assertEqual(offenders, [])

    def test_reader_sql_is_valid_select(self):
        for spec in SPECS.values():
            check_select_sql(spec.sql)
            self.assertNotIn("*", spec.sql)


class ConfigTest(unittest.TestCase):
    def test_example_config_and_env_secrets(self):
        example = PACKAGE_DIR.parent / "config.example.ini"
        os.environ["WINVET_FB_PASSWORD"] = "pw"
        os.environ["WINVET_ODOO_API_KEY"] = "key"
        try:
            cfg = load_config(example)
        finally:
            del os.environ["WINVET_FB_PASSWORD"], os.environ["WINVET_ODOO_API_KEY"]
        self.assertEqual(cfg.firebird.password, "pw")
        self.assertEqual(cfg.odoo.api_key, "key")
        self.assertEqual(cfg.batch_size, 500)
        self.assertEqual(cfg.interval_minutes, 15)
        self.assertEqual(cfg.full_sync_time, dt.time(3, 0))
        self.assertEqual(cfg.source, "live")
        self.assertEqual(cfg.state_file, example.parent.resolve() / "winvet_bridge_state.json")
        self.assertNotIn("pw", repr(cfg))
        self.assertNotIn("key'", repr(cfg))

    def test_missing_secret_and_bad_values(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "c.ini"
            path.write_text("[firebird]\ndsn = x\npassword_env = WINVET_TEST_UNSET_VAR\n", encoding="utf-8")
            with self.assertRaises(ConfigError):
                load_config(path)
            path.write_text("[firebird]\ndsn = x\npassword = p\n[bridge]\nbatch_size = 900\n", encoding="utf-8")
            with self.assertRaises(ConfigError):
                load_config(path)
            path.write_text("[firebird]\ndsn = x\npassword = p\n[bridge]\nsource = test\n", encoding="utf-8")
            with self.assertRaises(ConfigError):
                load_config(path)
            path.write_text("[firebird]\ndsn = x\npassword = p\n", encoding="utf-8")
            cfg = load_config(path)
            self.assertIsNone(cfg.odoo)
            with self.assertRaises(ConfigError):
                cfg.require_odoo()

    def test_group_tables_are_upper_case(self):
        for tables in GROUP_TABLES.values():
            for t in tables:
                self.assertEqual(t, t.upper())


if __name__ == "__main__":
    unittest.main()
