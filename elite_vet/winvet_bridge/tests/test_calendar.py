"""Contract v4 - WinVet calendar: binary columns, recurrence expansion, window, payload, guard.

Synthetic data only (the analysis copy is never used here).
"""

import datetime as dt
import struct
import tempfile
import unittest
from pathlib import Path

from winvet_bridge import CALENDAR_ENTITIES, ENTITY_ORDER
from winvet_bridge.entities import ENTITY_TABLES, SPECS, CalendarEventReader, used_columns
from winvet_bridge.guard import GROUP_TABLES, GROUPS, SchemaInfo, entity_groups, evaluate
from winvet_bridge.journal import BridgeState, StateStore
from winvet_bridge.odoo_client import OdooClient
from winvet_bridge.scheduler import (
    CalendarDecodeError, EventBuilder, Recurrence, Window, blob_bytes, decode_recurrence, decode_resources,
    delphi_color, make_window, occurrences, resolve_resources,
)
from winvet_bridge.sync import SyncRunner, resolve_only

from _support import FakeOdoo
from test_normalize_mapping import CONTRACT_KEYS

DELPHI_EPOCH = dt.datetime(1899, 12, 30)


# --------------------------------------------------------------------------- synthetic blobs


def wstr(text):
    return b"\x12" + struct.pack("<I", len(text)) + text.encode("utf-16-le")


def resource_blob(*values, as_list=None):
    if as_list is None:
        as_list = len(values) != 1
    body = b"".join(wstr(v) for v in values)
    if as_list:
        body = b"\x01\x02" + bytes([len(values)]) + body
    return struct.pack("<II", 0x200C, 8 + len(body)) + body


def delphi(day):
    return (dt.datetime.combine(day, dt.time()) - DELPHI_EPOCH).total_seconds() / 86400


def recurrence_blob(kind, count=-1, finish=None, occur_days=0, periodicity=1, day_type=0, day_number=1,
                    year_periodicity=1):
    # finish is stored like WinVet does: 23:00 of the previous day
    finish_value = delphi(finish) - 1 / 24 if finish else -1.0
    return struct.pack("<iiBdBiBdiBi", count, day_number, day_type, finish_value, occur_days, periodicity, kind,
                       0.0, year_periodicity, 1, 46000)


def as_text(blob):
    """What firebird-driver hands over for a WIN1250 text BLOB."""
    return blob.decode("cp1250", errors="strict") if all(b not in (0x81, 0x83, 0x88, 0x90, 0x98) for b in blob) \
        else "".join(chr(b) if b in (0x81, 0x83, 0x88, 0x90, 0x98) else bytes([b]).decode("cp1250") for b in blob)


def row(id_, start, end, typ=0, parent=None, index=None, options=2, resources=("5",), recurrence=None, **over):
    data = {
        "ID_KALENDAR": id_, "ID_PREDEK": parent, "TYP": typ, "ZACATEK": start, "KONEC": end, "VOLBY": options,
        "TITULEK": f"synthetic {id_}", "OPAKOVANI_INDEX": index,
        "OPAKOVANI_INFO": as_text(recurrence) if recurrence else None,
        "ZDROJ_INFO": as_text(resource_blob(*resources)) if resources else None,
        "STAV": 2, "ID_PARTNER": -1, "ID_PACIENT": 0, "ID_ORD_CINNOST": 3, "VYRIZENO": "N",
        "POSLEDNI_MODIFIKACE": dt.date(2026, 10, 1), "POSLEDNI_MODIFIKACE_TS": dt.datetime(2026, 10, 1, 9, 8, 7, 650000),
    }
    data.update(over)
    return data


D = dt.datetime


class BinaryColumnsTest(unittest.TestCase):
    def test_resources_single_list_and_name(self):
        self.assertEqual(decode_resources(resource_blob("5")), ["5"])
        self.assertEqual(decode_resources(resource_blob("5", as_list=True)), ["5"])
        self.assertEqual(decode_resources(resource_blob("5", "4", "5")), ["5", "4"])
        values = decode_resources(resource_blob("2", "ORDINACE 1"))
        self.assertEqual(resolve_resources(values, {"ordinace 1": 5}), [2, 5])
        self.assertEqual(resolve_resources(["UNKNOWN", "0", "-1"], {}), [])
        self.assertEqual(decode_resources(None), [])

    def test_resources_through_the_driver_text(self):
        blob = resource_blob("6")
        self.assertEqual(blob_bytes(as_text(blob)), blob)
        self.assertEqual(decode_resources(blob_bytes(as_text(blob))), ["6"])
        weird = bytes(range(256))
        self.assertEqual(blob_bytes(as_text(weird)), weird)

    def test_broken_resources(self):
        blob = resource_blob("5")
        with self.assertRaises(CalendarDecodeError):
            decode_resources(blob[:-3])
        with self.assertRaises(CalendarDecodeError):
            decode_resources(struct.pack("<II", 0x200C, 9) + b"\x7f")

    def test_recurrence_record(self):
        rule = decode_recurrence(recurrence_blob(1, count=0, finish=dt.date(2026, 9, 27), occur_days=0x41))
        self.assertEqual((rule.kind, rule.count, rule.finish, rule.occur_days), (1, 0, dt.date(2026, 9, 27), 0x41))
        self.assertIsNone(decode_recurrence(recurrence_blob(0, count=7)).finish)
        with self.assertRaises(CalendarDecodeError):
            decode_recurrence(b"\x00" * 10)

    def test_colors(self):
        self.assertEqual(delphi_color(0x00FDF6C9), "#c9f6fd")   # TColor = 0x00BBGGRR
        self.assertEqual(delphi_color(255), "#ff0000")
        self.assertIsNone(delphi_color(536870912))           # clDefault
        self.assertIsNone(delphi_color(None))


class RecurrenceTest(unittest.TestCase):
    def rule(self, **kw):
        base = dict(count=-1, day_number=1, day_type=0, finish=None, occur_days=0, periodicity=1, kind=0,
                    year_periodicity=1)
        base.update(kw)
        return Recurrence(**base)

    def dates(self, rule, first, until):
        return [d for _i, d in occurrences(rule, first, until)]

    def test_daily_every_n_days_count_and_finish(self):
        first = dt.date(2026, 9, 19)
        self.assertEqual(len(self.dates(self.rule(count=7, day_type=1), first, dt.date(2027, 1, 1))), 7)
        self.assertEqual(self.dates(self.rule(count=0, day_type=1, finish=dt.date(2026, 9, 21)), first,
                                    dt.date(2027, 1, 1)), [dt.date(2026, 9, d) for d in (19, 20, 21)])
        self.assertEqual(self.dates(self.rule(day_type=1, periodicity=3), first, dt.date(2026, 9, 26)),
                         [dt.date(2026, 9, d) for d in (19, 22, 25)])

    def test_daily_weekdays(self):
        self.assertEqual(self.dates(self.rule(day_type=2), dt.date(2026, 10, 9), dt.date(2026, 10, 13)),
                         [dt.date(2026, 10, d) for d in (9, 12, 13)])

    def test_weekly_days_and_periodicity(self):
        sat_sun = self.rule(kind=1, occur_days=0x41)  # bit 0 Sunday, bit 6 Saturday
        self.assertEqual(self.dates(sat_sun, dt.date(2026, 9, 19), dt.date(2026, 9, 27)),
                         [dt.date(2026, 9, d) for d in (19, 20, 26, 27)])
        thu_fri_2w = self.rule(kind=1, occur_days=0x30, periodicity=2)
        self.assertEqual(self.dates(thu_fri_2w, dt.date(2026, 9, 17), dt.date(2026, 10, 2)),
                         [dt.date(2026, 9, 17), dt.date(2026, 9, 18), dt.date(2026, 10, 1), dt.date(2026, 10, 2)])

    def test_monthly_and_yearly(self):
        self.assertEqual(self.dates(self.rule(kind=2, day_type=0, day_number=31), dt.date(2026, 1, 31),
                                    dt.date(2026, 4, 30)),
                         [dt.date(2026, 1, 31), dt.date(2026, 2, 28), dt.date(2026, 3, 31), dt.date(2026, 4, 30)])
        last_friday = self.rule(kind=2, day_type=9, day_number=5)  # 4 + 5 = Friday
        self.assertEqual(self.dates(last_friday, dt.date(2026, 10, 1), dt.date(2026, 11, 30)),
                         [dt.date(2026, 10, 30), dt.date(2026, 11, 27)])
        yearly = self.rule(kind=3, day_type=0, day_number=24, periodicity=12)
        self.assertEqual(self.dates(yearly, dt.date(2026, 12, 24), dt.date(2028, 12, 31)),
                         [dt.date(2026, 12, 24), dt.date(2027, 12, 24), dt.date(2028, 12, 24)])

    def test_min_index_reaches_past_until(self):
        out = occurrences(self.rule(day_type=1), dt.date(2026, 9, 1), dt.date(2026, 9, 2), min_index=5)
        self.assertEqual(out[-1], (5, dt.date(2026, 9, 6)))


class EventBuilderTest(unittest.TestCase):
    window = Window(dt.date(2026, 9, 20), dt.date(2026, 9, 30))

    def build(self, rows, names=None):
        builder = EventBuilder(self.window, names or {"ordinace 1": 5})
        return {r["key"]: r for r in builder.build(rows)}, builder

    def test_window_and_payload_shape(self):
        events, builder = self.build([
            row(1, D(2026, 9, 21, 10), D(2026, 9, 21, 10, 30)),
            row(2, D(2026, 9, 19, 10), D(2026, 9, 19, 10, 30)),        # before the window
            row(3, D(2026, 9, 30, 23, 30), D(2026, 10, 1, 0, 30)),      # reaches into the window
            row(4, D(2026, 10, 1, 8), D(2026, 10, 1, 9)),              # after the window
            row(5, D(2026, 9, 22, 9), D(2026, 9, 22, 9, 15), resources=("ORDINACE 1", "6")),
        ])
        self.assertEqual(sorted(events), ["1", "3", "5"])
        rec = events["1"]
        self.assertEqual(set(rec), CONTRACT_KEYS["calendar_events"])
        self.assertEqual(list(rec), list(SPECS["calendar_events"].keys))
        self.assertEqual((rec["id"], rec["start"], rec["end"], rec["all_day"], rec["recurring"]),
                         (1, "2026-09-21 10:00:00", "2026-09-21 10:30:00", False, False))
        self.assertEqual((rec["resource_ids"], rec["activity_id"], rec["owner_id"], rec["patient_id"]),
                         ([5], 3, None, None))
        self.assertEqual((rec["busy_status"], rec["done"], rec["modified"]), (2, False, "2026-10-01 09:08:07"))
        self.assertIsNone(rec["pattern_id"])
        self.assertEqual(events["5"]["resource_ids"], [5, 6])
        self.assertEqual(builder.problems, {})

    def test_all_day_stored_at_23_00(self):
        events, _b = self.build([
            row(10, D(2026, 9, 24, 23), D(2026, 9, 25, 23), options=3),   # = 25. 9.
            row(11, D(2026, 9, 25, 0), D(2026, 9, 27, 0), options=3),     # = 25.-26. 9.
            row(12, D(2026, 9, 19, 23), D(2026, 9, 20, 23), options=3),   # = 20. 9. (first day of the window)
        ])
        self.assertEqual((events["10"]["start"], events["10"]["end"], events["10"]["all_day"]),
                         ("2026-09-25 00:00:00", "2026-09-26 00:00:00", True))
        self.assertEqual((events["11"]["start"], events["11"]["end"]), ("2026-09-25 00:00:00", "2026-09-27 00:00:00"))
        self.assertIn("12", events)

    def test_recurrence_with_changed_and_deleted_occurrences(self):
        weekly = recurrence_blob(1, count=0, finish=dt.date(2026, 10, 31), occur_days=0x41)  # Sat + Sun
        rows = [
            row(49, D(2026, 9, 19, 8), D(2026, 9, 19, 8, 30), typ=1, index=-1, recurrence=weekly),
            row(125, D(2026, 9, 20, 8, 30), D(2026, 9, 20, 9), typ=4, parent=49, index=1),          # Sun 20 deleted
            row(60, D(2026, 9, 26, 11), D(2026, 9, 26, 12), typ=3, parent=49, index=2,             # Sat 26 moved
                resources=("6",), TITULEK="changed"),
            row(61, D(2026, 10, 3, 8), D(2026, 10, 3, 8, 30), typ=3, parent=49, index=4),          # outside window
        ]
        events, builder = self.build(rows)
        # 19 (outside), 20 deleted, 26 changed, 27 regular; 3. 10. outside the window
        self.assertEqual(sorted(events), ["49-20260926", "49-20260927"])
        changed, regular = events["49-20260926"], events["49-20260927"]
        self.assertEqual((changed["id"], changed["pattern_id"], changed["start"], changed["resource_ids"],
                          changed["occurrence_date"], changed["title"]),
                         (60, 49, "2026-09-26 11:00:00", [6], "2026-09-26", "changed"))
        self.assertEqual((regular["id"], regular["pattern_id"], regular["start"], regular["end"],
                          regular["recurring"]), (49, 49, "2026-09-27 08:00:00", "2026-09-27 08:30:00", True))
        self.assertEqual(builder.problems, {})

    def test_changed_occurrence_moved_into_the_window_keeps_its_key(self):
        daily = recurrence_blob(0, count=20, day_type=1)
        rows = [
            row(70, D(2026, 9, 1, 7), D(2026, 9, 1, 7, 30), typ=1, recurrence=daily),
            # occurrence 2 (3. 9., before the window) moved to 22. 9.
            row(71, D(2026, 9, 22, 15), D(2026, 9, 22, 15, 30), typ=3, parent=70, index=2),
        ]
        events, _b = self.build(rows)
        self.assertIn("70-20260903", events)
        self.assertEqual(events["70-20260903"]["start"], "2026-09-22 15:00:00")
        self.assertEqual(sorted(k for k in events if k != "70-20260903"),
                         ["70-202609%02d" % d for d in range(20, 21)])  # count 20 = 1. .. 20. 9.

    def test_problems_are_counted_not_raised(self):
        rows = [
            row(80, D(2026, 9, 21, 8), D(2026, 9, 21, 9), typ=1, recurrence=b"\x00\x01"),
            row(81, D(2026, 9, 21, 8), D(2026, 9, 21, 9), ZDROJ_INFO="garbage"),
            row(82, D(2026, 9, 22, 8), D(2026, 9, 22, 9), typ=3, parent=999, index=0),
            row(83, None, None),
        ]
        events, builder = self.build(rows)
        self.assertEqual(sorted(events), ["81", "999-20260922"])
        self.assertEqual(events["81"]["resource_ids"], [])
        self.assertEqual(set(builder.problems), {"recurrence info not decodable", "resource info not decodable",
                                                 "occurrence without pattern", "event without time"})

    def test_make_window(self):
        window = make_window(dt.date(2026, 10, 25), 1, 60)
        self.assertEqual(window.payload(), {"from": "2026-10-24", "to": "2026-12-24"})


class CalendarReaderTest(unittest.TestCase):
    class FakeTx:
        def __init__(self, rows):
            self.rows, self.calls = rows, []

        def query_dicts(self, sql, params=(), chunk_size=500):
            self.calls.append((sql, tuple(params)))
            if "KALENDAR_NEW_KALENDAR" in sql and "from KALENDAR_NEW k" not in sql:
                return iter([{"ID_KALENDAR_NEW_KALENDAR": 5, "KALENDAR_NAZEV": "ORDINACE 1", "BARVA": None,
                              "ZOBRAZIT": "A", "PRACOVNI_DOBA_OD": None, "PRACOVNI_DOBA_DO": None, "PORADI": 1}])
            return iter(self.rows)

    class FakeDb:
        def __init__(self, tx):
            self.tx = tx

        def transaction(self):
            tx = self.tx

            class Ctx:
                def __enter__(self):
                    return tx

                def __exit__(self, *exc):
                    return False
            return Ctx()

    def test_reader_reads_one_window_with_margin(self):
        tx = self.FakeTx([row(1, D(2026, 10, 25, 9), D(2026, 10, 25, 9, 30), resources=("ORDINACE 1",))])
        reader = CalendarEventReader(SPECS["calendar_events"], self.FakeDb(tx), days_back=1, days_ahead=60,
                                     today=lambda: dt.date(2026, 10, 25))
        records = reader.read_all()
        self.assertEqual([r["resource_ids"] for r in records], [[5]])
        self.assertEqual(reader.window.payload(), {"from": "2026-10-24", "to": "2026-12-24"})
        sql, params = tx.calls[-1]
        self.assertIn("coalesce(k.TYP, 0) <> 0 or (k.ZACATEK < ? and k.KONEC > ?)", sql)
        self.assertEqual(params, (D(2026, 12, 26), D(2026, 10, 23)))
        self.assertNotIn("ZPRAVA", sql)
        with self.assertRaises(NotImplementedError):
            reader.read_ids([1])


class CalendarGuardTest(unittest.TestCase):
    def test_tables_are_guarded_in_their_own_group(self):
        self.assertEqual(set(GROUP_TABLES["calendar"]), {"KALENDAR_NEW", "KALENDAR_NEW_KALENDAR", "ORD_CINNOST"})
        groups = entity_groups(ENTITY_TABLES)
        for entity in CALENDAR_ENTITIES:
            self.assertEqual(groups[entity], ["calendar"], entity)
        cols = used_columns()
        self.assertTrue({"ZACATEK", "KONEC", "TYP", "OPAKOVANI_INFO", "ZDROJ_INFO", "TITULEK"} <= cols["KALENDAR_NEW"])
        self.assertNotIn("ZPRAVA", cols["KALENDAR_NEW"])

    def test_changed_calendar_fingerprint_blocks_only_the_calendar(self):
        fps = {g: "0" * 16 for g in GROUPS}
        verified = {"versions": {"2603": {"fingerprints": dict(fps)}}}
        result = evaluate(SchemaInfo("2603", "13.1", "5.0.1", dict(fps, calendar="1" * 16)), verified, ENTITY_TABLES)
        self.assertEqual(result.blocked_entities, list(CALENDAR_ENTITIES))
        self.assertFalse(result.journal_blocked)
        self.assertIn("calendar", result.message)
        # a bridge v4 against verified.json of v3 (no calendar group yet): only the calendar waits
        old = {"versions": {"2603": {"fingerprints": {g: v for g, v in fps.items() if g != "calendar"}}}}
        result = evaluate(SchemaInfo("2603", "13.1", "5.0.1", dict(fps)), old, ENTITY_TABLES)
        self.assertEqual(result.blocked_entities, list(CALENDAR_ENTITIES))


class OnlyCalendarRunTest(unittest.TestCase):
    """``sync --only calendar``: only the calendar, window in every batch, journal untouched."""

    class Source:
        def __init__(self):
            self.read_log = []

        def schema_info(self):
            return SchemaInfo("2603", "13.1", "5.0.1", {g: "0" * 16 for g in GROUPS})

        def journal_max(self):
            raise AssertionError("the journal must not be read")

        def read_all(self, entity):
            self.read_log.append(entity)
            if entity == "calendar_events":
                return [{"key": f"{i}", "id": i} for i in range(1, 4)]
            return [{"id": 1}]

        def read_ids(self, entity, ids):
            raise AssertionError("no incremental reads")

        def push_extra(self, entity):
            return {"window": {"from": "2026-10-24", "to": "2026-12-24"}} if entity == "calendar_events" else {}

    def test_only_calendar(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = StateStore(Path(tmp) / "state.json")
            store.save(BridgeState(journal_cursor=500, last_full_date="2026-10-24",
                                   pending_full=["owners", "calendar_events"]))
            source = self.Source()
            verified = {"versions": {"2603": {"fingerprints": {g: "0" * 16 for g in GROUPS}}}}
            with FakeOdoo() as odoo:
                client = OdooClient(odoo.url, odoo.api_key, timeout=5, retries=0)
                runner = SyncRunner(source, store, verified, batch_size=2, client=client)
                report = runner.run(only=resolve_only(["calendar"]))
                pushes = odoo.pushes()
            self.assertEqual(report.mode, "only")
            self.assertEqual(source.read_log, list(CALENDAR_ENTITIES))
            self.assertEqual([p["entity"] for p in pushes],
                             ["calendar_resources", "calendar_activities", "calendar_events", "calendar_events"])
            events = [p for p in pushes if p["entity"] == "calendar_events"]
            self.assertTrue(all(p["window"] == {"from": "2026-10-24", "to": "2026-12-24"} for p in events))
            self.assertEqual([(p["batch"], p["batches"], p["mode"]) for p in events], [(1, 2, "full"), (2, 2, "full")])
            self.assertNotIn("window", pushes[0])
            state = store.load()
            self.assertEqual((state.journal_cursor, state.last_full_date, state.pending_full),
                             (500, "2026-10-24", ["owners"]))

    def test_resolve_only(self):
        self.assertIsNone(resolve_only(None))
        self.assertEqual(resolve_only(["calendar_events", "users"]), ["users", "calendar_events"])
        with self.assertRaises(ValueError):
            resolve_only(["owners"])  # journaled entities cannot run on their own
        self.assertEqual(ENTITY_ORDER[-3:], CALENDAR_ENTITIES)


if __name__ == "__main__":
    unittest.main()
