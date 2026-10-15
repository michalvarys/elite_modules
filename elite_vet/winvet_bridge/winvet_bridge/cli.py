"""Command line interface: check | sync | run | approve | export."""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import logging
import logging.handlers
import sys
import time
from pathlib import Path
from typing import List, Optional

from . import ENTITY_ORDER, __version__
from .config import BridgeConfig, ConfigError, load_config, resolve_config_path
from .db import ReadOnlyDatabase
from .entities import ENTITY_TABLES, get_reader
from .guard import GROUPS, approve, evaluate, load_verified, read_schema_info, used_column_map
from .journal import JOURNAL_TABLES, StateStore
from .schema_watch import compare, load_baseline, read_snapshot, save_baseline
from .odoo_client import OdooError, make_client
from .sync import make_runner

log = logging.getLogger("winvet_bridge")

EXIT_OK, EXIT_ERROR, EXIT_BLOCKED, EXIT_CONFIG = 0, 1, 2, 3


def setup_logging(config: Optional[BridgeConfig], verbose: bool = False) -> None:
    root = logging.getLogger()
    for handler in list(root.handlers):
        root.removeHandler(handler)
    level = logging.DEBUG if verbose else getattr(logging, (config.log_level if config else "INFO"), logging.INFO)
    root.setLevel(level)
    logging.getLogger("winvet_bridge").setLevel(logging.NOTSET)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    stderr = logging.StreamHandler(sys.stderr)
    stderr.setFormatter(fmt)
    root.addHandler(stderr)
    if config and config.log_file:
        config.log_file.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.handlers.RotatingFileHandler(
            config.log_file, maxBytes=5 * 1024 * 1024, backupCount=5, encoding="utf-8"
        )
        file_handler.setFormatter(fmt)
        root.addHandler(file_handler)


def _guard(db, config):
    schema = read_schema_info(db)
    return evaluate(schema, load_verified(config.verified_file), ENTITY_TABLES)


def _schema_report(db, config):
    return compare(read_snapshot(db), load_baseline(config.schema_baseline_file), used_column_map(), JOURNAL_TABLES)


def cmd_check(config: BridgeConfig, args) -> int:
    with ReadOnlyDatabase(config.firebird, config.batch_size) as db:
        guard = _guard(db, config)
        cursor = None if guard.journal_blocked else _max_cursor(db)
        report = _schema_report(db, config)
    state = StateStore(config.state_file).load()
    s = guard.schema
    print(f"bridge_version : {__version__}")
    print(f"source         : {config.source}")
    print(f"winvet_version : {s.winvet_version} ({'verified' if guard.version_verified else 'NOT VERIFIED'})")
    print(f"ods / engine   : {s.ods} / {s.engine}")
    print("fingerprints   :")
    for group in GROUPS:
        expected = (guard.expected or {}).get(group)
        mark = "ok" if expected == s.fingerprints.get(group) else f"DIFFERS (verified: {expected})"
        print(f"  {group:<9} {s.fingerprints.get(group)}  {mark}")
    print(f"blocked        : {', '.join(guard.blocked_entities) or '-'}")
    print(f"journal        : max ID_ZURNAL={cursor}, local cursor={state.journal_cursor}")
    if guard.message:
        print(f"message        : {guard.message}")
    counts = ", ".join(f"{k} {v}" for k, v in sorted(report.counts.items())) or "none"
    print(f"schema changes : {counts} (baseline {report.baseline_hash or 'missing'}, now {report.snapshot_hash})")
    for change in report.changes[:20]:
        print(f"  {change.describe()}")
    if len(report.changes) > 20:
        print(f"  ... {len(report.changes) - 20} more, see 'schema-diff'")
    return EXIT_BLOCKED if guard.blocked_entities else EXIT_OK


def cmd_schema_diff(config: BridgeConfig, args) -> int:
    with ReadOnlyDatabase(config.firebird, config.batch_size) as db:
        report = _schema_report(db, config)
    if report.baseline_hash is None:
        print("No schema baseline - run 'approve --yes' to store one.")
        return EXIT_ERROR
    if args.json:
        print(json.dumps(report.payload(limit=100000), indent=1, ensure_ascii=False))
    else:
        print(f"baseline {report.baseline_hash} (WinVet {report.baseline_version}) -> now {report.snapshot_hash}")
        for change in report.payload(limit=100000):
            from .schema_watch import SchemaChange
            print(SchemaChange(**change).describe())
        if not report.changes:
            print("No differences.")
    return EXIT_OK


def _max_cursor(db) -> int:
    from .journal import read_max_cursor

    return read_max_cursor(db)


def _print_report(report) -> None:
    print(f"run_id={report.run_id} mode={report.mode} dry_run={report.dry_run} "
          f"cursor={report.cursor_before}->{report.cursor_after} journal_entries={report.journal_entries}")
    for e in report.entities:
        if e.blocked:
            print(f"  {e.entity:<15} BLOCKED")
        else:
            print(f"  {e.entity:<15} {e.mode:<12} records={e.records:<6} deleted={e.deleted:<5} batches={e.batches}")
    if report.message:
        print(f"message: {report.message}")


def sync_once(config: BridgeConfig, full: bool, dry_run: bool):
    client = None if dry_run else make_client(config.require_odoo())
    with ReadOnlyDatabase(config.firebird, config.batch_size) as db:
        return make_runner(config, db, client).run(full=full, dry_run=dry_run)


def cmd_sync(config: BridgeConfig, args) -> int:
    report = sync_once(config, full=args.full, dry_run=args.dry_run)
    _print_report(report)
    return EXIT_BLOCKED if report.guard.blocked_entities else EXIT_OK


def should_run_full(now: _dt.datetime, last_full_date: Optional[str], full_time: _dt.time) -> bool:
    """Full sync once per day, at/after ``full_time`` local time (catches up if the PC was off)."""
    return now.time() >= full_time and last_full_date != now.date().isoformat()


def cmd_run(config: BridgeConfig, args) -> int:
    config.require_odoo()
    interval = config.interval_minutes * 60
    log.info("Bridge service started: interval=%d min, daily full sync at %s",
             config.interval_minutes, config.full_sync_time.strftime("%H:%M"))
    try:
        while True:
            started = time.monotonic()
            now = _dt.datetime.now()
            state = StateStore(config.state_file).load()
            full = should_run_full(now, state.last_full_date, config.full_sync_time)
            try:
                sync_once(config, full=full, dry_run=False)
            except OdooError as exc:
                log.error("Run failed (Odoo): %s - cursor not advanced, will retry", exc)
            except Exception:  # keep the service alive; details (no record data) go to the log
                log.exception("Run failed - cursor not advanced, will retry")
            if args.once:
                return EXIT_OK
            remaining = interval - (time.monotonic() - started)
            while remaining > 0:
                time.sleep(min(remaining, 5.0))
                remaining = interval - (time.monotonic() - started)
    except KeyboardInterrupt:
        log.info("Bridge service stopped")
        return EXIT_OK


def cmd_approve(config: BridgeConfig, args) -> int:
    with ReadOnlyDatabase(config.firebird, config.batch_size) as db:
        schema = read_schema_info(db)
    verified = load_verified(config.verified_file)
    old = verified["versions"].get(schema.winvet_version or "", {}).get("fingerprints", {})
    print(f"WinVet version {schema.winvet_version}, ODS {schema.ods}, engine {schema.engine}")
    for group in GROUPS:
        new = schema.fingerprints[group]
        print(f"  {group:<9} {old.get(group, '-'):<16} -> {new}{'' if old.get(group) == new else '  (changed)'}")
    if not args.yes:
        print("Nothing written. Re-run with --yes after you have checked the new WinVet version "
              "(see README) to mark these fingerprints as verified.")
        return EXIT_ERROR
    approve(config.verified_file, schema)
    with ReadOnlyDatabase(config.firebird, config.batch_size) as db:
        snapshot = read_snapshot(db)
    save_baseline(config.schema_baseline_file, snapshot, schema.winvet_version)
    log.info("Approved WinVet version %s in %s (schema baseline %s)", schema.winvet_version,
             config.verified_file, snapshot["hash"])
    print(f"Written to {config.verified_file} and {config.schema_baseline_file}")
    return EXIT_OK


def cmd_export(config: BridgeConfig, args) -> int:
    print("WARNING: the export contains PERSONAL DATA of clients. Keep it local, delete it after "
          "debugging, never e-mail or commit it.", file=sys.stderr)
    with ReadOnlyDatabase(config.firebird, config.batch_size) as db:
        guard = _guard(db, config)
        if guard.is_blocked(args.entity):
            log.error("Entity %s is blocked by the schema guard: %s", args.entity, guard.message)
            return EXIT_BLOCKED
        reader = get_reader(args.entity, db, config.batch_size)
        records = reader.read_ids(args.ids) if args.ids else reader.read_all()
    out = Path(args.out)
    with open(out, "w", encoding="utf-8") as handle:
        json.dump({"entity": args.entity, "records": records}, handle, ensure_ascii=False, indent=1)
    log.info("Exported %d %s records to %s", len(records), args.entity, out)
    return EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="winvet_bridge", description="WinVet (read-only) -> Odoo bridge")
    parser.add_argument("--config", help="INI config file (default: env WINVET_BRIDGE_CONFIG)")
    parser.add_argument("-v", "--verbose", action="store_true", help="debug logging")
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("check", help="connect, show version/fingerprints/blocked entities (no Odoo)")

    p = sub.add_parser("sync", help="one synchronisation run")
    p.add_argument("--full", action="store_true", help="full resync of all entities")
    p.add_argument("--dry-run", action="store_true", help="read and batch only, no HTTP, state untouched")

    p = sub.add_parser("run", help="service loop: incremental every interval, full once a day")
    p.add_argument("--once", action="store_true", help=argparse.SUPPRESS)

    p = sub.add_parser("approve", help="mark the current WinVet version/fingerprints as verified")
    p.add_argument("--yes", action="store_true", help="really write verified.json")

    p = sub.add_parser("schema-diff", help="list structural differences against the approved baseline")
    p.add_argument("--json", action="store_true", help="machine-readable output")

    p = sub.add_parser("export", help="debug export of one entity to JSON (contains personal data!)")
    p.add_argument("--entity", required=True, choices=ENTITY_ORDER)
    p.add_argument("--out", required=True)
    p.add_argument("--ids", type=int, nargs="*", help="only these WinVet ids")
    return parser


COMMANDS = {"check": cmd_check, "sync": cmd_sync, "run": cmd_run, "approve": cmd_approve, "export": cmd_export,
            "schema-diff": cmd_schema_diff}


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        config = load_config(resolve_config_path(args.config))
    except ConfigError as exc:
        setup_logging(None)
        log.error("Configuration error: %s", exc)
        return EXIT_CONFIG
    setup_logging(config, args.verbose)
    try:
        return COMMANDS[args.command](config, args)
    except ConfigError as exc:
        log.error("Configuration error: %s", exc)
        return EXIT_CONFIG
    except OdooError as exc:
        log.error("Odoo error: %s", exc)
        return EXIT_ERROR
    except KeyboardInterrupt:
        return EXIT_ERROR
    except Exception:
        log.exception("Failed")
        return EXIT_ERROR
