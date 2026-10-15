"""Change journal (WinVet table ZURNAL) and the local state file with the journal cursor."""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set, Tuple

log = logging.getLogger(__name__)

#: ZURNAL.TABULKA -> entity. ZURNAL.ID_ZAZNAM holds the primary key of the changed row
#: (verified on the analysis copy: 100 % of PARTNER/PLATBA/VARIANTA rows match their PK, while
#: ZURNAL.IDKEY holds a parent key, e.g. ID_DOKLAD for DOKLAD_POLOZKA).
#: DOKLAD_POLOZKA ids are shared by all DOKLAD_POLOZKA_* tables; the sale_lines reader looks them
#: up in DOKLAD_POLOZKA_UM, ids not found there are ignored (deletions are always forwarded).
JOURNAL_TABLES: Dict[str, str] = {
    "PARTNER": "owners",
    "PACIENT": "patients",
    "VAKCINACE_ODCERVENI": "vaccinations",
    "DENNI_ZAZNAM": "visits",
    "DOKLAD": "sale_documents",
    "DOKLAD_POLOZKA": "sale_lines",
    "PLATBA": "payments",
    "VARIANTA": "items",
}

_TABLES_IN = ", ".join(f"'{t}'" for t in JOURNAL_TABLES)
MAX_SQL = "select max(ID_ZURNAL) from ZURNAL"
CHANGES_SQL = (
    "select ID_ZURNAL, TABULKA, ID_ZAZNAM, AKCE from ZURNAL "
    f"where ID_ZURNAL > ? and ID_ZURNAL <= ? and trim(TABULKA) in ({_TABLES_IN}) order by ID_ZURNAL"
)


@dataclass
class JournalChanges:
    after: int
    upto: int
    entries: int = 0
    changed: Dict[str, Set[int]] = field(default_factory=dict)
    deleted: Dict[str, Set[int]] = field(default_factory=dict)

    def changed_ids(self, entity: str) -> List[int]:
        return sorted(self.changed.get(entity, ()))

    def deleted_ids(self, entity: str) -> List[int]:
        return sorted(self.deleted.get(entity, ()))


def collect_changes(rows: Iterable[Tuple], after: int, upto: int) -> JournalChanges:
    """Fold journal rows ``(ID_ZURNAL, TABULKA, ID_ZAZNAM, AKCE)`` into changed/deleted ids.

    Rows are processed in ID_ZURNAL order; the last action of an id wins (I/U -> changed,
    D -> deleted). Unknown tables and rows without an id are ignored.
    """
    result = JournalChanges(after=after, upto=upto)
    for id_zurnal, table, record_id, action in sorted(rows, key=lambda r: r[0]):
        result.entries += 1
        entity = JOURNAL_TABLES.get((table or "").strip().upper())
        if entity is None or record_id is None:
            continue
        record_id = int(record_id)
        action = (action or "").strip().upper()
        changed = result.changed.setdefault(entity, set())
        deleted = result.deleted.setdefault(entity, set())
        if action == "D":
            deleted.add(record_id)
            changed.discard(record_id)
        elif action in ("I", "U"):
            changed.add(record_id)
            deleted.discard(record_id)
    return result


def read_max_cursor(db) -> int:
    value = db.scalar(MAX_SQL)
    return int(value) if value is not None else 0


def read_changes(db, after: int, upto: int, chunk_size: int = 500) -> JournalChanges:
    with db.transaction() as tx:
        rows = list(tx.query(CHANGES_SQL, (after, upto), chunk_size))
    return collect_changes(rows, after, upto)


# --------------------------------------------------------------------------- local state


@dataclass
class BridgeState:
    journal_cursor: Optional[int] = None
    #: entities that were blocked/unread and must be pushed in full once they are readable again
    pending_full: List[str] = field(default_factory=list)
    last_full_date: Optional[str] = None
    last_success: Optional[str] = None


class StateStore:
    def __init__(self, path: Path):
        self.path = Path(path)

    def load(self) -> BridgeState:
        if not self.path.is_file():
            return BridgeState()
        with open(self.path, encoding="utf-8") as handle:
            data = json.load(handle)
        cursor = data.get("journal_cursor")
        return BridgeState(
            journal_cursor=int(cursor) if cursor is not None else None,
            pending_full=list(data.get("pending_full") or []),
            last_full_date=data.get("last_full_date"),
            last_success=data.get("last_success"),
        )

    def save(self, state: BridgeState) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        with open(tmp, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(asdict(state), handle, indent=2, sort_keys=True)
            handle.write("\n")
        tmp.replace(self.path)
