"""Schema guard: refuses to read data from a WinVet version/schema that was not verified.

* ``winvet_version`` (``VERZE.VERZE``) not present in ``verified.json`` -> every entity is blocked
  (and the change journal too).
* Version verified but the fingerprint of a group differs -> every entity that reads at least one
  table of that group is blocked. Other entities continue.

A fingerprint is the first 16 hex digits of SHA-256 over the structure (types, sub-types, lengths,
scales, nullability) of the columns the bridge actually reads (derived from the readers' SQL, see
:func:`winvet_bridge.entities.used_columns`) plus the primary key of every table of the group. New
columns or changes of columns the bridge does not read therefore do not block anything; they are
reported by :mod:`winvet_bridge.schema_watch`. The ``journal`` group also covers the source of the
triggers that write the change journal for the synced tables, so a WinVet update that changes the
journaling falls back to full synchronisation. Data is never part of a fingerprint.
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Optional, Sequence

from . import ENTITY_ORDER

log = logging.getLogger(__name__)

#: Fingerprint group -> tables (structure-only hash). Based on the analysis prototype; UZIVATEL_NEW
#: was added to ``catalog`` because the ``users`` entity reads it.
GROUP_TABLES: Dict[str, Sequence[str]] = {
    "owners": ("PARTNER", "PARTNER_KONTAKT", "TYP_KONTAKTU"),
    "patients": ("PACIENT", "VAKCINACE_ODCERVENI"),
    "clinical": ("PRIPAD", "DENNI_ZAZNAM"),
    "sales": ("DOKLAD", "DOKLAD_POLOZKA_UM", "PLATBA", "TYP_DOKLADU", "DRUH_DOKLADU"),
    "catalog": ("VARIANTA", "VARIANTA_CENIK", "KLASIFIKACE_VYROBKU", "VARIANTA_TYP", "UZIVATEL_NEW"),
    "journal": ("ZURNAL", "VERZE"),
}
GROUPS = tuple(GROUP_TABLES)

#: Columns read outside the entity readers (change journal, version check).
EXTRA_USED_COLUMNS: Dict[str, Sequence[str]] = {
    "ZURNAL": ("ID_ZURNAL", "TABULKA", "ID_ZAZNAM", "AKCE"),
    "VERZE": ("VERZE",),
}

_JOURNAL_TRIGGERS_SQL = """
select trim(t.rdb$trigger_name), trim(t.rdb$relation_name), coalesce(t.rdb$trigger_inactive, 0), t.rdb$trigger_source
from rdb$triggers t
where coalesce(t.rdb$system_flag, 0) = 0 and t.rdb$relation_name is not null
  and t.rdb$trigger_source containing 'ZURNAL'
"""

_COLUMNS_SQL = """
select trim(rf.rdb$field_name), f.rdb$field_type, coalesce(f.rdb$field_sub_type, 0),
       coalesce(f.rdb$character_length, f.rdb$field_length), coalesce(f.rdb$field_scale, 0),
       coalesce(rf.rdb$null_flag, f.rdb$null_flag, 0)
from rdb$relation_fields rf
join rdb$fields f on f.rdb$field_name = rf.rdb$field_source
where rf.rdb$relation_name = ?
order by 1
"""
_PK_SQL = """
select trim(s.rdb$field_name)
from rdb$relation_constraints c
join rdb$index_segments s on s.rdb$index_name = c.rdb$index_name
where c.rdb$relation_name = ? and c.rdb$constraint_type = 'PRIMARY KEY'
order by s.rdb$field_position
"""
# Only the VERZE column - VERZE.REGISTRACE is a licence key and is never selected.
_VERSION_SQL = "select first 1 VERZE from VERZE"
_SERVER_SQL = (
    "select mon$ods_major, mon$ods_minor, rdb$get_context('SYSTEM', 'ENGINE_VERSION') from mon$database"
)


@dataclass
class SchemaInfo:
    winvet_version: Optional[str]
    ods: Optional[str]
    engine: Optional[str]
    fingerprints: Dict[str, str]


@dataclass
class GuardResult:
    schema: SchemaInfo
    version_verified: bool
    expected: Optional[Dict[str, str]]
    mismatched_groups: List[str] = field(default_factory=list)
    blocked_entities: List[str] = field(default_factory=list)

    @property
    def journal_blocked(self) -> bool:
        return (not self.version_verified) or ("journal" in self.mismatched_groups)

    def is_blocked(self, entity: str) -> bool:
        return entity in self.blocked_entities

    @property
    def message(self) -> Optional[str]:
        if not self.version_verified:
            return (
                f"WinVet version {self.schema.winvet_version} is not verified - all entities are "
                "blocked. Check the bridge with the new version and run 'approve'."
            )
        if self.mismatched_groups:
            return (
                "Schema fingerprint changed for group(s): "
                + ", ".join(self.mismatched_groups)
                + ". Blocked entities: "
                + (", ".join(self.blocked_entities) or "none")
                + (". Change journal blocked - incremental sync replaced by full sync." if self.journal_blocked else ".")
            )
        return None


def used_column_map() -> Dict[str, set]:
    from .entities import used_columns  # local import: entities imports this module's GROUPS

    out = {t: set(c) for t, c in used_columns().items()}
    for table, cols in EXTRA_USED_COLUMNS.items():
        out.setdefault(table, set()).update(cols)
    return out


def table_structure(tx, table: str, used: Optional[set] = None) -> dict:
    """Structure of ``table``; with ``used`` only those columns count (missing ones are listed)."""
    columns = [list(row) for row in tx.query(_COLUMNS_SQL, (table,))]
    pk = [row[0] for row in tx.query(_PK_SQL, (table,))]
    if used is not None:
        present = {c[0] for c in columns}
        # Without the length: a longer/shorter text column does not break reading (warning only).
        columns = [[c[0], c[1], c[2], c[4], c[5]] for c in columns if c[0] in used]
        missing = sorted(set(used) - present)
        return {"columns": columns, "pk": pk, "missing": missing, "exists": bool(present)}
    return {"columns": columns, "pk": pk}


def journal_triggers(tx) -> list:
    """Name, table, inactive flag and source hash of triggers writing ZURNAL for synced tables."""
    from .journal import JOURNAL_TABLES

    def relevant(table: str) -> bool:
        return table in JOURNAL_TABLES or (table.startswith("DOKLAD_POLOZKA") and "DOKLAD_POLOZKA" in JOURNAL_TABLES)

    out = []
    for name, table, inactive, source in tx.query(_JOURNAL_TRIGGERS_SQL):
        if relevant(table):
            text = " ".join(str(source or "").split())
            out.append([name, table, int(inactive), hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]])
    return sorted(out)


def fingerprint_of(structures: Mapping[str, dict]) -> str:
    blob = json.dumps(structures, sort_keys=True)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def read_schema_info(db) -> SchemaInfo:
    """Read version, ODS, engine and per-group fingerprints (system tables + VERZE.VERZE only)."""
    used = used_column_map()
    with db.transaction() as tx:
        fingerprints = {}
        for group, tables in GROUP_TABLES.items():
            structures = {t: table_structure(tx, t, used.get(t, set())) for t in tables}
            if group == "journal":
                structures["_journal_triggers"] = journal_triggers(tx)
            fingerprints[group] = fingerprint_of(structures)
        version = tx.scalar(_VERSION_SQL)
        ods = engine = None
        for major, minor, eng in tx.query(_SERVER_SQL):
            ods, engine = f"{major}.{minor}", (eng or "").strip() or None
    return SchemaInfo(
        winvet_version=None if version is None else str(version).strip(),
        ods=ods,
        engine=engine,
        fingerprints=fingerprints,
    )


def entity_groups(entity_tables: Mapping[str, Iterable[str]]) -> Dict[str, List[str]]:
    """entity -> fingerprint groups covering the tables it reads."""
    table_group = {t: g for g, tables in GROUP_TABLES.items() for t in tables}
    out: Dict[str, List[str]] = {}
    for entity, tables in entity_tables.items():
        groups = []
        for table in tables:
            group = table_group.get(table.upper())
            if group is None:
                raise ValueError(f"Table {table} of entity {entity} is not covered by any fingerprint group")
            if group not in groups:
                groups.append(group)
        out[entity] = groups
    return out


def evaluate(
    schema: SchemaInfo, verified: Mapping, entity_tables: Mapping[str, Iterable[str]]
) -> GuardResult:
    """Apply the guard rules; ``verified`` is the parsed verified.json."""
    versions = (verified or {}).get("versions", {})
    entry = versions.get(schema.winvet_version) if schema.winvet_version else None
    deps = entity_groups(entity_tables)
    ordered = [e for e in ENTITY_ORDER if e in deps] + [e for e in deps if e not in ENTITY_ORDER]
    if not entry:
        return GuardResult(schema, False, None, list(GROUPS), ordered)
    expected = dict(entry.get("fingerprints", {}))
    mismatched = [g for g in GROUPS if schema.fingerprints.get(g) != expected.get(g)]
    blocked = [e for e in ordered if any(g in mismatched for g in deps[e])]
    return GuardResult(schema, True, expected, mismatched, blocked)


def load_verified(path: Path) -> dict:
    path = Path(path)
    if not path.is_file():
        log.warning("verified file %s not found - every WinVet version is treated as unverified", path)
        return {"versions": {}}
    with open(path, encoding="utf-8") as handle:
        data = json.load(handle)
    data.setdefault("versions", {})
    return data


def approve(path: Path, schema: SchemaInfo, now: Optional[_dt.datetime] = None) -> dict:
    """Store the current fingerprints as verified for the current WinVet version."""
    if not schema.winvet_version:
        raise ValueError("WinVet version could not be read; nothing to approve")
    path = Path(path)
    data = load_verified(path) if path.is_file() else {"versions": {}}
    data.setdefault(
        "comment",
        "WinVet versions verified for the bridge: version -> schema fingerprints per group. "
        "Update with 'python -m winvet_bridge approve --yes' after checking a new WinVet version.",
    )
    data["versions"][schema.winvet_version] = {
        "fingerprints": {g: schema.fingerprints[g] for g in GROUPS},
        "ods": schema.ods,
        "engine": schema.engine,
        "approved": (now or _dt.datetime.now()).strftime("%Y-%m-%d %H:%M:%S"),
    }
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(data, handle, indent=2, sort_keys=True)
        handle.write("\n")
    tmp.replace(path)
    return data
