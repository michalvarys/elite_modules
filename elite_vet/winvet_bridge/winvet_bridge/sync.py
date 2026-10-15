"""One synchronisation run: guard -> status -> read entities -> push batches -> advance cursor."""

from __future__ import annotations

import datetime as _dt
import logging
import math
import secrets
from dataclasses import dataclass, field
from typing import Dict, List, Mapping, Optional, Sequence

from . import ENTITY_ORDER, __version__
from .entities import ENTITY_TABLES, all_readers
from .guard import GuardResult, SchemaInfo, evaluate, read_schema_info, used_column_map
from .journal import JOURNAL_TABLES, BridgeState, JournalChanges, StateStore, read_changes, read_max_cursor
from .schema_watch import SchemaReport, compare, read_snapshot

log = logging.getLogger(__name__)

#: Entities that are not in the change journal (or are small) and are pushed in full every run.
ALWAYS_FULL = ("users", "contacts")


class WinVetSource:
    """Data source backed by a :class:`winvet_bridge.db.ReadOnlyDatabase`."""

    def __init__(self, db, chunk_size: int = 500):
        self.db = db
        self.chunk_size = chunk_size
        self.readers = all_readers(db, chunk_size)

    def schema_info(self) -> SchemaInfo:
        return read_schema_info(self.db)

    def schema_snapshot(self) -> dict:
        return read_snapshot(self.db)

    def journal_max(self) -> int:
        return read_max_cursor(self.db)

    def journal_changes(self, after: int, upto: int) -> JournalChanges:
        return read_changes(self.db, after, upto, self.chunk_size)

    def read_all(self, entity: str) -> List[dict]:
        return self.readers[entity].read_all()

    def read_ids(self, entity: str, ids: Sequence[int]) -> List[dict]:
        return self.readers[entity].read_ids(ids)


@dataclass
class EntityResult:
    entity: str
    mode: Optional[str]  # full | incremental | None (blocked)
    records: int = 0
    deleted: int = 0
    batches: int = 0
    blocked: bool = False


@dataclass
class RunReport:
    run_id: str
    mode: str
    dry_run: bool
    guard: GuardResult
    cursor_before: Optional[int]
    cursor_after: Optional[int]
    journal_entries: int = 0
    message: Optional[str] = None
    entities: List[EntityResult] = field(default_factory=list)
    schema: Optional[SchemaReport] = None

    def counts(self) -> Dict[str, int]:
        return {e.entity: e.records for e in self.entities}


def new_run_id(now: _dt.datetime) -> str:
    return f"{now.strftime('%Y-%m-%dT%H:%M:%S')}/{secrets.token_hex(3)}"


def build_batches(
    entity: str, mode: str, records: Sequence[dict], deleted: Sequence[int], batch_size: int, run_id: str
) -> List[dict]:
    """Split records/deleted ids into push payloads of at most ``batch_size`` items each.

    A full push always has at least one batch (possibly empty) so that Odoo can reconcile.
    An incremental push without changes has no batch at all.
    """
    if batch_size < 1:
        raise ValueError("batch_size must be >= 1")
    count = max(math.ceil(len(records) / batch_size), math.ceil(len(deleted) / batch_size))
    if count == 0 and mode == "full":
        count = 1
    batches = []
    for index in range(count):
        lo, hi = index * batch_size, (index + 1) * batch_size
        batches.append(
            {
                "entity": entity,
                "mode": mode,
                "records": list(records[lo:hi]),
                "deleted": list(deleted[lo:hi]),
                "batch": index + 1,
                "batches": count,
                "run_id": run_id,
            }
        )
    return batches


class SyncRunner:
    def __init__(
        self,
        source,
        state_store: StateStore,
        verified: Mapping,
        batch_size: int = 500,
        source_kind: str = "live",
        client=None,
        entity_tables: Mapping[str, Sequence[str]] = ENTITY_TABLES,
        schema_baseline: Optional[Mapping] = None,
    ):
        self.source = source
        self.state_store = state_store
        self.verified = verified
        self.batch_size = batch_size
        self.source_kind = source_kind
        self.client = client
        self.entity_tables = entity_tables
        self.schema_baseline = schema_baseline

    def schema_report(self) -> Optional[SchemaReport]:
        """Compare the live schema with the approved baseline (None if the source cannot snapshot)."""
        snapshot = getattr(self.source, "schema_snapshot", None)
        if snapshot is None:
            return None
        return compare(snapshot(), self.schema_baseline, used_column_map(), JOURNAL_TABLES)

    def status_payload(self, guard: GuardResult, cursor: Optional[int], message: Optional[str],
                       schema_report: Optional[SchemaReport] = None) -> dict:
        schema = guard.schema
        extra = {}
        if schema_report is not None:
            extra = {
                "schema_hash": schema_report.snapshot_hash,
                "schema_baseline_hash": schema_report.baseline_hash,
                "schema_change_counts": schema_report.counts,
                "schema_changes": schema_report.payload(),
            }
        return {**extra, **{
            "bridge_version": __version__,
            "source": self.source_kind,
            "winvet_version": schema.winvet_version,
            "ods": schema.ods,
            "engine": schema.engine,
            "fingerprints": dict(schema.fingerprints),
            "blocked": list(guard.blocked_entities),
            "journal_cursor": cursor,
            "message": message,
        }}

    def run(self, full: bool = False, dry_run: bool = False, now: Optional[_dt.datetime] = None) -> RunReport:
        now = now or _dt.datetime.now()
        if not dry_run and self.client is None:
            raise ValueError("An Odoo client is required unless dry_run is set")

        guard = evaluate(self.source.schema_info(), self.verified, self.entity_tables)
        schema_report = self.schema_report()
        state = self.state_store.load()
        cursor_before = state.journal_cursor
        messages = [guard.message] if guard.message else []
        if schema_report is not None and schema_report.summary():
            messages.append(schema_report.summary())
            for change in schema_report.changes[:50]:
                log.warning("Schema change: %s", change.describe())
        changes: Optional[JournalChanges] = None

        if guard.journal_blocked or (schema_report is not None and schema_report.journal_changed):
            mode, cursor_after = "full", cursor_before
        else:
            upto = self.source.journal_max()
            if cursor_before is not None and upto < cursor_before:
                messages.append(
                    f"Change journal restarted (max ID_ZURNAL {upto} < cursor {cursor_before}) - full sync."
                )
                log.warning(messages[-1])
                mode = "full"
            elif full or cursor_before is None:
                mode = "full"
            else:
                mode = "incremental"
                changes = self.source.journal_changes(cursor_before, upto)
            cursor_after = upto

        run_id = new_run_id(now)
        message = " ".join(messages) or None
        report = RunReport(
            run_id=run_id,
            mode=mode,
            dry_run=dry_run,
            guard=guard,
            cursor_before=cursor_before,
            cursor_after=cursor_after,
            journal_entries=changes.entries if changes else 0,
            message=message,
            schema=schema_report,
        )
        log.info(
            "Run %s: mode=%s dry_run=%s winvet=%s cursor=%s->%s journal_entries=%d blocked=%s",
            run_id, mode, dry_run, guard.schema.winvet_version, cursor_before, cursor_after,
            report.journal_entries, ",".join(guard.blocked_entities) or "-",
        )

        if not dry_run:
            self.client.status(self.status_payload(guard, cursor_before, message, schema_report))

        pending = set(state.pending_full)
        for entity in ENTITY_ORDER:
            if entity not in self.entity_tables:
                continue
            if guard.is_blocked(entity):
                pending.add(entity)
                report.entities.append(EntityResult(entity, None, blocked=True))
                log.warning("Entity %s blocked by the schema guard - not read", entity)
                continue
            entity_full = mode == "full" or entity in ALWAYS_FULL or entity in pending or changes is None
            if entity_full:
                entity_mode, records, deleted = "full", self.source.read_all(entity), []
            else:
                entity_mode = "incremental"
                ids = changes.changed_ids(entity)
                records = self.source.read_ids(entity, ids) if ids else []
                deleted = changes.deleted_ids(entity)
            batches = build_batches(entity, entity_mode, records, deleted, self.batch_size, run_id)
            for payload in batches:
                if not dry_run:
                    self.client.push(payload)
            if entity_full:
                pending.discard(entity)
            report.entities.append(EntityResult(entity, entity_mode, len(records), len(deleted), len(batches)))
            log.info(
                "Entity %s: mode=%s records=%d deleted=%d batches=%d%s",
                entity, entity_mode, len(records), len(deleted), len(batches), " (dry run)" if dry_run else "",
            )

        if not dry_run:
            # Reached only when every push succeeded: now it is safe to advance the cursor.
            new_state = BridgeState(
                journal_cursor=cursor_after,
                pending_full=[e for e in ENTITY_ORDER if e in pending],
                last_full_date=now.date().isoformat() if mode == "full" else state.last_full_date,
                last_success=now.strftime("%Y-%m-%d %H:%M:%S"),
            )
            self.state_store.save(new_state)
        return report


def make_runner(config, db, client=None, verified: Optional[Mapping] = None) -> SyncRunner:
    from .guard import load_verified
    from .schema_watch import load_baseline

    return SyncRunner(
        source=WinVetSource(db, config.batch_size),
        state_store=StateStore(config.state_file),
        verified=verified if verified is not None else load_verified(config.verified_file),
        batch_size=config.batch_size,
        source_kind=config.source,
        client=client,
        schema_baseline=load_baseline(config.schema_baseline_file),
    )
