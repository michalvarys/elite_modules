"""Table-level watch of WinVet schema changes.

On every run the bridge takes a snapshot of the whole WinVet schema (system tables only, no data)
and compares it with the approved baseline (``schema_baseline.json``, written by ``approve``).
Every difference is reported as one change with a severity:

* ``breaking`` - a table or column the bridge reads was removed or its type changed. The guard
  blocks the affected entities (via the used-columns fingerprints in :mod:`winvet_bridge.guard`).
* ``journal``  - a trigger that writes the change journal (ZURNAL) for a synced table was changed,
  removed or deactivated. Incremental sync cannot be trusted -> full sync.
* ``warning``  - other change in a table the bridge reads (new column, length change, index, ...).
  Reading continues because the bridge selects explicit columns.
* ``info``     - anything else (tables the bridge does not read, views, procedures).

A cheap pre-check compares ``RDB$RELATIONS.RDB$FORMAT`` (Firebird increments it on every
structural change of a table) and a hash of the snapshot.
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import json
import logging
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Optional, Set

log = logging.getLogger(__name__)

TYPE_NAMES = {
    7: "SMALLINT", 8: "INTEGER", 10: "FLOAT", 12: "DATE", 13: "TIME", 14: "CHAR", 16: "BIGINT",
    23: "BOOLEAN", 24: "DECFLOAT(16)", 25: "DECFLOAT(34)", 26: "INT128", 27: "DOUBLE PRECISION",
    28: "TIME WITH TIME ZONE", 29: "TIMESTAMP WITH TIME ZONE", 35: "TIMESTAMP", 37: "VARCHAR",
    261: "BLOB",
}

_TABLES_SQL = """
select trim(r.rdb$relation_name), coalesce(r.rdb$format, 0), r.rdb$view_blr is not null
from rdb$relations r
where coalesce(r.rdb$system_flag, 0) = 0
"""
_COLUMNS_SQL = """
select trim(rf.rdb$relation_name), trim(rf.rdb$field_name), f.rdb$field_type,
       coalesce(f.rdb$field_sub_type, 0), coalesce(f.rdb$character_length, f.rdb$field_length),
       coalesce(f.rdb$field_precision, 0), coalesce(f.rdb$field_scale, 0),
       coalesce(rf.rdb$null_flag, f.rdb$null_flag, 0),
       coalesce(rf.rdb$default_source, f.rdb$default_source), f.rdb$computed_source
from rdb$relation_fields rf
join rdb$fields f on f.rdb$field_name = rf.rdb$field_source
join rdb$relations r on r.rdb$relation_name = rf.rdb$relation_name
where coalesce(r.rdb$system_flag, 0) = 0
"""
_INDEXES_SQL = """
select trim(i.rdb$relation_name), trim(i.rdb$index_name), coalesce(i.rdb$unique_flag, 0),
       coalesce(i.rdb$index_inactive, 0), trim(s.rdb$field_name), s.rdb$field_position
from rdb$indices i
join rdb$index_segments s on s.rdb$index_name = i.rdb$index_name
where coalesce(i.rdb$system_flag, 0) = 0
"""
_CONSTRAINTS_SQL = """
select trim(c.rdb$relation_name), trim(c.rdb$constraint_name), trim(c.rdb$constraint_type),
       trim(c.rdb$index_name)
from rdb$relation_constraints c
join rdb$relations r on r.rdb$relation_name = c.rdb$relation_name
where coalesce(r.rdb$system_flag, 0) = 0 and c.rdb$constraint_type in ('PRIMARY KEY', 'UNIQUE', 'FOREIGN KEY')
"""
_TRIGGERS_SQL = """
select trim(t.rdb$trigger_name), trim(coalesce(t.rdb$relation_name, '')), t.rdb$trigger_type,
       coalesce(t.rdb$trigger_inactive, 0), t.rdb$trigger_source
from rdb$triggers t
where coalesce(t.rdb$system_flag, 0) = 0
"""
_PROCEDURES_SQL = """
select trim(p.rdb$procedure_name), p.rdb$procedure_source
from rdb$procedures p
where coalesce(p.rdb$system_flag, 0) = 0
"""
_VIEWS_SQL = """
select trim(r.rdb$relation_name), r.rdb$view_source
from rdb$relations r
where coalesce(r.rdb$system_flag, 0) = 0 and r.rdb$view_blr is not null
"""


def _sha(text) -> Optional[str]:
    if text is None:
        return None
    if not isinstance(text, str):
        text = str(text)
    # Whitespace-insensitive: reformatting a trigger must not count as a change.
    return hashlib.sha256(" ".join(text.split()).encode("utf-8")).hexdigest()[:16]


def column_type(ftype, sub, length, precision, scale) -> str:
    name = TYPE_NAMES.get(ftype, f"TYPE{ftype}")
    if ftype in (7, 8, 16, 26) and scale and scale < 0:
        return f"NUMERIC({precision},{-scale})"
    if ftype in (14, 37):
        return f"{name}({length})"
    if ftype == 261:
        return f"BLOB SUB_TYPE {sub}"
    return name


def read_snapshot(db) -> dict:
    """Snapshot of the whole user schema (structure only)."""
    tables: Dict[str, dict] = {}
    with db.transaction() as tx:
        for name, fmt, is_view in tx.query(_TABLES_SQL):
            tables[name] = {"view": bool(is_view), "format": int(fmt), "columns": {}, "pk": [],
                            "unique": {}, "fks": {}, "indexes": {}, "triggers": {}}
        for table, col, ftype, sub, length, prec, scale, notnull, default, computed in tx.query(_COLUMNS_SQL):
            if table in tables:
                tables[table]["columns"][col] = {
                    "type": column_type(ftype, sub, length, prec, scale),
                    "not_null": bool(notnull),
                    "default": _sha(default),
                    "computed": _sha(computed),
                }
        segments: Dict[str, List[tuple]] = {}
        index_table: Dict[str, tuple] = {}
        for table, index, unique, inactive, field, pos in tx.query(_INDEXES_SQL):
            segments.setdefault(index, []).append((pos or 0, field))
            index_table[index] = (table, bool(unique), bool(inactive))
        index_fields = {i: [f for _p, f in sorted(segs)] for i, segs in segments.items()}
        for index, (table, unique, inactive) in index_table.items():
            if table in tables:
                tables[table]["indexes"][index] = {"fields": index_fields[index], "unique": unique,
                                                   "inactive": inactive}
        for table, cname, ctype, index in tx.query(_CONSTRAINTS_SQL):
            if table not in tables:
                continue
            fields = index_fields.get(index, [])
            if ctype == "PRIMARY KEY":
                tables[table]["pk"] = fields
            elif ctype == "UNIQUE":
                tables[table]["unique"][cname] = fields
            else:
                tables[table]["fks"][cname] = fields
        db_triggers: Dict[str, dict] = {}
        for name, table, ttype, inactive, source in tx.query(_TRIGGERS_SQL):
            entry = {"type": int(ttype or 0), "inactive": bool(inactive), "source": _sha(source),
                     "journal": bool(source and "ZURNAL" in str(source).upper())}
            if table and table in tables:
                tables[table]["triggers"][name] = entry
            else:
                db_triggers[name] = entry
        procedures = {name: _sha(src) for name, src in tx.query(_PROCEDURES_SQL)}
        views = {name: _sha(src) for name, src in tx.query(_VIEWS_SQL)}
    snapshot = {"tables": tables, "procedures": procedures, "views": views, "db_triggers": db_triggers}
    snapshot["hash"] = snapshot_hash(snapshot)
    return snapshot


def snapshot_hash(snapshot: Mapping) -> str:
    body = {k: v for k, v in snapshot.items() if k not in ("hash", "taken", "winvet_version")}
    return hashlib.sha256(json.dumps(body, sort_keys=True).encode("utf-8")).hexdigest()[:16]


# --------------------------------------------------------------------------- diff


@dataclass
class SchemaChange:
    object: str  # table | column | primary_key | unique | foreign_key | index | trigger | procedure | view | db_trigger
    table: Optional[str]
    name: Optional[str]
    change: str  # added | removed | changed
    old: Optional[str] = None
    new: Optional[str] = None
    severity: str = "info"

    def as_dict(self) -> dict:
        return asdict(self)

    def describe(self) -> str:
        where = ".".join(x for x in (self.table, self.name) if x) or "-"
        detail = ""
        if self.change == "changed":
            detail = f": {self.old} -> {self.new}"
        elif self.change == "added" and self.new:
            detail = f": {self.new}"
        elif self.change == "removed" and self.old:
            detail = f" (was {self.old})"
        return f"[{self.severity}] {self.object} {where} {self.change}{detail}"


def _fmt_column(col: Mapping) -> str:
    text = col["type"] + (" NOT NULL" if col.get("not_null") else "")
    if col.get("computed"):
        text += " COMPUTED"
    return text


def _fmt_trigger(trg: Mapping) -> str:
    return f"type {trg['type']}{' inactive' if trg['inactive'] else ''} src {trg['source']}"


def _diff_mapping(kind, table, old: Mapping, new: Mapping, fmt) -> List[SchemaChange]:
    out = []
    for name in sorted(set(old) | set(new)):
        if name not in new:
            out.append(SchemaChange(kind, table, name, "removed", old=fmt(old[name])))
        elif name not in old:
            out.append(SchemaChange(kind, table, name, "added", new=fmt(new[name])))
        elif old[name] != new[name]:
            out.append(SchemaChange(kind, table, name, "changed", old=fmt(old[name]), new=fmt(new[name])))
    return out


def diff(baseline: Mapping, current: Mapping) -> List[SchemaChange]:
    """All structural differences between two snapshots (unclassified, severity ``info``)."""
    changes: List[SchemaChange] = []
    old_t, new_t = baseline.get("tables", {}), current.get("tables", {})
    for table in sorted(set(old_t) | set(new_t)):
        kind = "view" if (new_t.get(table) or old_t.get(table) or {}).get("view") else "table"
        if table not in new_t:
            changes.append(SchemaChange(kind, table, None, "removed"))
            continue
        if table not in old_t:
            changes.append(SchemaChange(kind, table, None, "added",
                                        new=f"{len(new_t[table]['columns'])} columns"))
            continue
        o, n = old_t[table], new_t[table]
        changes += _diff_mapping("column", table, o["columns"], n["columns"], _fmt_column)
        if o["pk"] != n["pk"]:
            changes.append(SchemaChange("primary_key", table, None, "changed",
                                        old=",".join(o["pk"]) or None, new=",".join(n["pk"]) or None))
        changes += _diff_mapping("unique", table, o["unique"], n["unique"], ",".join)
        changes += _diff_mapping("foreign_key", table, o["fks"], n["fks"], ",".join)
        changes += _diff_mapping("index", table, o["indexes"], n["indexes"],
                                 lambda i: ",".join(i["fields"]) + (" unique" if i["unique"] else "")
                                 + (" inactive" if i["inactive"] else ""))
        changes += _diff_mapping("trigger", table, o["triggers"], n["triggers"], _fmt_trigger)
    changes += _diff_mapping("procedure", None, baseline.get("procedures", {}), current.get("procedures", {}),
                             lambda s: s)
    view_changes = _diff_mapping("view", None, baseline.get("views", {}), current.get("views", {}), lambda s: s)
    # A view added/removed is already reported as a table-level change above.
    changes += [c for c in view_changes if c.change == "changed"]
    changes += _diff_mapping("db_trigger", None, baseline.get("db_triggers", {}), current.get("db_triggers", {}),
                             _fmt_trigger)
    return changes


def classify(changes: Iterable[SchemaChange], used_columns: Mapping[str, Set[str]],
             journal_tables: Iterable[str], baseline: Mapping, current: Mapping) -> List[SchemaChange]:
    """Set the severity of every change (see module docstring)."""
    journal_tables = {t.upper() for t in journal_tables}
    # ZURNAL.TABULKA "DOKLAD_POLOZKA" is written by the triggers of every DOKLAD_POLOZKA_* table.
    def journal_relevant(table: Optional[str]) -> bool:
        if not table:
            return False
        return table in journal_tables or (table.startswith("DOKLAD_POLOZKA") and "DOKLAD_POLOZKA" in journal_tables)

    def is_journal_trigger(table, name) -> bool:
        for snap in (baseline, current):
            trg = snap.get("tables", {}).get(table, {}).get("triggers", {}).get(name)
            if trg and trg.get("journal"):
                return True
        return False

    out = []
    for c in changes:
        used = used_columns.get(c.table or "", set())
        severity = "info"
        if c.object in ("table", "view") and c.table in used_columns:
            severity = "breaking" if c.change == "removed" else "warning"
        elif c.object == "column" and c.table in used_columns:
            if c.name in used and c.change == "removed":
                severity = "breaking"
            elif c.name in used and c.change == "changed":
                old_type = (c.old or "").split("(")[0].split(" NOT NULL")[0]
                new_type = (c.new or "").split("(")[0].split(" NOT NULL")[0]
                severity = "breaking" if old_type != new_type else "warning"
            else:
                severity = "warning"
        elif c.object == "primary_key" and c.table in used_columns:
            severity = "breaking"
        elif c.object == "trigger" and journal_relevant(c.table) and is_journal_trigger(c.table, c.name):
            severity = "journal"
        elif c.table in used_columns:
            severity = "warning"
        c.severity = severity
        out.append(c)
    return out


# --------------------------------------------------------------------------- baseline file


def load_baseline(path: Path) -> Optional[dict]:
    path = Path(path)
    if not path.is_file():
        return None
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def save_baseline(path: Path, snapshot: Mapping, winvet_version: Optional[str],
                  now: Optional[_dt.datetime] = None) -> None:
    data = dict(snapshot)
    data["winvet_version"] = winvet_version
    data["taken"] = (now or _dt.datetime.now()).strftime("%Y-%m-%d %H:%M:%S")
    path = Path(path)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(data, handle, indent=1, sort_keys=True)
        handle.write("\n")
    tmp.replace(path)


@dataclass
class SchemaReport:
    snapshot_hash: str
    baseline_hash: Optional[str]
    baseline_version: Optional[str]
    changes: List[SchemaChange]

    @property
    def counts(self) -> Dict[str, int]:
        out: Dict[str, int] = {}
        for c in self.changes:
            out[c.severity] = out.get(c.severity, 0) + 1
        return out

    @property
    def journal_changed(self) -> bool:
        return any(c.severity == "journal" for c in self.changes)

    def summary(self) -> Optional[str]:
        if self.baseline_hash is None:
            return "No schema baseline - run 'approve' to store one."
        if not self.changes:
            return None
        counts = ", ".join(f"{k} {v}" for k, v in sorted(self.counts.items()))
        return f"WinVet schema differs from the approved baseline ({counts})."

    def payload(self, limit: int = 300) -> List[dict]:
        order = {"breaking": 0, "journal": 1, "warning": 2, "info": 3}
        ranked = sorted(self.changes, key=lambda c: (order.get(c.severity, 9), c.table or "", c.name or ""))
        return [c.as_dict() for c in ranked[:limit]]


def compare(snapshot: Mapping, baseline: Optional[Mapping], used_columns: Mapping[str, Set[str]],
            journal_tables: Iterable[str]) -> SchemaReport:
    if baseline is None:
        return SchemaReport(snapshot["hash"], None, None, [])
    if baseline.get("hash") == snapshot["hash"]:
        return SchemaReport(snapshot["hash"], baseline.get("hash"), baseline.get("winvet_version"), [])
    changes = classify(diff(baseline, snapshot), used_columns, journal_tables, baseline, snapshot)
    return SchemaReport(snapshot["hash"], baseline.get("hash"), baseline.get("winvet_version"), changes)
