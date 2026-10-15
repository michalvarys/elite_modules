"""Strictly read-only access to the WinVet Firebird database.

Safety layers:

1. Every statement runs inside a transaction started with a TPB of access mode READ
   (``isc_tpb_read``). Firebird itself rejects any INSERT/UPDATE/DELETE/DDL in such a transaction
   ("attempted update during read-only transaction").
2. Transactions are never committed: they always end with ROLLBACK (nothing to commit anyway).
3. :meth:`ReadOnlyTransaction.query` only accepts a single plain SELECT statement (no ``;``, no
   ``EXECUTE``, no ``INSERT/UPDATE/DELETE/MERGE``) and refuses the forbidden columns
   (licence key, personal identifiers, password hashes). Clinical notes (``DENNI_ZAZNAM.DEKURS``)
   are allowed since contract v2 (``visits.notes``).
4. Callers select from base tables only - never from views and never from stored procedures,
   because WinVet relies on 11 UDF libraries that may not be installed.

Isolation: SNAPSHOT (``isc_tpb_concurrency``). Each entity is read in its own short transaction, so
one entity (e.g. sale lines joined with documents and visits) is internally consistent, and no
transaction stays open for longer than one entity read. SNAPSHOT is supported by every Firebird
version WinVet may run on (2.5 - 5.0), unlike READ COMMITTED READ CONSISTENCY (4.0+).

Rows are fetched in chunks (``fetchmany``).
"""

from __future__ import annotations

import logging
import re
from contextlib import contextmanager
from typing import Any, Iterator, List, Optional, Sequence, Set

from .config import FirebirdConfig

log = logging.getLogger(__name__)

#: Columns that must never be selected by the bridge.
FORBIDDEN_COLUMNS = ("REGISTRACE", "RODNE_CISLO", "HASH", "KOD_CVK")

_FORBIDDEN_RE = re.compile(r"\b(" + "|".join(FORBIDDEN_COLUMNS) + r")\b", re.IGNORECASE)
_WRITE_RE = re.compile(
    r"\b(INSERT|UPDATE|DELETE|MERGE|UPSERT|EXECUTE|CREATE|ALTER|DROP|RECREATE|GRANT|REVOKE|COMMIT|"
    r"ROLLBACK|SET\s+GENERATOR|GEN_ID|NEXT\s+VALUE)\b",
    re.IGNORECASE,
)
_COMMENT_RE = re.compile(r"/\*.*?\*/|--[^\n]*", re.DOTALL)
_STRING_RE = re.compile(r"'(?:[^']|'')*'")


class UnsafeSqlError(ValueError):
    """Raised when a statement is not a plain read-only SELECT."""


def check_select_sql(sql: str) -> str:
    """Validate that ``sql`` is a single plain SELECT; return it unchanged."""
    stripped = _COMMENT_RE.sub(" ", sql).strip()
    code = _STRING_RE.sub("''", stripped)
    if not re.match(r"^(SELECT|WITH)\b", code, re.IGNORECASE):
        raise UnsafeSqlError("Only SELECT statements are allowed")
    if ";" in code:
        raise UnsafeSqlError("Multiple statements are not allowed")
    match = _WRITE_RE.search(code)
    if match:
        raise UnsafeSqlError(f"Keyword {match.group(1).upper()!r} is not allowed")
    match = _FORBIDDEN_RE.search(code)
    if match:
        raise UnsafeSqlError(f"Column {match.group(1).upper()!r} must never be selected")
    return sql


def _driver():
    from firebird import driver  # imported lazily so unit tests run without the client library

    return driver


_client_library_set = False


def configure_client_library(path) -> None:
    """Point firebird-driver to fbclient (``fbclient.dll`` / ``libfbclient.so``) once."""
    global _client_library_set
    if path is None or _client_library_set:
        return
    _driver().driver_config.fb_client_library.value = str(path)
    _client_library_set = True


def read_only_tpb() -> bytes:
    drv = _driver()
    return drv.TPB(
        access_mode=drv.TraAccessMode.READ,
        isolation=drv.Isolation.SNAPSHOT,
        lock_timeout=10,
    ).get_buffer()


class ReadOnlyTransaction:
    """One read-only SNAPSHOT transaction; created by :meth:`ReadOnlyDatabase.transaction`."""

    def __init__(self, database: "ReadOnlyDatabase", manager: Any):
        self._database = database
        self.manager = manager  # firebird.driver.TransactionManager (exposed for tests only)

    def query(self, sql: str, params: Sequence[Any] = (), chunk_size: int = 500) -> Iterator[tuple]:
        """Execute a validated SELECT and yield rows, fetched ``chunk_size`` at a time."""
        check_select_sql(sql)
        self._database.executed_sql.add(" ".join(sql.split()))
        cursor = self.manager.cursor()
        try:
            cursor.execute(sql, tuple(params))
            while True:
                rows = cursor.fetchmany(chunk_size)
                if not rows:
                    break
                for row in rows:
                    yield row
        finally:
            cursor.close()

    def query_dicts(self, sql: str, params: Sequence[Any] = (), chunk_size: int = 500) -> Iterator[dict]:
        """Like :meth:`query` but yield ``{column alias: value}`` dicts."""
        check_select_sql(sql)
        self._database.executed_sql.add(" ".join(sql.split()))
        cursor = self.manager.cursor()
        try:
            cursor.execute(sql, tuple(params))
            names = [d[0].strip().upper() for d in cursor.description]
            while True:
                rows = cursor.fetchmany(chunk_size)
                if not rows:
                    break
                for row in rows:
                    yield dict(zip(names, row))
        finally:
            cursor.close()

    def scalar(self, sql: str, params: Sequence[Any] = ()) -> Any:
        for row in self.query(sql, params, chunk_size=1):
            return row[0]
        return None


class ReadOnlyDatabase:
    """Connection to WinVet that only ever opens read-only transactions."""

    #: Every distinct statement executed through any instance (used by the safety tests).
    executed_sql: Set[str] = set()

    def __init__(self, config: FirebirdConfig, chunk_size: int = 500):
        self.config = config
        self.chunk_size = chunk_size
        self._connection = None

    def connect(self) -> "ReadOnlyDatabase":
        if self._connection is None:
            configure_client_library(self.config.fb_client_library)
            drv = _driver()
            self._connection = drv.connect(
                self.config.dsn,
                user=self.config.user,
                password=self.config.password,
                charset="UTF8",
            )
            log.debug("Connected to WinVet database")
        return self

    def close(self) -> None:
        if self._connection is not None:
            try:
                self._connection.close()
            finally:
                self._connection = None

    def __enter__(self) -> "ReadOnlyDatabase":
        return self.connect()

    def __exit__(self, *exc) -> None:
        self.close()

    @contextmanager
    def transaction(self) -> Iterator[ReadOnlyTransaction]:
        """Open a short read-only SNAPSHOT transaction; it is always rolled back at the end."""
        self.connect()
        drv = _driver()
        manager = self._connection.transaction_manager(
            default_tpb=read_only_tpb(), default_action=drv.DefaultAction.ROLLBACK
        )
        manager.begin()
        try:
            yield ReadOnlyTransaction(self, manager)
        finally:
            try:
                if manager.is_active():
                    manager.rollback()
            finally:
                manager.close()

    def query_all(self, sql: str, params: Sequence[Any] = ()) -> List[tuple]:
        with self.transaction() as tx:
            return list(tx.query(sql, params, self.chunk_size))

    def scalar(self, sql: str, params: Sequence[Any] = ()) -> Optional[Any]:
        with self.transaction() as tx:
            return tx.scalar(sql, params)
