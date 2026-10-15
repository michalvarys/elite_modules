"""Shared helpers for the tests (not a test module itself).

Integration tests use the local analysis copy of WinVet. Override with environment variables:
WINVET_TEST_DSN, WINVET_TEST_USER, WINVET_TEST_PASSWORD, WINVET_TEST_FBCLIENT.
They are skipped when the database is not reachable.
"""

from __future__ import annotations

import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import List, Optional, Set

from winvet_bridge.config import FirebirdConfig

LOCAL_ROOT = Path(__file__).resolve().parents[4] / "winvet-local"
DEFAULT_DSN = "localhost/3050:/var/lib/firebird/data/winvet.fdb"

_db_state = {"checked": False, "reason": None}


def _local_password() -> Optional[str]:
    env_file = LOCAL_ROOT / ".env"
    if not env_file.is_file():
        return None
    for line in env_file.read_text(encoding="utf-8").splitlines():
        if line.startswith("FIREBIRD_ROOT_PASSWORD="):
            return line.split("=", 1)[1].strip()
    return None


def local_firebird_config() -> Optional[FirebirdConfig]:
    password = os.environ.get("WINVET_TEST_PASSWORD") or _local_password()
    if not password:
        return None
    lib = os.environ.get("WINVET_TEST_FBCLIENT")
    if not lib:
        candidate = LOCAL_ROOT / "lib" / "libfbclient.so.2"
        lib = str(candidate) if candidate.is_file() else None
    return FirebirdConfig(
        dsn=os.environ.get("WINVET_TEST_DSN", DEFAULT_DSN),
        user=os.environ.get("WINVET_TEST_USER", "SYSDBA"),
        password=password,
        fb_client_library=Path(lib) if lib else None,
    )


def db_unavailable_reason() -> Optional[str]:
    """None when the local WinVet copy is reachable, otherwise a reason to skip."""
    if _db_state["checked"]:
        return _db_state["reason"]
    _db_state["checked"] = True
    config = local_firebird_config()
    if config is None:
        _db_state["reason"] = "no WinVet test database configured"
        return _db_state["reason"]
    try:
        from winvet_bridge.db import ReadOnlyDatabase

        with ReadOnlyDatabase(config) as db:
            db.scalar("select 1 from rdb$database")
    except Exception as exc:  # driver missing, client library missing, server down ...
        _db_state["reason"] = f"WinVet test database not reachable: {type(exc).__name__}"
    return _db_state["reason"]


# --------------------------------------------------------------------------- fake Odoo


class FakeOdoo:
    """A tiny HTTP server that records JSON-RPC calls and answers like the Odoo module."""

    def __init__(self, api_key: str = "secret-key"):
        self.api_key = api_key
        self.calls: List[dict] = []  # {"path", "auth", "body"}
        self.fail_push_at: Optional[int] = None  # 1-based index of push call answered ok:false
        self.http_errors: List[int] = []  # status codes to answer before succeeding
        #: entities answered like an Odoo without the receiving module (contract v2)
        self.unknown_entities: Set[str] = set()
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):  # silence
                pass

            def do_POST(self):
                length = int(self.headers.get("Content-Length", 0))
                body = json.loads(self.rfile.read(length).decode("utf-8"))
                fake.calls.append({"path": self.path, "auth": self.headers.get("Authorization"), "body": body})
                if fake.http_errors:
                    self.send_response(fake.http_errors.pop(0))
                    self.end_headers()
                    return
                params = body.get("params", {})
                if self.headers.get("Authorization") != f"Bearer {fake.api_key}":
                    result = {"ok": False, "error": "unauthorized"}
                elif self.path.endswith("/push"):
                    index = sum(1 for c in fake.calls if c["path"].endswith("/push"))
                    if fake.fail_push_at is not None and index == fake.fail_push_at:
                        result = {"ok": False, "error": "boom"}
                    elif params.get("entity") in fake.unknown_entities:
                        result = {"ok": False, "error": "unknown entity"}
                    else:
                        result = {"ok": True, "created": len(params.get("records", [])), "updated": 0,
                                  "deleted": len(params.get("deleted", [])), "skipped": 0}
                else:
                    result = {"ok": True}
                data = json.dumps({"jsonrpc": "2.0", "id": body.get("id"), "result": result}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def __enter__(self) -> "FakeOdoo":
        self.thread.start()
        return self

    def __exit__(self, *exc) -> None:
        self.server.shutdown()
        self.server.server_close()

    def pushes(self) -> List[dict]:
        return [c["body"]["params"] for c in self.calls if c["path"].endswith("/push")]


# Keep test output readable: the bridge's warnings are asserted through behaviour, not log text.
import logging as _logging

_logging.getLogger("winvet_bridge").setLevel(_logging.ERROR)
